import logging
from collections import defaultdict
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme

from tracker.models import UpdateCache, Project, StackComponent, FutureUpdateCache, NotificationRecord
from tracker.forms import LoginForm, RegistrationForm
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
    
    return render(request, 'tracker/login.html', {'form': form})


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
    
    return render(request, 'tracker/register.html', {'form': form})


@login_required
def dashboard(request):
    """
    New Analytics Dashboard.
    Displays high-level metrics and charts.
    """
    projects_qs = _user_projects_queryset(request)
    total_projects = projects_qs.count()
    
    # Count total libraries (using StackComponent or unique libraries)
    # Using StackComponent gives us the libraries actually tracked in projects
    total_components = StackComponent.objects.filter(project__owner=request.user).exclude(key='language').count()
    
    # Calculate unique category breakdown using optimized SQL
    from django.db.models import Case, When, Value, CharField, Count

    # Annotate components with normalized category buckets
    # Logic mirrors previous python mapping: language -> languages, tool -> tools, module -> modules, else -> libraries
    annotated_components = StackComponent.objects.filter(project__owner=request.user).annotate(
        norm_cat=Case(
            When(key__icontains='language', then=Value('languages')),
            When(category__icontains='language', then=Value('languages')),
            When(category__icontains='tool', then=Value('tools')),
            When(category__icontains='module', then=Value('modules')),
            default=Value('libraries'),
            output_field=CharField(),
        )
    )

    # Get unique counts per category bucket
    # We want count of unique NAMES per bucket
    category_aggs = annotated_components.values('norm_cat').annotate(
        unique_count=Count('name', distinct=True)
    )

    # Convert to dictionary for context
    category_counts = {
        "languages": 0,
        "libraries": 0, 
        "tools": 0,
        "modules": 0
    }
    
    total_unique_items = 0
    for entry in category_aggs:
        cat = entry['norm_cat']
        count = entry['unique_count']
        if cat in category_counts:
            category_counts[cat] = count
        # For total unique, complex because same name could appear in diff buckets (rare but possible)
        # We'll trust the sum of buckets or doing a separate distinct count
    
    # Total unique stack count (across all categories)
    total_unique_stack_count = StackComponent.objects.filter(project__owner=request.user).values('name', 'category').distinct().count()

    
    # Calculate updates available
    updates_qs = UpdateCache.objects.filter(project__owner=request.user)
    total_updates = updates_qs.count()
    
    major_updates = updates_qs.filter(category='major').count()
    minor_updates = updates_qs.filter(category='minor').count()
    
    # Future updates
    tracked_libraries = StackComponent.objects.filter(
        project__owner=request.user
    ).exclude(key="language").values_list("name", flat=True)
    tracked_library_keys = {name.strip().lower() for name in tracked_libraries if name and name.strip()}
    future_updates_count = sum(
        1
        for update in FutureUpdateCache.objects.filter(status__in=['detected', 'confirmed'])
        if (update.library or "").strip().lower() in tracked_library_keys
    )
    
    # Health Score Calculation
    # Simple logic: 100 - (updates / components * 100)
    # If components is 0, score is 100.
    health_score = 100
    if total_components > 0:
        ratio = total_updates / total_components
        # Cap at 100% impact (meaning 0 score) if ratio > 1
        params = min(ratio, 1.0)
        health_score = int((1.0 - params) * 100)
    
    context = {
        "total_projects": total_projects,
        "total_components": total_components,
        "total_updates": total_updates,
        "major_updates": major_updates,
        "minor_updates": minor_updates,
        "future_updates_count": future_updates_count,
        "total_unique_stack_count": total_unique_stack_count,
        "health_score": health_score,
        # Category breakdown
        "languages_count": category_counts["languages"],
        "libraries_count": category_counts["libraries"],
        "tools_count": category_counts["tools"],
        "modules_count": category_counts["modules"],
    }
    return render(request, "tracker/dashboard.html", context)


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
        paginator = Paginator(regs, 5)
        registrations_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "tracker/projects.html",
        {
            "registrations_page": registrations_page,
            "registrations_total": registrations_total,
            "registrations_per_page": 5,
            "cache": cache,
            "future_updates": future_updates,  # ===== NEW =====
        },
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

    cache_qs = UpdateCache.objects.filter(project__owner=request.user).order_by("-updated_at").all()
    cache = list(cache_qs)
    for entry in cache:
        lib_key = (entry.library or "").strip().lower()
        entry.project_names = project_lookup.get(lib_key, [])
        entry.release_date_formatted = ProjectService.format_release_date(entry.release_date)

        # Fetch latest notification record to show status
        latest_notification = NotificationRecord.objects.filter(
            project=entry.project,
            library=entry.library
        ).order_by("-created_at").first()
        entry.last_notification_success = latest_notification.success if latest_notification else None
        entry.last_notification_sent_at = latest_notification.sent_at if latest_notification else None

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
