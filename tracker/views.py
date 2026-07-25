import logging
import os
import threading
from datetime import timedelta
from collections import defaultdict
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.management import call_command
from django.db import close_old_connections
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from tracker.models import (
    DailyCheckRun,
    FutureUpdateCache,
    Project,
    SecurityVulnerability,
    StackComponent,
    UpdateCache,
    UpdateEvent,
)
from tracker.forms import LoginForm, RegistrationForm
from tracker.services.dashboard_metrics_service import DashboardMetricsService
from tracker.services.github_repo_import_service import GitHubRepoImportService
from tracker.services.manifest_parser_service import ManifestParserService
from tracker.services.project_service import ProjectService

logger = logging.getLogger("libtrack")


def _user_projects_queryset(request):
    return Project.objects.filter(owner=request.user)

def login_view(request):
    """
    Handles user login.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                next_url = request.GET.get('next', '')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(
        request,
        'tracker/login.html',
        {'form': form, 'github_login_enabled': settings.GITHUB_LOGIN_ENABLED},
    )


def logout_view(request):
    """
    Handles user logout.
    """
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


def register_view(request):
    """
    Handles user registration.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created successfully for {username}! Please log in.')
            return redirect('login')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.capitalize()}: {error}')
    else:
        form = RegistrationForm()
    
    return render(
        request,
        'tracker/register.html',
        {'form': form, 'github_login_enabled': settings.GITHUB_LOGIN_ENABLED},
    )


@login_required
def dashboard(request):
    """
    New Analytics Dashboard.
    Displays high-level metrics and charts.
    """
    context = DashboardMetricsService.build_for_owner(request.user)
    active_statuses = ["queued", "running"]
    recent_runs_qs = DailyCheckRun.objects.select_related("triggered_by", "scope_owner")
    if request.user.is_staff or request.user.is_superuser:
        recent_runs = recent_runs_qs.order_by("-created_at")[:5]
    else:
        recent_runs = recent_runs_qs.filter(scope_owner=request.user).order_by("-created_at")[:5]

    active_manual_run = DailyCheckRun.objects.filter(
        scope_owner=request.user,
        status__in=active_statuses,
    ).order_by("-created_at").first()
    latest_manual_run = DailyCheckRun.objects.filter(scope_owner=request.user).order_by("-created_at").first()
    cooldown_since = timezone.now() - timedelta(minutes=15)
    cooldown_run = DailyCheckRun.objects.filter(
        scope_owner=request.user,
        created_at__gte=cooldown_since,
    ).exclude(status__in=active_statuses).order_by("-created_at").first()
    context.update(
        {
            "recent_daily_check_runs": recent_runs,
            "active_manual_run": active_manual_run,
            "latest_manual_run": latest_manual_run,
            "manual_run_cooldown_active": bool(cooldown_run),
            "manual_run_cooldown_minutes": 15,
            "email_test_mode": os.getenv("TEST_MODE", "True").lower() in {"1", "true", "yes", "y"},
        }
    )
    return render(request, "tracker/dashboard.html", context)


@login_required
@require_POST
def run_daily_check_now(request):
    """
    Trigger an owner-scoped manual daily check from the dashboard.
    Admin users may explicitly request a global run.
    """
    active_statuses = ["queued", "running"]
    requested_scope = request.POST.get("scope", "owner")
    is_admin = request.user.is_staff or request.user.is_superuser
    is_global = requested_scope == "global" and is_admin
    scope_owner = None if is_global else request.user

    active_qs = DailyCheckRun.objects.filter(status__in=active_statuses)
    if is_global:
        active_qs = active_qs.filter(scope="global")
    else:
        active_qs = active_qs.filter(scope_owner=request.user)
    if active_qs.exists():
        messages.warning(request, "A check is already running. Wait for it to finish before starting another one.")
        return redirect("dashboard")

    cooldown_since = timezone.now() - timedelta(minutes=15)
    cooldown_qs = DailyCheckRun.objects.filter(created_at__gte=cooldown_since).exclude(status__in=active_statuses)
    if is_global:
        cooldown_qs = cooldown_qs.filter(scope="global", triggered_by=request.user)
    else:
        cooldown_qs = cooldown_qs.filter(scope_owner=request.user)
    if cooldown_qs.exists():
        messages.warning(request, "Manual checks are limited to one run every 15 minutes.")
        return redirect("dashboard")

    run = DailyCheckRun.objects.create(
        triggered_by=request.user,
        scope="global" if is_global else "owner",
        scope_owner=scope_owner,
        status="queued",
    )
    thread = threading.Thread(
        target=_run_daily_check_background,
        args=(run.id, request.user.id if not is_global else None, is_global),
        daemon=True,
    )
    thread.start()

    if is_global:
        messages.success(request, "Global check started. Status will update in Recent Runs.")
    else:
        messages.success(request, "Check started for your projects. Status will update in Recent Runs.")
    return redirect("dashboard")


