import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from tracker.models import (
    DailyCheckRun,
    FutureUpdateCache,
    Library,
    Project,
    ProjectFutureNotification,
    StackComponent,
    UpdateCache,
    UpdateEvent,
)
from tracker.services.future_update_service import FutureUpdateService
from tracker.services.notification_service import NotificationService


User = get_user_model()


@pytest.mark.django_db
def test_projects_page_only_shows_current_users_projects(client):
    user_a = User.objects.create_user(username="owner-a", password="pass12345")
    user_b = User.objects.create_user(username="owner-b", password="pass12345")
    Project.objects.create(
        owner=user_a,
        project_name="Visible Project",
        developer_names="Dev A",
        developer_emails="a@example.com",
    )
    Project.objects.create(
        owner=user_b,
        project_name="Hidden Project",
        developer_names="Dev B",
        developer_emails="b@example.com",
    )

    client.force_login(user_a)
    response = client.get(reverse("projects"))

    content = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "Visible Project" in content
    assert "Hidden Project" not in content


@pytest.mark.django_db
def test_manual_daily_check_button_creates_owner_scoped_run(client):
    user = User.objects.create_user(username="manual-owner", password="pass12345")
    other = User.objects.create_user(username="other-owner", password="pass12345")
    Project.objects.create(
        owner=user,
        project_name="Visible Manual Project",
        developer_names="Dev",
        developer_emails="dev@example.com",
    )
    Project.objects.create(
        owner=other,
        project_name="Other Project",
        developer_names="Dev",
        developer_emails="other@example.com",
    )

    class FakeThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def start(self):
            return None

    client.force_login(user)
    with patch("tracker.views.threading.Thread", FakeThread):
        response = client.post(reverse("run_daily_check_now"), {"scope": "owner"})

    run = DailyCheckRun.objects.get()
    assert response.status_code == 302
    assert run.triggered_by == user
    assert run.scope_owner == user
    assert run.scope == "owner"
    assert run.status == "queued"


@pytest.mark.django_db
def test_manual_daily_check_blocks_active_run(client):
    user = User.objects.create_user(username="active-owner", password="pass12345")
    DailyCheckRun.objects.create(
        triggered_by=user,
        scope_owner=user,
        scope="owner",
        status="running",
    )

    client.force_login(user)
    response = client.post(reverse("run_daily_check_now"), {"scope": "owner"})

    assert response.status_code == 302
    assert DailyCheckRun.objects.count() == 1


