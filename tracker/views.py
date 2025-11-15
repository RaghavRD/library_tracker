import traceback
from collections import defaultdict
from django.shortcuts import render, redirect
from django.contrib import messages
from tracker.utils.google_sheet_manager import GoogleSheetManager
from tracker.models import UpdateCache
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


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


def register_project(request):
    """
    Handles project registration via HTML form.
    Validates input and stores project details in Google Sheets.
    Shows success/error toast messages on redirect.
    """
    if request.method == "POST":
        project_name = request.POST.get("project_name", "").strip()
        developer_names = request.POST.get("developer_names", "").strip()
        developer_emails = request.POST.get("developer_emails", "").strip()
        language_used = request.POST.get("language_used", "").strip()
        language_version = request.POST.get("language_version", "").strip()
        libraries = request.POST.get("libraries", "").strip()
        library_versions = request.POST.get("library_versions", "").strip()
        notification_type = request.POST.get("notification_type", "both").strip().lower()

        # ✅ Required field validation
        if not all([project_name, developer_names, developer_emails, language_used, language_version, libraries, library_versions]):
            messages.error(request, "Please fill in all fields before submitting.")
            return render(request, "tracker/register.html")

        # ✅ Email validation
        emails = _validate_emails(developer_emails)
        if emails is None:
            messages.error(request, "One or more developer emails are invalid.")
            return render(request, "tracker/register.html")

        # ✅ Validate library–version alignment
        libs = [x.strip() for x in libraries.split(",") if x.strip()]
        vers = [x.strip() for x in library_versions.split(",") if x.strip()]
        if len(libs) != len(vers):
            messages.error(request, "Each library must have a corresponding version.")
            return render(request, "tracker/register.html")

        # ✅ Attempt to save to Google Sheets
        try:
            gsm = GoogleSheetManager()
            gsm.append_registration({
                "project_name": project_name,
                "developer_names": developer_names,
                "developer_emails": ", ".join(emails),
                "language_used": language_used,
                "language_version": language_version,
                "libraries": ", ".join(libs),
                "library_versions": ", ".join(vers),
                "notification_type": notification_type,
            })
            messages.success(request, f"Project '{project_name}' saved successfully!")
        except Exception as e:
            # Logs traceback in terminal for debugging
            print("Error while saving registration:", traceback.format_exc())
            messages.error(request, "Failed to save to Google Sheets. Please try again later.")
            return render(request, "tracker/register.html")

        # ✅ Redirect to Dashboard after success
        return redirect("dashboard")

    # GET → render form
    return render(request, "tracker/register.html")


def dashboard(request):
    """
    Displays project registrations and update cache.
    """
    try:
        gsm = GoogleSheetManager()
        regs = gsm.read_all_registrations()
    except Exception as e:
        print("Error while reading registrations:", traceback.format_exc())
        regs = []
        messages.error(request, "Could not fetch Google Sheet data.")

    cache = UpdateCache.objects.order_by("-updated_at").all()

    return render(
        request,
        "tracker/dashboard.html",
        {"registrations": regs, "cache": cache},
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

    return render(
        request,
        "tracker/history.html",
        {
            "cache": cache,
            "project_names": project_names,
        },
    )