@login_required
def run_daily_check_status(request):
    """Return current user's latest manual check status for dashboard polling."""
    run_id = request.GET.get("run_id")
    runs = DailyCheckRun.objects.select_related("triggered_by", "scope_owner")
    if run_id:
        runs = runs.filter(pk=run_id)
    if request.user.is_staff or request.user.is_superuser:
        run = runs.order_by("-created_at").first()
    else:
        run = runs.filter(scope_owner=request.user).order_by("-created_at").first()
    if not run:
        return JsonResponse({"ok": False, "error": "run_not_found"}, status=404)

    return JsonResponse(
        {
            "ok": True,
            "id": run.id,
            "status": run.status,
            "status_label": run.status.title(),
            "is_active": run.status in {"queued", "running"},
            "started_at": timezone.localtime(run.started_at).strftime("%b %d, %Y %H:%M") if run.started_at else "",
            "finished_at": timezone.localtime(run.finished_at).strftime("%b %d, %Y %H:%M") if run.finished_at else "",
            "duration": run.duration_label,
            "projects_scanned": run.projects_scanned,
            "libraries_checked": run.libraries_checked,
            "emails_sent": run.emails_sent,
            "emails_failed": run.emails_failed,
            "emails_skipped": run.emails_skipped,
            "error_message": run.error_message,
        }
    )


def _run_daily_check_background(run_id: int, owner_id: int | None, is_global: bool):
    close_old_connections()
    try:
        command_kwargs = {"manual_run_id": run_id}
        if is_global:
            command_kwargs["global_run"] = True
        else:
            command_kwargs["owner_id"] = owner_id
        call_command("run_daily_check", **command_kwargs)
    finally:
        close_old_connections()


@login_required
def projects_view(request):
    """
    Displays project active registrations (Renamed from Dashboard).
    """
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            payload, error = ProjectService.build_registration_payload(request)
            if error:
                messages.error(request, error)
            else:
                try:
                    ProjectService.save_project_from_payload(payload, owner=request.user)
                    messages.success(request, f"Project '{payload['project_name']}' added successfully.")
                except ValueError as exc:
                    messages.error(request, str(exc))
                except Exception:
                    logger.exception("Error while creating project")
                    messages.error(request, "Failed to add project. Please try again.")
            return redirect("projects")

        if action == "update":
            project_id = request.POST.get("project_id")
            try:
                project = _user_projects_queryset(request).prefetch_related("components").get(pk=int(project_id))
            except (TypeError, ValueError, Project.DoesNotExist):
                messages.error(request, "Invalid project reference for update.")
                return redirect("projects")

            payload, error = ProjectService.build_registration_payload(request)
            if error:
                messages.error(request, error)
                return redirect("projects")

            try:
                ProjectService.save_project_from_payload(payload, instance=project, owner=request.user)
                messages.success(request, f"Project '{payload['project_name']}' updated.")
            except ValueError as exc:
                messages.error(request, str(exc))
            except Exception:
                logger.exception("Error while updating project")
                messages.error(request, "Failed to update project. Please try again.")
            return redirect("projects")

        if action == "delete":
            project_id = request.POST.get("project_id")
            try:
                project = _user_projects_queryset(request).get(pk=int(project_id))
            except (TypeError, ValueError, Project.DoesNotExist):
                messages.error(request, "Invalid project reference for deletion.")
                return redirect("projects")

            project_name = request.POST.get("project_name") or project.project_name or "Project"
            project.delete()
            messages.success(request, f"{project_name} deleted.")
            return redirect("projects")

        messages.error(request, "Unknown action.")
        return redirect("projects")

    project_qs = _user_projects_queryset(request).prefetch_related("components").order_by("-created_at")
    regs = [ProjectService.serialize_project(project) for project in project_qs]

    cache = UpdateCache.objects.filter(project__owner=request.user).order_by("-updated_at").all()

    user_library_keys = {
        component.name.strip().lower()
        for project in project_qs
        for component in project.components.all()
        if component.name and component.name.strip()
    }
    future_updates = [
        update
        for update in FutureUpdateCache.objects.filter(
            status__in=['detected', 'confirmed']
        ).order_by('-confidence', '-updated_at')
        if (update.library or "").strip().lower() in user_library_keys
    ][:10]

    registrations_total = len(regs)
    registrations_page = None
    if registrations_total:
        paginator = Paginator(regs, 10)
        registrations_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "tracker/projects.html",
        {
            "registrations_page": registrations_page,
            "registrations_total": registrations_total,
            "registrations_per_page": 10,
            "cache": cache,
            "future_updates": future_updates,  # ===== NEW =====
        },
    )


