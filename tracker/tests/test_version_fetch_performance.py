"""
Tests for the concurrent, freshness-filtered registry fetch path.

The fetch step used to be the whole time budget: one library at a time with a
fixed sleep between each. These cover the properties that replaced it.
"""

import threading
import time
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from tracker.models import Library, Project, StackComponent
from tracker.services.version_fetch_service import VersionFetchService
from tracker.utils.registry_adapters import VersionInfo


def _make_library(name, *, latest_version="1.0.0", last_checked_at=None):
    """Create a Library with a component linked to it, so it is 'in use'."""
    library = Library.objects.create(
        name=name,
        key=name.lower(),
        latest_version=latest_version,
        registry_type="pypi",
        last_checked_at=last_checked_at,
    )
    project, _ = Project.objects.get_or_create(
        project_name="Fetch Project",
        defaults={"developer_names": "Dev", "developer_emails": "dev@example.com"},
    )
    StackComponent.objects.create(
        project=project,
        category="Package",
        key="library",
        name=name,
        version=latest_version,
        library_ref=library,
    )
    return library


def _version_info(version):
    return VersionInfo(
        version=version,
        release_date=date(2026, 1, 1),
        homepage_url="https://example.test",
        summary="",
        source_url="https://example.test",
        trust_level=100,
    )


def _service(detect):
    """Build a service whose network layer is the given detect callable."""
    service = VersionFetchService(use_official_apis=True)
    service.helper = MagicMock()
    service.helper.detect.side_effect = detect
    service.helper.apply.side_effect = lambda library, info, **kw: library
    return service


@pytest.mark.django_db
def test_fresh_libraries_are_skipped():
    _make_library("fresh", last_checked_at=timezone.now() - timedelta(hours=1))
    _make_library("stale", last_checked_at=timezone.now() - timedelta(hours=48))
    _make_library("never")

    checked = []
    service = _service(lambda name, **kw: checked.append(name) or None)

    with override_settings(LIBTRACK_FRESHNESS_HOURS=20):
        summary = service.fetch_all_libraries()

    assert sorted(checked) == ["never", "stale"]
    assert summary["skipped_fresh_count"] == 1
    assert summary["checked_count"] == 2


@pytest.mark.django_db
def test_force_ignores_the_freshness_window():
    _make_library("fresh", last_checked_at=timezone.now() - timedelta(hours=1))

    checked = []
    service = _service(lambda name, **kw: checked.append(name) or None)

    with override_settings(LIBTRACK_FRESHNESS_HOURS=20):
        summary = service.fetch_all_libraries(force=True)

    assert checked == ["fresh"]
    assert summary["skipped_fresh_count"] == 0


@pytest.mark.django_db
def test_unchanged_library_still_records_last_checked_at():
    """Otherwise an up-to-date library is re-fetched on every single run."""
    library = _make_library("stable", last_checked_at=None)
    service = _service(lambda name, **kw: None)

    service.fetch_all_libraries()

    library.refresh_from_db()
    assert library.last_checked_at is not None


@pytest.mark.django_db
def test_detection_runs_concurrently():
    for index in range(8):
        _make_library(f"lib-{index}")

    in_flight = []
    peak = []
    lock = threading.Lock()

    def detect(name, **kwargs):
        with lock:
            in_flight.append(name)
            peak.append(len(in_flight))
        time.sleep(0.05)
        with lock:
            in_flight.remove(name)
        return None

    service = _service(detect)
    with override_settings(LIBTRACK_FETCH_MAX_WORKERS=4, LIBTRACK_FRESHNESS_HOURS=0):
        service.fetch_all_libraries()

    assert max(peak) > 1, "detection should overlap across workers"
    assert max(peak) <= 4, "concurrency must respect LIBTRACK_FETCH_MAX_WORKERS"


@pytest.mark.django_db
def test_database_writes_stay_on_the_main_thread():
    """Workers must not touch the ORM: Django connections are per-thread."""
    _make_library("threaded")
    main_thread = threading.current_thread().ident
    apply_threads = []

    service = VersionFetchService(use_official_apis=True)
    service.helper = MagicMock()
    service.helper.detect.side_effect = lambda name, **kw: _version_info("2.0.0")
    service.helper.apply.side_effect = lambda library, info, **kw: apply_threads.append(
        threading.current_thread().ident
    )

    with override_settings(LIBTRACK_FETCH_MAX_WORKERS=4):
        service.fetch_all_libraries()

    assert apply_threads == [main_thread]


@pytest.mark.django_db
def test_detection_failure_is_counted_not_raised():
    _make_library("broken")

    def detect(name, **kwargs):
        raise RuntimeError("registry exploded")

    service = _service(detect)
    summary = service.fetch_all_libraries()

    assert summary["error_count"] == 1
    assert summary["updated_count"] == 0
    service.helper.record_failure.assert_called_once()


@pytest.mark.django_db
def test_fetch_stops_at_the_deadline():
    for index in range(5):
        _make_library(f"slow-{index}")

    service = _service(lambda name, **kw: None)
    summary = service.fetch_all_libraries(deadline=time.monotonic() - 1)

    assert summary["unchecked_count"] == 5
    assert summary["checked_count"] == 0
