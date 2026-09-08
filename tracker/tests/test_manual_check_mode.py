"""
Tests for manual checks: they now run inline (so they work on serverless), they
report their outcome once, and they honour a per-user check-depth preference.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse

from tracker.models import DailyCheckRun, Project, UserPreference

User = get_user_model()


@pytest.fixture
def owner(db):
    user = User.objects.create_user(username="owner", password="pass12345")
    Project.objects.create(
        owner=user,
        project_name="Owned Project",
        developer_names="Dev",
        developer_emails="dev@example.com",
    )
    return user


def _succeed(*args, **kwargs):
    """Stand-in for the management command that marks the run successful."""
    run = DailyCheckRun.objects.get(pk=kwargs["manual_run_id"])
    run.status = "success"
    run.duration_seconds = 12.0
    run.projects_scanned = 1
    run.libraries_checked = 4
    run.emails_sent = 1
    run.save()


def _messages(response_wsgi_request):
    return [str(m) for m in get_messages(response_wsgi_request)]


# --- running inline -------------------------------------------------------


@pytest.mark.django_db
@override_settings(IS_VERCEL=True)
def test_manual_check_runs_on_vercel(client, owner):
    """
    Regression: manual runs used to be refused in production.

    They were disabled because the old implementation used a background thread,
    which a serverless host kills as soon as the response is returned.
    """
    client.force_login(owner)
    UserPreference.objects.create(user=owner, check_mode=UserPreference.QUICK)

    with patch("tracker.views.call_command", side_effect=_succeed) as command:
        response = client.post(reverse("run_daily_check_now"), {"scope": "owner"})

    assert response.status_code == 302
    command.assert_called_once()
    assert DailyCheckRun.objects.get().status == "success"


@pytest.mark.django_db
def test_completed_run_reports_once_as_a_message(client, owner):
    client.force_login(owner)
    UserPreference.objects.create(user=owner, check_mode=UserPreference.QUICK)

    with patch("tracker.views.call_command", side_effect=_succeed):
        response = client.post(reverse("run_daily_check_now"), {"scope": "owner"})

    text = " ".join(_messages(response.wsgi_request))
    assert "completed in 12s" in text
    assert "1 project scanned" in text


@pytest.mark.django_db
def test_dashboard_does_not_repeat_the_result(client, owner):
    """
    Regression: the result banner was rendered from the newest run on every
    dashboard load, so it reappeared on every later visit.
    """
    client.force_login(owner)
    UserPreference.objects.create(user=owner, check_mode=UserPreference.QUICK)

    with patch("tracker.views.call_command", side_effect=_succeed):
        client.post(reverse("run_daily_check_now"), {"scope": "owner"}, follow=True)

    # Navigate away, then back.
    client.get(reverse("projects"))
    response = client.get(reverse("dashboard"))

    assert _messages(response.wsgi_request) == []
    assert b"Manual check completed" not in response.content


@pytest.mark.django_db
def test_failed_run_is_reported_as_an_error(client, owner):
    client.force_login(owner)
    UserPreference.objects.create(user=owner, check_mode=UserPreference.QUICK)

    with patch("tracker.views.call_command", side_effect=RuntimeError("registry down")):
        response = client.post(reverse("run_daily_check_now"), {"scope": "owner"})

    text = " ".join(_messages(response.wsgi_request))
    assert "failed" in text.lower()
    assert "registry down" in text
    assert DailyCheckRun.objects.get().status == "failed"


# --- check-mode preference ------------------------------------------------


@pytest.mark.django_db
def test_new_user_is_asked_to_choose(client, owner):
    client.force_login(owner)
    response = client.get(reverse("dashboard"))

    assert response.context["needs_check_mode_choice"] is True
    assert b'data-needs-choice="true"' in response.content


@pytest.mark.django_db
def test_choosing_a_mode_saves_it_and_stops_the_prompt(client, owner):
    client.force_login(owner)

    with patch("tracker.views.call_command", side_effect=_succeed) as command:
        client.post(reverse("run_daily_check_now"), {"scope": "owner", "check_mode": "thorough"})

    assert UserPreference.for_user(owner).check_mode == "thorough"
    assert command.call_args.kwargs["force"] is True

    response = client.get(reverse("dashboard"))
    assert response.context["needs_check_mode_choice"] is False
    assert b'data-needs-choice="false"' in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mode,expected_force",
    [("thorough", True), ("quick", False)],
)
def test_saved_mode_drives_the_run(client, owner, mode, expected_force):
    client.force_login(owner)
    UserPreference.objects.create(user=owner, check_mode=mode)

    with patch("tracker.views.call_command", side_effect=_succeed) as command:
        client.post(reverse("run_daily_check_now"), {"scope": "owner"})

    assert command.call_args.kwargs["force"] is expected_force


@pytest.mark.django_db
def test_post_without_a_mode_runs_quick_and_keeps_asking(client, owner):
    """A form submitted with JavaScript off must not answer the question."""
    client.force_login(owner)

    with patch("tracker.views.call_command", side_effect=_succeed) as command:
        client.post(reverse("run_daily_check_now"), {"scope": "owner"})

    assert command.call_args.kwargs["force"] is False
    assert UserPreference.for_user(owner).check_mode == ""
    assert client.get(reverse("dashboard")).context["needs_check_mode_choice"] is True


@pytest.mark.django_db
def test_admin_global_run_uses_the_same_preference(client):
    admin = User.objects.create_superuser(username="admin", password="pass12345")
    client.force_login(admin)
    UserPreference.objects.create(user=admin, check_mode=UserPreference.THOROUGH)

    with patch("tracker.views.call_command", side_effect=_succeed) as command:
        client.post(reverse("run_daily_check_now"), {"scope": "global"})

    assert command.call_args.kwargs["global_run"] is True
    assert command.call_args.kwargs["force"] is True


# --- settings page --------------------------------------------------------


@pytest.mark.django_db
def test_settings_page_updates_the_mode(client, owner):
    client.force_login(owner)
    UserPreference.objects.create(user=owner, check_mode=UserPreference.QUICK)

    response = client.post(
        reverse("settings"), {"form": "check_mode", "check_mode": "thorough"}
    )

    assert response.status_code == 302
    assert UserPreference.for_user(owner).check_mode == "thorough"


@pytest.mark.django_db
def test_settings_page_rejects_an_unknown_mode(client, owner):
    client.force_login(owner)
    UserPreference.objects.create(user=owner, check_mode=UserPreference.QUICK)

    client.post(reverse("settings"), {"form": "check_mode", "check_mode": "sideways"})

    assert UserPreference.for_user(owner).check_mode == "quick"


@pytest.mark.django_db
def test_settings_page_works_without_projects(client):
    """The check-depth form sits outside the projects block for this reason."""
    user = User.objects.create_user(username="projectless", password="pass12345")
    client.force_login(user)

    response = client.post(
        reverse("settings"), {"form": "check_mode", "check_mode": "quick"}, follow=True
    )

    assert response.status_code == 200
    assert UserPreference.for_user(user).check_mode == "quick"
