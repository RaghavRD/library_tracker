from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tracker.models import (
    FutureUpdateCache,
    Library,
    Project,
    SecurityVulnerability,
    StackComponent,
)
from tracker.services.notification_service import NotificationService
from tracker.utils.send_mail import send_update_email


User = get_user_model()


def _project_with_package(*, notification_type="major, minor", latest_version="1.0.0"):
    user = User.objects.create_user(username=f"owner-{Project.objects.count()}", password="pass12345")
    project = Project.objects.create(
        owner=user,
        project_name="Digest Project",
        developer_names="Team",
        developer_emails="dev@example.com",
        notification_type=notification_type,
        min_confidence_threshold=50,
    )
    library = Library.objects.create(
        name=f"package-{Library.objects.count()}",
        key=f"package-{Library.objects.count()}",
        component_type="library",
        latest_version=latest_version,
        last_checked_at=timezone.now(),
    )
    component = StackComponent.objects.create(
        project=project,
        library_ref=library,
        category="Library",
        key="library",
        name=library.name,
        version="1.0.0",
    )
    return project, library, component


@pytest.mark.django_db
def test_project_digest_contains_current_future_and_security_state():
    project, library, component = _project_with_package(
        notification_type="major, minor, future",
        latest_version="2.0.0",
    )
    FutureUpdateCache.objects.create(
        library=library.name,
        version="3.0.0-beta.1",
        confidence=85,
        status="confirmed",
        features="Planned runtime and API improvements.",
        source="https://example.com/roadmap",
    )
    SecurityVulnerability.objects.create(
        project=project,
        component=component,
        library=library.name,
        version=component.version,
        ecosystem="PyPI",
        osv_id="OSV-2026-100",
        severity="HIGH",
        summary="A crafted request can bypass validation.",
        source_url="https://osv.dev/vulnerability/OSV-2026-100",
        fixed_versions=["1.0.1"],
        status="active",
        last_seen_at=timezone.now(),
    )

    service = NotificationService(mailtrap_key="key", sender_email="noreply@example.com")
    findings = list(project.security_vulnerabilities.filter(status="active"))
    digest = service._build_project_digest(
        project,
        prefs={"major", "minor", "future"},
        updates=[],
        active_findings=findings,
    )

    package = digest["packages"][0]
    assert package["installed_version"] == "1.0.0"
    assert package["latest_version"] == "2.0.0"
    assert package["future_version"] == "3.0.0-beta.1"
    assert package["security"] == "High"
    assert package["security_findings"][0]["fixed_versions"] == ["1.0.1"]
    assert digest["severity_counts"]["high"] == 1
    assert digest["fixes_available"] == 1


@pytest.mark.django_db
def test_high_security_finding_is_sent_once_by_scheduled_notification_cycle():
    project, library, component = _project_with_package()
    finding = SecurityVulnerability.objects.create(
        project=project,
        component=component,
        library=library.name,
        version=component.version,
        ecosystem="npm",
        osv_id="OSV-2026-200",
        severity="CRITICAL",
        summary="Remote code execution is possible.",
        status="active",
        last_seen_at=timezone.now(),
    )

    with patch(
        "tracker.services.notification_service.send_update_email",
        return_value={"success": True, "status_text": "sent", "http_status": 200},
    ) as send_mock:
        NotificationService(mailtrap_key="key", sender_email="noreply@example.com").notify_all_projects()
        finding.refresh_from_db()

        assert send_mock.call_count == 1
        assert send_mock.call_args.kwargs["category"] == "security"
        assert send_mock.call_args.kwargs["digest"]["active_security_count"] == 1
        assert finding.last_notified_signature
        assert finding.last_notified_at is not None

        NotificationService(mailtrap_key="key", sender_email="noreply@example.com").notify_all_projects()
        assert send_mock.call_count == 1


@pytest.mark.django_db
def test_low_security_finding_does_not_trigger_security_only_email():
    project, library, component = _project_with_package()
    SecurityVulnerability.objects.create(
        project=project,
        component=component,
        library=library.name,
        version=component.version,
        ecosystem="npm",
        osv_id="OSV-2026-300",
        severity="LOW",
        summary="Low impact information disclosure.",
        status="active",
        last_seen_at=timezone.now(),
    )

    with patch("tracker.services.notification_service.send_update_email") as send_mock:
        NotificationService(mailtrap_key="key", sender_email="noreply@example.com").notify_all_projects()

    send_mock.assert_not_called()


def test_email_template_renders_health_future_and_escaped_content(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "True")
    result = send_update_email(
        mailtrap_api_key="key",
        project_name="<script>alert(1)</script>",
        recipients="dev@example.com",
        library="django",
        version="6.0.0",
        category="future",
        summary="Planned security improvements",
        source="javascript:alert(1)",
        updates=[
            {
                "library": "django",
                "from_version": "5.2.0",
                "version": "6.0.0",
                "category": "future",
                "summary": "Planned security improvements",
                "source": "javascript:alert(1)",
                "confidence": 91,
            }
        ],
        future_opt_in=True,
        from_email="noreply@example.com",
    )

    html = result["html_content"]
    assert result["success"] is True
    assert "Project health" in html
    assert "Security health" in html
    assert "Future update summary" in html
    assert "Confidence: 91%" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "javascript:alert(1)" not in html
    assert "CURRENT PACKAGE STATE" in result["text_content"]
