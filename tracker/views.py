import json
import traceback
from collections import defaultdict
from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction

from tracker.models import UpdateCache, Project, StackComponent
from tracker.forms import LoginForm, RegistrationForm

VALID_NOTIFICATION_TYPES = {"both", "major", "minor", "future"}
NOTIFICATION_ORDER = ("major", "minor", "future")
STANDARD_DATE_OUTPUT = "%Y-%m-%d"

def _normalize_notification_types(selected: list[str]) -> set[str]:
    normalized: set[str] = set()
    for choice in selected:
        value = choice.strip().lower()
        if not value:
            continue
        if value == "both":
            normalized.update({"major", "minor"})
            continue
        if value in VALID_NOTIFICATION_TYPES and value != "both":
            normalized.add(value)
    if not normalized:
        normalized.update({"major", "minor"})
    return normalized

def _validate_emails(csv: str):
    """
    Validates a comma-separated string of emails.
    Returns a list of valid emails or None if any are invalid.
    """
    emails = [e.strip() for e in csv.split(",") if e.strip()]
    for e in emails:
        try:
            validate_email(e)
        except ValidationError:
            return None
    return emails


def _build_registration_payload(request):
    """
    Extracts and validates registration form data from POST requests.
    Returns a tuple of (payload_dict, error_message).
    """
    project_name = request.POST.get("project_name", "").strip()
    developer_names = request.POST.get("developer_names", "").strip()
    developer_emails_raw = request.POST.get("developer_emails", "").strip()
    notification_selections = request.POST.getlist("notification_types")
    normalized_preferences = _normalize_notification_types(notification_selections or ["major", "minor"])
    notification_type = ", ".join([option for option in NOTIFICATION_ORDER if option in normalized_preferences])

    if not all([project_name, developer_names, developer_emails_raw]):
        return None, "Please complete the project and team fields before submitting."

    emails = _validate_emails(developer_emails_raw)
    if emails is None:
        return None, "One or more developer emails are invalid."

    component_types = request.POST.getlist("component_type[]")
    component_names = request.POST.getlist("component_name[]")
    component_versions = request.POST.getlist("component_version[]")
    component_scopes = request.POST.getlist("component_scope[]")

    components: list[dict] = []
    for idx, raw_name in enumerate(component_names):
        name = raw_name.strip()
        if not name:
            continue

        version = component_versions[idx].strip() if idx < len(component_versions) else ""
        if not version:
            return None, f"Please provide a version for '{name}'."

        type_label = component_types[idx].strip() if idx < len(component_types) else ""
        scope = component_scopes[idx].strip() if idx < len(component_scopes) else ""
        category = type_label or "Dependency"
        key = category.strip().lower() or "dependency"
        if "language" in key:
            key = "language"
        components.append(
            {
                "category": category,
                "key": key,
                "name": name,
                "version": version,
                "scope": scope,
            }
        )

    if not components:
        return None, "Add at least one technology component to the stack."

    languages = [c for c in components if c["key"] == "language"]
    others = [c for c in components if c["key"] != "language"]

    payload = {
        "project_name": project_name,
        "developer_names": developer_names,
        "developer_emails": ", ".join(emails),
        "language_used": ", ".join([c["name"] for c in languages]),
        "language_version": ", ".join([c["version"] for c in languages]),
        "libraries": ", ".join([c["name"] for c in others]),
        "library_versions": ", ".join([c["version"] for c in others]),
        "notification_type": notification_type,
        "tech_stack": json.dumps(components),
    }
    payload["stack_components"] = components
    return payload, None