@pytest.mark.django_db
def test_manual_daily_check_status_endpoint_returns_formatted_duration(client):
    user = User.objects.create_user(username="status-owner", password="pass12345")
    run = DailyCheckRun.objects.create(
        triggered_by=user,
        scope_owner=user,
        scope="owner",
        status="success",
        duration_seconds=392.2,
        projects_scanned=3,
        libraries_checked=54,
        emails_sent=2,
    )

    client.force_login(user)
    response = client.get(reverse("run_daily_check_status"), {"run_id": run.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["duration"] == "6m 32s"
    assert payload["projects_scanned"] == 3
    assert payload["libraries_checked"] == 54


@pytest.mark.django_db
def test_owner_scoped_daily_check_command_passes_owner_to_services():
    user = User.objects.create_user(username="command-owner", password="pass12345")
    project = Project.objects.create(
        owner=user,
        project_name="Command Project",
        developer_names="Dev",
        developer_emails="dev@example.com",
    )
    library = Library.objects.create(name="requests", key="requests", component_type="library")
    StackComponent.objects.create(
        project=project,
        library_ref=library,
        category="Library",
        key="library",
        name="requests",
        version="1.0.0",
    )
    run = DailyCheckRun.objects.create(
        triggered_by=user,
        scope_owner=user,
        scope="owner",
        status="queued",
    )

    with patch.dict("os.environ", {"MAILTRAP_API_KEY": "key", "MAILTRAP_FROM_EMAIL": "noreply@example.com"}), \
        patch("tracker.services.library_sync_service.LibrarySyncService.sync_all_libraries", return_value={"synced_count": 0, "created_count": 0}) as sync_mock, \
        patch("tracker.services.version_fetch_service.VersionFetchService.fetch_all_libraries", return_value={"checked_count": 1, "updated_count": 0, "skipped_count": 1, "error_count": 0}) as fetch_mock, \
        patch("tracker.services.future_update_service.FutureUpdateService.check_future_versions", return_value=None), \
        patch("tracker.services.security_vulnerability_service.SecurityVulnerabilityService.scan_all_projects", return_value={"projects_scanned": 1, "scanned_count": 1, "finding_count": 0, "resolved_count": 0, "error_count": 0}) as security_mock, \
        patch("tracker.services.notification_service.NotificationService.notify_all_projects", return_value={"projects_checked": 1, "sent_count": 0, "skipped_count": 1, "error_count": 0}) as notify_mock, \
        patch("tracker.services.dashboard_metrics_service.DashboardMetricsService.record_all_owner_snapshots", return_value=1) as snapshot_mock:
        call_command("run_daily_check", owner_id=user.id, manual_run_id=run.id)

    run.refresh_from_db()
    assert sync_mock.call_args.kwargs["owner"] == user
    assert fetch_mock.call_args.kwargs["owner"] == user
    assert security_mock.call_args.kwargs["owner"] == user
    assert notify_mock.call_args.kwargs["owner"] == user
    assert snapshot_mock.call_args.kwargs["owner"] == user
    assert run.status == "success"
    assert run.projects_scanned == 1
    assert run.libraries_checked == 1


@pytest.mark.django_db
def test_future_detection_does_not_mark_notification_sent_before_email():
    service = FutureUpdateService()

    payload = service._handle_future_update(
        library_name="pandas",
        version="3.0.0",
        confidence=85,
        expected_date="",
        summary="Upcoming release",
        source="https://example.com/roadmap",
        prerelease_type="roadmap",
        detection_method="official_website",
    )

    future_update = FutureUpdateCache.objects.get(library="pandas", version="3.0.0")
    assert payload["future_update_id"] == future_update.id
    assert future_update.notification_sent is False
    assert future_update.notification_sent_at is None


@pytest.mark.django_db
def test_low_confidence_future_detection_is_stored_for_project_threshold_filtering():
    service = FutureUpdateService()

    payload = service._handle_future_update(
        library_name="django",
        version="6.0.0",
        confidence=45,
        expected_date="",
        summary="Early roadmap signal",
        source="https://example.com/roadmap",
        prerelease_type="roadmap",
        detection_method="official_website",
    )

    future_update = FutureUpdateCache.objects.get(library="django", version="6.0.0")
    assert payload is not None
    assert payload["confidence"] == 45
    assert future_update.confidence == 45
    assert future_update.notification_sent is False


@pytest.mark.django_db
def test_future_notification_success_is_tracked_per_project():
    user = User.objects.create_user(username="owner", password="pass12345")
    project = Project.objects.create(
        owner=user,
        project_name="Tracked Project",
        developer_names="Dev",
        developer_emails="dev@example.com",
        notification_type="future",
        min_confidence_threshold=50,
    )
    library = Library.objects.create(
        name="pandas",
        key="pandas",
        component_type="library",
    )
    StackComponent.objects.create(
        project=project,
        library_ref=library,
        category="Library",
        key="library",
        name="pandas",
        version="2.2.0",
    )
    future_update = FutureUpdateCache.objects.create(
        library="pandas",
        version="3.0.0",
        confidence=85,
        status="detected",
        features="Upcoming release",
        source="https://example.com/roadmap",
    )
    with patch(
        "tracker.services.notification_service.send_update_email",
        return_value={"success": True, "status_text": "sent", "http_status": 200},
    ) as send_mock:
        service = NotificationService(mailtrap_key="key", sender_email="noreply@example.com")
        service.notify_all_projects()

        project_delivery = ProjectFutureNotification.objects.get(
            project=project,
            future_update=future_update,
        )
        future_update.refresh_from_db()
        assert project_delivery.success is True
        assert project_delivery.sent_at is not None
        assert future_update.notification_sent is True
        assert UpdateEvent.objects.filter(
            project=project,
            library="pandas",
            version="3.0.0",
            category="future",
            notification_success=True,
        ).exists()
        assert send_mock.call_count == 1

        service = NotificationService(mailtrap_key="key", sender_email="noreply@example.com")
        service.notify_all_projects()
        assert send_mock.call_count == 1


@pytest.mark.django_db
def test_update_events_preserve_multiple_versions_while_cache_tracks_latest():
    user = User.objects.create_user(username="history-owner", password="pass12345")
    project = Project.objects.create(
        owner=user,
        project_name="History Project",
        developer_names="Dev",
        developer_emails="dev@example.com",
        notification_type="major",
    )
    library = Library.objects.create(
        name="requests",
        key="requests",
        component_type="library",
        latest_version="2.0.0",
    )
    StackComponent.objects.create(
        project=project,
        library_ref=library,
        category="Library",
        key="library",
        name="requests",
        version="1.0.0",
    )

    with patch(
        "tracker.services.notification_service.send_update_email",
        return_value={"success": True, "status_text": "sent", "http_status": 200},
    ):
        service = NotificationService(mailtrap_key="key", sender_email="noreply@example.com")
        service.notify_all_projects()

        library.latest_version = "3.0.0"
        library.save(update_fields=["latest_version"])
        service = NotificationService(mailtrap_key="key", sender_email="noreply@example.com")
        service.notify_all_projects()

    cache = UpdateCache.objects.get(project=project, library="requests")
    events = UpdateEvent.objects.filter(project=project, library="requests").order_by("version")

    assert cache.version == "3.0.0"
    assert list(events.values_list("version", flat=True)) == ["2.0.0", "3.0.0"]
    assert all(event.from_version == "1.0.0" for event in events)
