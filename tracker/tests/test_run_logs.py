"""
Tests for the run log: each user sees their own manual runs plus the all-users
runs, counted for their projects only, within a one-week retention window.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.management.commands.run_daily_check import Command
from tracker.models import (
    DailyCheckRun,
    Library,
    NotificationRecord,
    Project,
    StackComponent,
    UserPreference,
)

User = get_user_model()


def _user_with_project(username):
    user = User.objects.create_user(username=username, password="pass12345")
    project = Project.objects.create(
        owner=user,
        project_name=f"{username} project",
        developer_names="Dev",
        developer_emails=f"{username}@example.com",
    )
    return user, project


@pytest.fixture
def alice(db):
    return _user_with_project("alice")[0]


@pytest.fixture
def bob(db):
    return _user_with_project("bob")[0]


def _manual_run(user, **fields):
    return DailyCheckRun.objects.create(
        **{"triggered_by": user, "scope": "owner", "scope_owner": user, "status": "success", **fields}
    )


def _scheduled_run(**fields):
    return DailyCheckRun.objects.create(**{"scope": "global", "status": "success", **fields})


def _backdate(run, **delta):
    """created_at is auto_now_add, so move it with a queryset update."""
    DailyCheckRun.objects.filter(pk=run.pk).update(created_at=timezone.now() - timedelta(**delta))
    run.refresh_from_db()
    return run


# --- who sees what --------------------------------------------------------


@pytest.mark.django_db
def test_run_logs_require_login(client):
    response = client.get(reverse("run_logs"))
    assert response.status_code == 302
    assert reverse("login") in response["Location"]


@pytest.mark.django_db
def test_user_sees_own_manual_runs_and_all_users_runs(client, alice, bob):
    own = _manual_run(alice)
    _manual_run(bob)
    scheduled = _scheduled_run()

    client.force_login(alice)
    response = client.get(reverse("run_logs"))

    assert response.status_code == 200
    assert {run.id for run in response.context["runs"]} == {own.id, scheduled.id}


@pytest.mark.django_db
def test_all_users_run_shows_only_the_users_own_figures(client, alice, bob):
    _scheduled_run(
        projects_scanned=40,
        emails_sent=25,
        summary={"owners": {str(alice.pk): {"projects": 1, "libraries": 3, "emails_sent": 1, "emails_failed": 0}}},
    )

    client.force_login(alice)
    assert client.get(reverse("run_logs")).context["runs"][0].figures == {
        "projects": 1, "libraries": 3, "emails_sent": 1, "emails_failed": 0,
    }

    # A user the run recorded nothing for had nothing checked, not unknown figures.
    client.force_login(bob)
    assert client.get(reverse("run_logs")).context["runs"][0].figures == {
        "projects": 0, "libraries": 0, "emails_sent": 0, "emails_failed": 0,
    }


@pytest.mark.django_db
def test_all_users_run_without_recorded_figures_hides_the_totals(client, alice):
    _scheduled_run(projects_scanned=40, emails_sent=25)

    client.force_login(alice)
    response = client.get(reverse("run_logs"))

    assert response.context["runs"][0].figures is None


@pytest.mark.django_db
def test_trigger_filter(client, alice):
    manual = _manual_run(alice)
    scheduled = _scheduled_run()
    client.force_login(alice)

    scheduled_only = client.get(reverse("run_logs"), {"trigger": "scheduled"}).context["runs"]
    manual_only = client.get(reverse("run_logs"), {"trigger": "manual"}).context["runs"]

    assert [run.id for run in scheduled_only] == [scheduled.id]
    assert [run.id for run in manual_only] == [manual.id]


@pytest.mark.django_db
def test_dashboard_uses_the_same_visibility_and_links_to_run_logs(client, alice, bob):
    bob.is_staff = True
    bob.save()
    _manual_run(alice)
    scheduled = _scheduled_run()

    client.force_login(bob)
    response = client.get(reverse("dashboard"))

    assert [run.id for run in response.context["recent_daily_check_runs"]] == [scheduled.id]
    assert reverse("run_logs") in response.content.decode()


@pytest.mark.django_db
def test_settings_page_links_to_run_logs(client, alice):
    client.force_login(alice)
    response = client.get(reverse("settings"))
    assert reverse("run_logs") in response.content.decode()


# --- retention ------------------------------------------------------------


@pytest.mark.django_db
def test_runs_older_than_a_week_are_hidden(client, alice):
    _backdate(_manual_run(alice), days=8)
    recent = _backdate(_manual_run(alice), days=6)

    client.force_login(alice)
    response = client.get(reverse("run_logs"))

    assert [run.id for run in response.context["runs"]] == [recent.id]


@pytest.mark.django_db
@override_settings(CRON_SECRET="cron-test-secret")
def test_scheduled_run_deletes_runs_older_than_a_week(client, alice):
    old = _backdate(_manual_run(alice), days=8)
    recent = _backdate(_manual_run(alice), days=6)
    record = NotificationRecord.objects.create(daily_check_run=old, library="django", success=True)

    def mark_run_success(*args, **kwargs):
        DailyCheckRun.objects.filter(pk=kwargs["manual_run_id"]).update(status="success")

    with patch("tracker.views.call_command", side_effect=mark_run_success):
        response = client.get(
            reverse("run_scheduled_daily_check"),
            HTTP_AUTHORIZATION="Bearer cron-test-secret",
        )

    assert response.status_code == 200
    assert not DailyCheckRun.objects.filter(pk=old.pk).exists()
    assert DailyCheckRun.objects.filter(pk=recent.pk).exists()
    # Delivery history survives; only its link to the deleted run is cleared.
    record.refresh_from_db()
    assert record.daily_check_run is None


# --- recording per-owner figures ------------------------------------------


@pytest.mark.django_db
def test_all_users_run_records_figures_per_owner():
    alice, alice_project = _user_with_project("alice")
    bob, bob_project = _user_with_project("bob")
    library = Library.objects.create(name="django", key="django")
    for project in (alice_project, bob_project):
        StackComponent.objects.create(
            project=project, category="library", key="library", name="django", version="5.0", library_ref=library
        )
    run = _scheduled_run(status="running")
    NotificationRecord.objects.create(daily_check_run=run, project=alice_project, success=True)
    NotificationRecord.objects.create(daily_check_run=run, project=bob_project, success=False)

    command = Command()
    command.daily_check_run = run
    command.scope_owner = None
    command.run_summary = {}
    command.step_timings = {}
    command._mark_run_finished(status="success", duration=1.0)

    run.refresh_from_db()
    assert run.summary["check_mode"] == UserPreference.QUICK
    assert run.summary["owners"] == {
        str(alice.pk): {"projects": 1, "libraries": 1, "emails_sent": 1, "emails_failed": 0},
        str(bob.pk): {"projects": 1, "libraries": 1, "emails_sent": 0, "emails_failed": 1},
    }


# --- cooldown and missed runs ---------------------------------------------


@pytest.mark.django_db
def test_manual_runs_are_limited_to_one_every_ten_minutes(client, alice):
    UserPreference.objects.create(user=alice, check_mode=UserPreference.QUICK)
    previous = _backdate(_manual_run(alice), minutes=9)
    client.force_login(alice)

    with patch("tracker.views.call_command") as command:
        response = client.post(reverse("run_daily_check_now"), {"scope": "owner"})
    command.assert_not_called()
    assert "one run every 10 minutes" in " ".join(str(m) for m in get_messages(response.wsgi_request))

    _backdate(previous, minutes=11)
    with patch("tracker.views.call_command") as command:
        client.post(reverse("run_daily_check_now"), {"scope": "owner"})
    command.assert_called_once()


@pytest.mark.django_db
def test_scheduled_run_missed():
    due = datetime(2026, 9, 15, 5, 30, tzinfo=dt_timezone.utc)

    assert DailyCheckRun.next_scheduled_at(due - timedelta(minutes=1)) == due
    assert DailyCheckRun.next_scheduled_at(due) == due + timedelta(days=1)
    # Still inside the hour a cron may fire in.
    assert DailyCheckRun.scheduled_run_missed(now=due + timedelta(minutes=20)) is False
    assert DailyCheckRun.scheduled_run_missed(now=due + timedelta(hours=2)) is True

    # An admin's manual global run is not the scheduled run.
    admin = User.objects.create_user(username="admin", password="pass12345", is_staff=True)
    manual = DailyCheckRun.objects.create(scope="global", triggered_by=admin, status="success")
    DailyCheckRun.objects.filter(pk=manual.pk).update(created_at=due - timedelta(minutes=20))
    assert DailyCheckRun.scheduled_run_missed(now=due + timedelta(hours=2)) is True

    scheduled = _scheduled_run()
    DailyCheckRun.objects.filter(pk=scheduled.pk).update(created_at=due - timedelta(minutes=20))
    assert DailyCheckRun.scheduled_run_missed(now=due + timedelta(hours=2)) is False