def _format_release_date(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    known_formats = (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
    )

    for fmt in known_formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime(STANDARD_DATE_OUTPUT)
        except ValueError:
            continue

    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime(STANDARD_DATE_OUTPUT)
    except ValueError:
        pass

    return value


def _normalize_component_key(category: str, key: str | None) -> str:
    candidate = (key or category or "dependency").strip().lower() or "dependency"
    if "language" in candidate:
        return "language"
    return candidate


def _parse_stack_payload(payload: dict) -> list[dict]:
    stack = payload.get("stack_components")
    if stack is None:
        try:
            stack = json.loads(payload.get("tech_stack", "[]") or "[]")
        except json.JSONDecodeError:
            stack = []

    normalized: list[dict] = []
    for component in stack or []:
        name = str(component.get("name", "")).strip()
        version = str(component.get("version", "")).strip()
        if not name or not version:
            continue
        category = str(component.get("category") or component.get("type") or "Dependency").strip() or "Dependency"
        key = _normalize_component_key(category, component.get("key"))
        scope = str(component.get("scope", "")).strip()
        normalized.append(
            {
                "category": category,
                "key": key,
                "name": name,
                "version": version,
                "scope": scope,
            }
        )
    return normalized


def _save_project_from_payload(payload: dict, *, instance: Project | None = None) -> Project:
    stack = _parse_stack_payload(payload)
    if not stack:
        raise ValueError("Add at least one technology component to the stack.")

    notification_value = payload.get("notification_type") or "major, minor"

    with transaction.atomic():
        if instance is None:
            instance = Project.objects.create(
                project_name=payload["project_name"],
                developer_names=payload["developer_names"],
                developer_emails=payload["developer_emails"],
                notification_type=notification_value,
            )
        else:
            instance.project_name = payload["project_name"]
            instance.developer_names = payload["developer_names"]
            instance.developer_emails = payload["developer_emails"]
            instance.notification_type = notification_value
            instance.save()
            instance.components.all().delete()

        StackComponent.objects.bulk_create(
            [
                StackComponent(
                    project=instance,
                    category=item["category"],
                    key=item["key"],
                    name=item["name"],
                    version=item["version"],
                    scope=item["scope"],
                )
                for item in stack
            ]
        )

    return instance


def _serialize_project(project: Project) -> dict:
    components = [
        {
            "id": component.id,
            "category": component.category,
            "key": component.key,
            "name": component.name,
            "version": component.version,
            "scope": component.scope,
        }
        for component in project.components.all()
    ]

    languages = [comp for comp in components if comp["key"] == "language"]
    notification_list = [item.strip() for item in (project.notification_type or "").split(",") if item.strip()]
    if not notification_list:
        notification_list = ["major", "minor"]

    return {
        "project_id": project.id,
        "project_name": project.project_name,
        "developer_names": project.developer_names,
        "developer_emails": project.developer_emails,
        "language_used": ", ".join([comp["name"] for comp in languages]),
        "language_version": ", ".join([comp["version"] for comp in languages]),
        "stack_components": components,
        "stack_json": json.dumps(components),
        "notification_type": project.notification_type,
        "notification_list": notification_list,
    }


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
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
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


def register_project(request):
    """
    Handles project registration via HTML form.
    Validates input and stores project details in Google Sheets.
    Shows success/error toast messages on redirect.
    """
    if request.method == "POST":
        payload, error = _build_registration_payload(request)
        if error:
            messages.error(request, error)
            return render(request, "tracker/register.html")

        try:
            _save_project_from_payload(payload)
            messages.success(request, f"Project '{payload['project_name']}' saved successfully!")
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, "tracker/register.html")
        except Exception:
            print("Error while saving registration:", traceback.format_exc())
            messages.error(request, "Failed to save project. Please try again later.")
            return render(request, "tracker/register.html")

        return redirect("dashboard")

    return render(request, "tracker/register.html")


@login_required
def dashboard(request):
    """
    Displays project registrations and update cache.
    """
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            payload, error = _build_registration_payload(request)
            if error:
                messages.error(request, error)
            else:
                try:
                    _save_project_from_payload(payload)
                    messages.success(request, f"Project '{payload['project_name']}' added successfully.")
                except ValueError as exc:
                    messages.error(request, str(exc))
                except Exception:
                    print("Error while creating project:", traceback.format_exc())
                    messages.error(request, "Failed to add project. Please try again.")
            return redirect("dashboard")

        if action == "update":
            project_id = request.POST.get("project_id")
            try:
                project = Project.objects.prefetch_related("components").get(pk=int(project_id))
            except (TypeError, ValueError, Project.DoesNotExist):
                messages.error(request, "Invalid project reference for update.")
                return redirect("dashboard")

            payload, error = _build_registration_payload(request)
            if error:
                messages.error(request, error)
                return redirect("dashboard")

            try:
                _save_project_from_payload(payload, instance=project)
                messages.success(request, f"Project '{payload['project_name']}' updated.")
            except ValueError as exc:
                messages.error(request, str(exc))
            except Exception:
                print("Error while updating project:", traceback.format_exc())
                messages.error(request, "Failed to update project. Please try again.")
            return redirect("dashboard")

        if action == "delete":
            project_id = request.POST.get("project_id")
            try:
                project = Project.objects.get(pk=int(project_id))
            except (TypeError, ValueError, Project.DoesNotExist):
                messages.error(request, "Invalid project reference for deletion.")
                return redirect("dashboard")

            project_name = request.POST.get("project_name") or project.project_name or "Project"
            project.delete()
            messages.success(request, f"{project_name} deleted.")
            return redirect("dashboard")

        messages.error(request, "Unknown action.")
        return redirect("dashboard")

    project_qs = Project.objects.prefetch_related("components").order_by("-created_at")
    regs = [_serialize_project(project) for project in project_qs]

    cache = UpdateCache.objects.order_by("-updated_at").all()
    
    # ===== NEW: Fetch future updates =====
    from tracker.models import FutureUpdateCache
    future_updates = FutureUpdateCache.objects.filter(
        status__in=['detected', 'confirmed']
    ).order_by('-confidence', '-updated_at')[:10]

    registrations_total = len(regs)
    registrations_page = None
    if registrations_total:
        paginator = Paginator(regs, 5)
        registrations_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "tracker/dashboard.html",
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

    projects = Project.objects.prefetch_related("components").all()
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

    cache_qs = UpdateCache.objects.order_by("-updated_at").all()
    cache = list(cache_qs)
    for entry in cache:
        lib_key = (entry.library or "").strip().lower()
        entry.project_names = project_lookup.get(lib_key, [])
        entry.release_date_formatted = _format_release_date(entry.release_date)

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
    from tracker.models import FutureUpdateCache
    
    # Build project lookup for filtering
    project_names = []
    project_lookup = {}  # {library_key: [project_names]}
    
    if True:  # Always build lookup for filtering
        from collections import defaultdict
        map_temp = defaultdict(set)
        projects_set = set()
        
        project_qs = Project.objects.prefetch_related("components").all()
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
