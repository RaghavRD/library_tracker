import json
import traceback
from collections import defaultdict
from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator

from tracker.utils.google_sheet_manager import GoogleSheetManager
from tracker.models import UpdateCache

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
    return payload, None


def _split_csv_preserve(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",")]


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


def _stack_from_registration(reg: dict) -> list[dict]:
    """
    Returns normalized stack components from the stored tech_stack JSON.
    Falls back to legacy language/library CSVs for older rows.
    """
    stack_raw = reg.get("tech_stack", "")
    stack: list[dict] = []

    if stack_raw:
        try:
            parsed = json.loads(stack_raw)
        except json.JSONDecodeError:
            parsed = []
        for component in parsed or []:
            category = (
                str(component.get("category") or component.get("type") or component.get("key") or "Component").strip()
                or "Component"
            )
            key = (component.get("key") or category).strip().lower() or "component"
            if "language" in key:
                key = "language"
            stack.append(
                {
                    "category": category,
                    "key": key,
                    "name": str(component.get("name", "")).strip(),
                    "version": str(component.get("version", "")).strip(),
                    "scope": str(component.get("scope", "")).strip(),
                }
            )

    if stack:
        return stack

    languages = _split_csv_preserve(reg.get("language_used"))
    language_versions = _split_csv_preserve(reg.get("language_version"))
    for idx, lang in enumerate(languages):
        if not lang:
            continue
        version = language_versions[idx] if idx < len(language_versions) else ""
        stack.append(
            {
                "category": "Language",
                "key": "language",
                "name": lang,
                "version": version,
                "scope": "",
            }
        )

    libs = _split_csv_preserve(reg.get("libraries"))
    lib_versions = _split_csv_preserve(reg.get("library_versions"))
    for idx, lib in enumerate(libs):
        if not lib:
            continue
        version = lib_versions[idx] if idx < len(lib_versions) else ""
        stack.append(
            {
                "category": "Dependency",
                "key": "dependency",
                "name": lib,
                "version": version,
                "scope": "",
            }
        )

    return stack


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
            gsm = GoogleSheetManager()
            gsm.append_registration(payload)
            messages.success(request, f"Project '{payload['project_name']}' saved successfully!")
        except Exception:
            print("Error while saving registration:", traceback.format_exc())
            messages.error(request, "Failed to save to Google Sheets. Please try again later.")
            return render(request, "tracker/register.html")

        return redirect("dashboard")

    return render(request, "tracker/register.html")


def dashboard(request):
    """
    Displays project registrations and update cache.
    """
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            gsm = GoogleSheetManager()
        except Exception:
            print("Error while instantiating GoogleSheetManager:", traceback.format_exc())
            messages.error(request, "Could not connect to Google Sheets.")
            return redirect("dashboard")

        if action == "create":
            payload, error = _build_registration_payload(request)
            if error:
                messages.error(request, error)
            else:
                try:
                    gsm.append_registration(payload)
                    messages.success(request, f"Project '{payload['project_name']}' added successfully.")
                except Exception:
                    print("Error while creating registration:", traceback.format_exc())
                    messages.error(request, "Failed to add project. Please try again.")
            return redirect("dashboard")

        if action == "update":
            row_id = request.POST.get("row_id")
            try:
                row_int = int(row_id)
            except (TypeError, ValueError):
                messages.error(request, "Invalid project reference for update.")
                return redirect("dashboard")

            payload, error = _build_registration_payload(request)
            if error:
                messages.error(request, error)
                return redirect("dashboard")

            try:
                gsm.update_registration(row_int, payload)
                messages.success(request, f"Project '{payload['project_name']}' updated.")
            except Exception:
                print("Error while updating registration:", traceback.format_exc())
                messages.error(request, "Failed to update project. Please try again.")
            return redirect("dashboard")

        if action == "delete":
            row_id = request.POST.get("row_id")
            try:
                row_int = int(row_id)
            except (TypeError, ValueError):
                messages.error(request, "Invalid project reference for deletion.")
                return redirect("dashboard")

            project_name = request.POST.get("project_name") or "Project"
            try:
                gsm.delete_registration(row_int)
                messages.success(request, f"{project_name} deleted.")
            except Exception:
                print("Error while deleting registration:", traceback.format_exc())
                messages.error(request, "Failed to delete project. Please try again.")
            return redirect("dashboard")

        messages.error(request, "Unknown action.")
        return redirect("dashboard")

    try:
        gsm = GoogleSheetManager()
        regs = gsm.read_all_registrations()
    except Exception as e:
        print("Error while reading registrations:", traceback.format_exc())
        regs = []
        messages.error(request, "Could not fetch Google Sheet data.")
    else:
        for reg in regs:
            stack_components = _stack_from_registration(reg)
            reg["stack_components"] = stack_components
            reg["stack_json"] = json.dumps(stack_components)
            reg["notification_list"] = [
                x.strip() for x in str(reg.get("notification_type", "") or "").split(",") if x.strip()
            ]

    cache = UpdateCache.objects.order_by("-updated_at").all()

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
        },
    )

def updateHistory(request):
    """
    Displays project update cache.
    """
    project_lookup: dict[str, list[str]] = {}
    project_names: list[str] = []

    try:
        gsm = GoogleSheetManager()
        regs = gsm.read_all_registrations()
    except Exception:
        regs = []
        messages.error(request, "Could not fetch Google Sheet data for project filters.")

    if regs:
        map_temp: dict[str, set[str]] = defaultdict(set)
        projects_set: set[str] = set()
        for reg in regs:
            project = str(reg.get("project_name", "")).strip()
            libs_raw = str(reg.get("libraries", "") or "")
            libraries = [lib.strip().lower() for lib in libs_raw.split(",") if lib.strip()]
            if not project or not libraries:
                continue
            projects_set.add(project)
            for lib in libraries:
                map_temp[lib].add(project)
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
