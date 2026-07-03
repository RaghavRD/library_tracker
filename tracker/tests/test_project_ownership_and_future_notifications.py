import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse

from tracker.models import (
    FutureUpdateCache,
    Library,
    Project,
    ProjectFutureNotification,
    StackComponent,
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
        assert send_mock.call_count == 1

        service = NotificationService(mailtrap_key="key", sender_email="noreply@example.com")
        service.notify_all_projects()
        assert send_mock.call_count == 1
