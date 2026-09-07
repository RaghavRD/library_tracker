"""
Tests for daily check run recovery and the wall-clock time budget.

A run only leaves an active status when the command marks it finished, so a
process killed mid-run (a Vercel function hitting its duration cap) used to
leave the row active forever and lock out every later run.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import DailyCheckRun


def _backdate(run, minutes):
    """created_at is auto_now_add, so move it with a queryset update."""
    DailyCheckRun.objects.filter(pk=run.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes)
    )
    run.refresh_from_db()
    return run


@pytest.mark.django_db
def test_reap_stale_fails_abandoned_runs():
    stale = _backdate(DailyCheckRun.objects.create(scope="global", status="running"), 30)

    assert DailyCheckRun.reap_stale() == 1

    stale.refresh_from_db()
    assert stale.status == "failed"
    assert stale.finished_at is not None
    assert "abandoned" in stale.error_message


@pytest.mark.django_db
def test_reap_stale_leaves_recent_and_finished_runs_alone():
    recent = DailyCheckRun.objects.create(scope="global", status="running")
    finished = _backdate(DailyCheckRun.objects.create(scope="global", status="success"), 60)

    assert DailyCheckRun.reap_stale() == 0

    recent.refresh_from_db()
    finished.refresh_from_db()
    assert recent.status == "running"
    assert finished.status == "success"


@pytest.mark.django_db
@override_settings(CRON_SECRET="cron-test-secret")
def test_scheduled_check_is_not_locked_out_by_an_abandoned_run(client):
    """Regression: a killed run must not block every future cron invocation."""
    stale = _backdate(DailyCheckRun.objects.create(scope="global", status="running"), 30)

    def mark_run_success(*args, **kwargs):
        run = DailyCheckRun.objects.get(pk=kwargs["manual_run_id"])
        run.status = "success"
        run.save(update_fields=["status", "updated_at"])

    with patch("tracker.views.call_command", side_effect=mark_run_success):
        response = client.get(
            reverse("run_scheduled_daily_check"),
            HTTP_AUTHORIZATION="Bearer cron-test-secret",
        )

    stale.refresh_from_db()
    assert stale.status == "failed"
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert DailyCheckRun.objects.count() == 2


@pytest.mark.django_db
def test_run_stops_at_the_time_budget_and_records_partial():
    run = DailyCheckRun.objects.create(scope="global", status="queued")
    # monotonic() is read once to arm the budget, then once per budget check.
    ticks = iter([0.0, 100.0])

    with patch(
        "tracker.management.commands.run_daily_check.time.monotonic",
        side_effect=lambda: next(ticks),
    ):
        call_command("run_daily_check", global_run=True, manual_run_id=run.id, budget_seconds=50)

    run.refresh_from_db()
    assert run.status == "partial"
    assert run.summary["stopped_before"] == "sync"
    assert run.summary["timings"] == {}
    assert "budget" in run.error_message.lower()


@pytest.mark.django_db
def test_completed_run_records_per_step_timings():
    run = DailyCheckRun.objects.create(scope="global", status="queued")

    call_command("run_daily_check", global_run=True, manual_run_id=run.id, budget_seconds=0)

    run.refresh_from_db()
    assert run.status == "success"
    assert set(run.summary["timings"]) == {
        "sync",
        "fetch",
        "future",
        "security",
        "notifications",
        "snapshots",
    }
    assert "stopped_before" not in run.summary
