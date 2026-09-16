"""
Tests for email summary cleaning.

Registries and OSV hand us whatever text they have: a PyPI long description is
a whole README with HTML tables, a GitHub release body is markdown full of
badges. Emails escape HTML, so raw text used to reach the reader as literal
"<table><tr><td>".
"""

from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from tracker.models import FutureUpdateCache, Library, LibraryRelease
from tracker.utils import text_summary
from tracker.utils.text_summary import (
    MAX_SUMMARY_CHARS,
    clean_summary,
    looks_unsummarized,
    summarize,
)

README_WITH_HTML = """
<p align="center">
  <img src="https://img.shields.io/badge/build-passing-green" alt="build">
</p>
<h1>Acme Toolkit</h1>
<p>Acme Toolkit speeds up data pipelines.</p>
<table>
  <tr><th>Python</th><th>Status</th></tr>
  <tr><td>3.12</td><td>Supported</td></tr>
</table>
<!-- hidden note -->
<pre><code>pip install acme</code></pre>
"""

GITHUB_RELEASE_BODY = """
## What's Changed

[![CI](https://img.shields.io/badge/ci-green.svg)](https://github.com/acme/acme/actions)

* **Breaking:** dropped Python 3.8 support by @dev in https://github.com/acme/acme/pull/12
* Added a `--retry` flag to the CLI
* Fixed a crash in [the parser](https://github.com/acme/acme/blob/main/parser.py)

```python
client = Acme(retry=3)
```

**Full Changelog**: https://github.com/acme/acme/compare/v1.0...v1.1
"""

OSV_DETAILS = """
### Impact

A crafted request can cause unbounded memory growth in the `parse_headers`
function, leading to denial of service.

### Patches
Upgrade to **2.4.1**.

| Version | Affected |
| ------- | -------- |
| < 2.4.1 | yes      |
"""


@pytest.fixture(autouse=True)
def _fresh_ai_budget():
    text_summary.reset_ai_budget()
    yield
    text_summary.reset_ai_budget()


# --- cleaning -------------------------------------------------------------


@pytest.mark.parametrize("raw", [README_WITH_HTML, GITHUB_RELEASE_BODY, OSV_DETAILS])
def test_markup_never_survives_cleaning(raw):
    cleaned = clean_summary(raw)

    assert cleaned
    assert len(cleaned) <= MAX_SUMMARY_CHARS
    # A bare "<" is fine - OSV writes version ranges like "< 2.4.1" - but no
    # tag or markdown syntax may survive.
    for marker in ("<p", "<img", "<table", "<td", "<h1", "</", "![", "](", "```", "|", "##", "**", "https://"):
        assert marker not in cleaned


def test_readme_keeps_the_readable_sentence():
    cleaned = clean_summary(README_WITH_HTML)

    assert "Acme Toolkit speeds up data pipelines." in cleaned
    assert "hidden note" not in cleaned
    assert "shields.io" not in cleaned


def test_release_notes_keep_the_important_points():
    cleaned = clean_summary(GITHUB_RELEASE_BODY)

    assert "Breaking: dropped Python 3.8 support" in cleaned
    assert "--retry" in cleaned
    # Link text survives; the URL does not.
    assert "the parser" in cleaned
    assert "github.com" not in cleaned


def test_table_rows_read_as_text():
    cleaned = clean_summary(README_WITH_HTML)
    assert "3.12, Supported" in cleaned


def test_short_clean_text_is_left_alone():
    text = "Adds a retry flag and fixes a parser crash."
    assert clean_summary(text) == text
    assert looks_unsummarized(text) is False


def test_cleaning_is_repeatable():
    once = clean_summary(GITHUB_RELEASE_BODY)
    assert clean_summary(once) == once
    assert looks_unsummarized(once) is False


def test_long_text_is_cut_at_a_sentence_and_marked():
    text = "First sentence is short. " + "Filler words that go on and on. " * 40
    cleaned = clean_summary(text)

    assert len(cleaned) <= MAX_SUMMARY_CHARS
    assert cleaned.endswith(".") or cleaned.endswith("…")
    assert "Filler" in cleaned


def test_text_without_sentence_ends_is_marked_as_cut():
    cleaned = clean_summary("word " * 200)

    assert cleaned.endswith("…")
    assert len(cleaned) <= MAX_SUMMARY_CHARS