@login_required
@require_POST
def parse_manifest(request):
    manifest_type = request.POST.get("manifest_type", "")
    content = request.POST.get("manifest_content", "")

    uploaded = request.FILES.get("manifest_file")
    if uploaded:
        try:
            content = uploaded.read().decode("utf-8")
        except UnicodeDecodeError:
            return JsonResponse(
                {
                    "ok": False,
                    "components": [],
                    "warnings": [],
                    "error": "Uploaded manifest must be UTF-8 text.",
                },
                status=400,
            )

    result = ManifestParserService.parse(manifest_type, content)
    ok = not result.get("error")
    return JsonResponse(
        {
            "ok": ok,
            "components": result.get("components", []),
            "warnings": result.get("warnings", []),
            "error": result.get("error", ""),
        },
        status=200 if ok else 400,
    )


@login_required
@require_POST
def import_github_repo(request):
    repo_url = request.POST.get("repo_url", "")
    result = GitHubRepoImportService().import_repository(repo_url)
    ok = not result.get("error")
    return JsonResponse(
        {
            "ok": ok,
            "components": result.get("components", []),
            "warnings": result.get("warnings", []),
            "files": result.get("files", []),
            "repository": result.get("repository", ""),
            "default_branch": result.get("default_branch", ""),
            "error": result.get("error", ""),
        },
        status=200 if ok else 400,
    )


@login_required
def updateHistory(request):
    """
    Displays project update cache.
    """
    project_lookup: dict[str, list[str]] = {}
    project_names: list[str] = []

    projects = _user_projects_queryset(request).prefetch_related("components").all()
    if projects:
        map_temp: dict[str, set[str]] = defaultdict(set)
        projects_set: set[str] = set()
        for project in projects:
            project_name = (project.project_name or "").strip()
            if not project_name:
                continue
            projects_set.add(project_name)
            for component in project.components.all():
                if component.key == "language":
                    continue
                lib_key = (component.name or "").strip().lower()
                if not lib_key:
                    continue
                map_temp[lib_key].add(project_name)
        project_lookup = {lib: sorted(list(names), key=str.casefold) for lib, names in map_temp.items()}
        project_names = sorted(projects_set, key=str.casefold)

    cache_qs = UpdateEvent.objects.filter(project__owner=request.user).select_related("project").order_by("-updated_at").all()
    cache = list(cache_qs)
    for entry in cache:
        lib_key = (entry.library or "").strip().lower()
        project_name = (entry.project.project_name or "").strip()
        entry.project_names = [project_name] if project_name else project_lookup.get(lib_key, [])
        entry.release_date_formatted = ProjectService.format_release_date(entry.release_date)
        entry.last_notification_success = entry.notification_success
        entry.last_notification_sent_at = entry.notification_sent_at

    selected_project = (request.GET.get("project") or "").strip()
    if selected_project:
        filtered_cache = [entry for entry in cache if selected_project in entry.project_names]
    else:
        filtered_cache = cache

    history_total = len(filtered_cache)
    history_page = None
    if history_total:
        paginator = Paginator(filtered_cache, 10)
        history_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "tracker/history.html",
        {
            "history_page": history_page,
            "history_total": history_total,
            "history_per_page": 10,
            "selected_project": selected_project,
            "project_names": project_names,
        },
    )


