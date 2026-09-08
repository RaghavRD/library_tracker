"""
Tests for the future/pre-release step's cost controls.

This step used to make between two and eight HTTP calls per library, for every
library, every night. These cover the four things that changed.
"""

import threading
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from tracker.models import Library, Project, StackComponent
from tracker.services.future_update_service import FutureUpdateService
from tracker.utils.github_fetcher import GitHubFetcher
from tracker.utils.registry_adapters.pypi import PyPIRegistry


def _make_library(name, *, last_future_check_at=None):
    library = Library.objects.create(
        name=name,
        key=name.lower(),
        latest_version="1.0.0",
        registry_type="pypi",
        last_future_check_at=last_future_check_at,
    )
    project, _ = Project.objects.get_or_create(
        project_name="Future Project",
        defaults={"developer_names": "Dev", "developer_emails": "dev@example.com"},
    )
    StackComponent.objects.create(
        project=project,
        category="Package",
        key="library",
        name=name,
        version="1.0.0",
        library_ref=library,
    )
    return library


def _service(detect):
    service = FutureUpdateService()
    service.detector = MagicMock()
    service.detector.detect_future_versions.side_effect = detect
    return service


def _in_use():
    return Library.objects.filter(linked_components__isnull=False).distinct()


# --- Change 1: freshness window ------------------------------------------


@pytest.mark.django_db
def test_recently_checked_libraries_are_skipped():
    _make_library("fresh", last_future_check_at=timezone.now() - timedelta(hours=2))
    _make_library("stale", last_future_check_at=timezone.now() - timedelta(hours=200))
    _make_library("never")

    checked = []
    service = _service(lambda name, *a, **kw: checked.append(name) or [])

    with override_settings(LIBTRACK_FUTURE_FRESHNESS_HOURS=72):
        summary = service.check_all_libraries(_in_use())

    assert sorted(checked) == ["never", "stale"]
    assert summary["skipped_fresh_count"] == 1
    assert summary["libraries_checked"] == 2


@pytest.mark.django_db
def test_force_ignores_the_future_freshness_window():
    _make_library("fresh", last_future_check_at=timezone.now() - timedelta(hours=2))

    checked = []
    service = _service(lambda name, *a, **kw: checked.append(name) or [])

    with override_settings(LIBTRACK_FUTURE_FRESHNESS_HOURS=72):
        service.check_all_libraries(_in_use(), force=True)

    assert checked == ["fresh"]


@pytest.mark.django_db
def test_library_with_no_future_version_is_still_stamped():
    """Otherwise it is re-checked every night forever."""
    library = _make_library("quiet")
    service = _service(lambda name, *a, **kw: [])

    service.check_all_libraries(_in_use())

    library.refresh_from_db()
    assert library.last_future_check_at is not None


@pytest.mark.django_db
def test_failed_check_is_not_stamped_so_it_retries_tomorrow():
    library = _make_library("flaky")

    def boom(*args, **kwargs):
        raise RuntimeError("github down")

    service = _service(boom)
    summary = service.check_all_libraries(_in_use())

    library.refresh_from_db()
    assert library.last_future_check_at is None
    assert service.error_count == 1
    assert summary["future_updates_found"] == 0


@pytest.mark.django_db
def test_future_detection_writes_stay_on_the_main_thread():
    for index in range(4):
        _make_library(f"lib-{index}")

    main_thread = threading.current_thread().ident
    detect_threads = set()

    def detect(name, *args, **kwargs):
        detect_threads.add(threading.current_thread().ident)
        return []

    service = _service(detect)
    with override_settings(LIBTRACK_FETCH_MAX_WORKERS=4):
        service.check_all_libraries(_in_use())

    # Detection runs off the main thread; the stamping writes it triggers do not.
    assert detect_threads and main_thread not in detect_threads
    assert Library.objects.filter(last_future_check_at__isnull=False).count() == 4


# --- Change 2: one registry response per package -------------------------


def test_response_cache_deduplicates_identical_gets():
    registry = PyPIRegistry()
    response = MagicMock(status_code=200)

    with patch.object(type(registry), "session", new=MagicMock()) as session:
        session.get.return_value = response

        registry.begin_response_cache()
        try:
            first = registry.get("https://pypi.org/pypi/django/json")
            second = registry.get("https://pypi.org/pypi/django/json")
        finally:
            registry.end_response_cache()

        assert first is second
        assert session.get.call_count == 1

        # Outside the cache window every call goes to the network again.
        registry.get("https://pypi.org/pypi/django/json")
        assert session.get.call_count == 2


def test_response_cache_distinguishes_params():
    registry = PyPIRegistry()

    with patch.object(type(registry), "session", new=MagicMock()) as session:
        session.get.return_value = MagicMock(status_code=200)

        registry.begin_response_cache()
        try:
            registry.get("https://example.test/search", params={"q": "a"})
            registry.get("https://example.test/search", params={"q": "b"})
        finally:
            registry.end_response_cache()

        assert session.get.call_count == 2


def test_response_cache_is_per_thread():
    """A shared adapter must not serve one thread's response to another."""
    registry = PyPIRegistry()
    seen = []

    with patch.object(type(registry), "session", new=MagicMock()) as session:
        session.get.side_effect = lambda *a, **kw: MagicMock(status_code=200)

        def worker():
            registry.begin_response_cache()
            try:
                seen.append(registry.get("https://pypi.org/pypi/x/json"))
            finally:
                registry.end_response_cache()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Each thread had its own cache, so each made its own request.
        assert session.get.call_count == 4
        assert len({id(response) for response in seen}) == 4


# --- Change 4: roadmap lookup costs one call -----------------------------


def test_roadmap_lookup_uses_a_single_listing_call():
    fetcher = GitHubFetcher()
    listing = MagicMock(status_code=200)
    listing.json.return_value = [
        {"type": "file", "name": "README.md"},
        {"type": "file", "name": "Roadmap.md", "html_url": "https://github.test/r", "url": "https://api.test/r"},
    ]
    blob = MagicMock(status_code=200)
    blob.json.return_value = {"content": "IyBSb2FkbWFw"}  # "# Roadmap"

    with patch.object(GitHubFetcher, "get", side_effect=[listing, blob]) as mock_get:
        result = fetcher.detect_roadmap_file("owner", "repo")

    assert result is not None
    assert "Roadmap.md" in result.summary
    # One listing plus one blob fetch, versus four filename guesses before.
    assert mock_get.call_count == 2


def test_missing_roadmap_costs_one_call():
    fetcher = GitHubFetcher()
    listing = MagicMock(status_code=200)
    listing.json.return_value = [{"type": "file", "name": "README.md"}]

    with patch.object(GitHubFetcher, "get", return_value=listing) as mock_get:
        assert fetcher.detect_roadmap_file("owner", "repo") is None

    assert mock_get.call_count == 1


def test_roadmap_match_is_case_insensitive():
    fetcher = GitHubFetcher()
    listing = MagicMock(status_code=200)
    listing.json.return_value = [
        {"type": "file", "name": "ROADMAP.MD", "html_url": "", "url": "https://api.test/r"},
    ]
    blob = MagicMock(status_code=200)
    blob.json.return_value = {"content": ""}

    with patch.object(GitHubFetcher, "get", side_effect=[listing, blob]):
        assert fetcher.detect_roadmap_file("owner", "repo") is not None