def test_empty_input():
    assert clean_summary("") == ""
    assert clean_summary(None) == ""
    assert looks_unsummarized("") is False
    assert summarize(None) == ""


def test_markup_only_input_yields_nothing():
    assert clean_summary("<p><img src='https://img.shields.io/badge/x.svg'></p>") == ""


# --- AI summaries ---------------------------------------------------------


def _long_notes():
    return "Release notes. " + "This release changes many internal details. " * 30


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("tracker.utils.groq_analyzer.GroqAnalyzer")
def test_long_text_is_summarized_by_groq(analyzer):
    analyzer.return_value.summarize_release_notes.return_value = (
        "Drops Python 3.8 and fixes a parser crash."
    )

    summary = summarize(_long_notes(), library="acme", version="1.1")

    assert summary == "Drops Python 3.8 and fixes a parser crash."
    analyzer.return_value.summarize_release_notes.assert_called_once()


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("tracker.utils.groq_analyzer.GroqAnalyzer")
def test_failed_ai_call_falls_back_to_trimming(analyzer):
    analyzer.return_value.summarize_release_notes.side_effect = RuntimeError("rate limited")

    summary = summarize(_long_notes(), library="acme", version="1.1")

    assert summary.startswith("Release notes.")
    assert len(summary) <= MAX_SUMMARY_CHARS


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("tracker.utils.groq_analyzer.GroqAnalyzer")
def test_ai_markup_is_cleaned_too(analyzer):
    analyzer.return_value.summarize_release_notes.return_value = "**Breaking:** drops 3.8."

    assert summarize(_long_notes()) == "Breaking: drops 3.8."


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("tracker.utils.groq_analyzer.GroqAnalyzer")
def test_short_text_never_calls_groq(analyzer):
    assert summarize("Adds a retry flag.") == "Adds a retry flag."
    analyzer.assert_not_called()


@override_settings(LIBTRACK_AI_SUMMARIES=False)
@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("tracker.utils.groq_analyzer.GroqAnalyzer")
def test_ai_summaries_can_be_turned_off(analyzer):
    summary = summarize(_long_notes())

    analyzer.assert_not_called()
    assert summary.startswith("Release notes.")
    assert len(summary) <= MAX_SUMMARY_CHARS


@patch.dict("os.environ", {}, clear=True)
@patch("tracker.utils.groq_analyzer.GroqAnalyzer")
def test_missing_api_key_falls_back_to_trimming(analyzer):
    summary = summarize(_long_notes())

    analyzer.assert_not_called()
    assert len(summary) <= MAX_SUMMARY_CHARS


@patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
@patch("tracker.utils.groq_analyzer.GroqAnalyzer")
def test_ai_calls_are_capped_per_process(analyzer):
    analyzer.return_value.summarize_release_notes.return_value = "Short summary."

    for _ in range(text_summary.AI_CALL_LIMIT + 5):
        summarize(_long_notes())

    assert analyzer.return_value.summarize_release_notes.call_count == text_summary.AI_CALL_LIMIT


# --- cleaning what is already stored --------------------------------------


@pytest.mark.django_db
def test_clean_summaries_command_rewrites_stored_text():
    library = Library.objects.create(name="acme", key="acme")
    release = LibraryRelease.objects.create(
        library=library, version="1.1", summary=README_WITH_HTML
    )
    future = FutureUpdateCache.objects.create(
        library="acme", version="2.0", features=GITHUB_RELEASE_BODY, confidence=60
    )
    tidy = LibraryRelease.objects.create(
        library=library, version="1.0", summary="Adds a retry flag."
    )

    call_command("clean_summaries", "--no-ai")

    release.refresh_from_db()
    future.refresh_from_db()
    tidy.refresh_from_db()
    assert "<table>" not in release.summary
    assert len(release.summary) <= MAX_SUMMARY_CHARS
    assert "![" not in future.features
    assert tidy.summary == "Adds a retry flag."


@pytest.mark.django_db
def test_clean_summaries_dry_run_writes_nothing():
    library = Library.objects.create(name="acme", key="acme")
    release = LibraryRelease.objects.create(
        library=library, version="1.1", summary=README_WITH_HTML
    )

    call_command("clean_summaries", "--dry-run", "--no-ai")

    release.refresh_from_db()
    assert release.summary == README_WITH_HTML