@login_required
def future_updates(request):
    """
    Displays future/planned updates with filtering and pagination.
    """
    # Build project lookup for filtering
    map_temp = defaultdict(set)
    projects_set = set()

    project_qs = _user_projects_queryset(request).prefetch_related("components").all()
    for project in project_qs:
        project_name = (project.project_name or "").strip()
        if not project_name:
            continue
        projects_set.add(project_name)
        for component in project.components.all():
            lib_key = (component.name or "").strip().lower()
            if not lib_key:
                continue
            map_temp[lib_key].add(project_name)

    project_lookup = {lib: sorted(list(names), key=str.casefold) for lib, names in map_temp.items()}
    project_names = sorted(projects_set, key=str.casefold)

    # Get all future updates
    future_qs = FutureUpdateCache.objects.order_by('-confidence', '-updated_at').all()
    future_list = list(future_qs)
    
    # Attach project names to each future update
    for entry in future_list:
        lib_key = (entry.library or "").strip().lower()
        entry.project_names = project_lookup.get(lib_key, [])
    future_list = [entry for entry in future_list if entry.project_names]
    
    # Filter by project if selected
    selected_project = (request.GET.get("project") or "").strip()
    if selected_project:
        future_list = [entry for entry in future_list if selected_project in entry.project_names]
    
    # Filter by status if selected
    selected_status = (request.GET.get("status") or "").strip()
    if selected_status:
        future_list = [entry for entry in future_list if entry.status == selected_status]
    
    # Pagination
    future_total = len(future_list)
    future_page = None
    if future_total:
        paginator = Paginator(future_list, 10)
        future_page = paginator.get_page(request.GET.get("page"))
    
    # Status choices for filter dropdown
    status_choices = ['detected', 'confirmed', 'released', 'cancelled']
    
    return render(
        request,
        "tracker/future_updates.html",
        {
            "future_page": future_page,
            "future_total": future_total,
            "future_per_page": 10,
            "selected_project": selected_project,
            "selected_status": selected_status,
            "project_names": project_names,
            "status_choices": status_choices,
        },
    )


@login_required
def security_alerts(request):
    """
    Displays OSV-backed security vulnerability alerts for the user's projects.
    """
    projects = _user_projects_queryset(request).order_by("project_name")
    project_names = list(projects.values_list("project_name", flat=True))

    selected_project = (request.GET.get("project") or "").strip()
    selected_status = (request.GET.get("status") or "active").strip()

    alerts_qs = SecurityVulnerability.objects.filter(
        project__owner=request.user,
    ).select_related("project", "component").order_by("status", "-updated_at")

    if selected_project:
        alerts_qs = alerts_qs.filter(project__project_name=selected_project)

    if selected_status:
        alerts_qs = alerts_qs.filter(status=selected_status)

    alerts_total = alerts_qs.count()
    alerts_page = None
    if alerts_total:
        paginator = Paginator(alerts_qs, 10)
        alerts_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "tracker/security_alerts.html",
        {
            "alerts_page": alerts_page,
            "alerts_total": alerts_total,
            "alerts_per_page": 10,
            "selected_project": selected_project,
            "selected_status": selected_status,
            "project_names": project_names,
            "status_choices": ["active", "resolved", "ignored"],
        },
    )


@login_required
def profile_view(request):
    """
    Displays user profile and handles password change.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'tracker/profile.html', {
        'form': form
    })


@login_required
def settings_view(request):
    """
    User settings page for managing per-project notification preferences.
    Allows users to toggle notify_paused and set min_confidence_threshold.
    """
    projects = _user_projects_queryset(request).order_by('project_name')
    
    if request.method == 'POST':
        try:
            for project in projects:
                # Get form data for this project
                notify_paused_key = f"notify_paused_{project.id}"
                threshold_key = f"min_confidence_threshold_{project.id}"
                
                # Handle notify_paused toggle (checkbox)
                notify_paused = request.POST.get(notify_paused_key) == 'on'
                
                # Handle threshold value
                threshold_str = request.POST.get(threshold_key, "50").strip()
                try:
                    threshold = int(threshold_str)
                    if threshold < 0:
                        threshold = 0
                    elif threshold > 100:
                        threshold = 100
                except (ValueError, TypeError):
                    threshold = 50
                
                # Update project if changed
                project.notify_paused = notify_paused
                project.min_confidence_threshold = threshold
                project.save()
            
            messages.success(request, 'Project settings updated successfully!')
            return redirect('settings')
        except Exception as exc:
            messages.error(request, f'Error updating settings: {str(exc)}')
            logger.exception("Error in settings_view POST")
    
    return render(request, 'tracker/settings.html', {
        'projects': projects,
    })
