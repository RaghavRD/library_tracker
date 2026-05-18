
import json
from datetime import datetime
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from tracker.models import Project, StackComponent

VALID_NOTIFICATION_TYPES = {"both", "major", "minor", "future"}
NOTIFICATION_ORDER = ("major", "minor", "future")
STANDARD_DATE_OUTPUT = "%Y-%m-%d"

class ProjectService:
    """
    Service layer for Project-related business logic.
    Refactored from views.py to improve separation of concerns.
    """

    @staticmethod
    def normalize_notification_types(selected: list[str]) -> set[str]:
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

    @staticmethod
    def validate_emails(csv: str):
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

    @staticmethod
    def format_release_date(raw: str | None) -> str:
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

    @staticmethod
    def normalize_component_key(category: str, key: str | None) -> str:
        candidate = (key or category or "dependency").strip().lower() or "dependency"
        if "language" in candidate:
            return "language"
        return candidate

    @staticmethod
    def parse_stack_payload(payload: dict) -> list[dict]:
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
            key = ProjectService.normalize_component_key(category, component.get("key"))
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

    @staticmethod
    def build_registration_payload(request):
        """
        Extracts and validates registration form data from POST requests.
        Returns a tuple of (payload_dict, error_message).
        """
        project_name = request.POST.get("project_name", "").strip()
        developer_names = request.POST.get("developer_names", "").strip()
        developer_emails_raw = request.POST.get("developer_emails", "").strip()
        notification_selections = request.POST.getlist("notification_types")
        normalized_preferences = ProjectService.normalize_notification_types(notification_selections or ["major", "minor"])
        notification_type = ", ".join([option for option in NOTIFICATION_ORDER if option in normalized_preferences])

        if not all([project_name, developer_names, developer_emails_raw]):
            return None, "Please complete the project and team fields before submitting."

        emails = ProjectService.validate_emails(developer_emails_raw)
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

    @staticmethod
    def save_project_from_payload(payload: dict, *, instance: Project | None = None) -> Project:
        stack = ProjectService.parse_stack_payload(payload)
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

    @staticmethod
    def serialize_project(project: Project) -> dict:
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
