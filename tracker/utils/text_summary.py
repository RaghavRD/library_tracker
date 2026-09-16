"""
Turn release notes, roadmap text and vulnerability write-ups into a short
summary fit for an email.

Sources hand us whatever they have: a PyPI long description is a whole README
in HTML or markdown, a GitHub release body is markdown full of badges, and OSV
details are markdown. Templates escape HTML, so raw text reaches the reader as
literal "<table><tr><td>". Text that will be shown to a user goes through
summarize() before it is saved.

Cleaning is rule based and always runs. For text that is still long after
cleaning, Groq is asked for a plain-language summary; if that is unavailable or
fails, the cleaned text is trimmed instead.
"""

import html
import logging
import os
import re

from django.conf import settings
from django.utils.html import strip_tags

logger = logging.getLogger("libtrack")

# How long a summary may be once cleaned.
MAX_SUMMARY_CHARS = 400
# Cleaned text longer than this is worth asking Groq to condense.
AI_THRESHOLD_CHARS = 600
# Cap AI calls per process so one run cannot spend its whole time budget here.
AI_CALL_LIMIT = 20

_ai_calls_made = 0

_FENCED_CODE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_PRE_BLOCK = re.compile(r"<pre\b.*?</pre>", re.DOTALL | re.IGNORECASE)
_TABLE_CELL_END = re.compile(r"</t[dh]>", re.IGNORECASE)
_BLOCK_END = re.compile(
    r"<br\s*/?>|</(?:p|div|li|tr|table|ul|ol|blockquote|h[1-6])>", re.IGNORECASE
)
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")
_TABLE_DIVIDER = re.compile(r"^\s*\|?[\s:|-]*\|[\s:|-]*\|?\s*$")
_LINE_PREFIX = re.compile(r"^\s*(?:[#>]+\s*|[-*+]\s+|\d+[.)]\s+)")
_EMPHASIS = re.compile(r"(\*\*|__|~~|`)")
_WHITESPACE = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def clean_summary(text, max_chars: int | None = MAX_SUMMARY_CHARS) -> str:
    """
    Strip markup from ``text`` and shorten it to ``max_chars``.

    Pass max_chars=None to clean without shortening. Running this on already
    cleaned text leaves it unchanged.
    """
    if not text:
        return ""

    cleaned = str(text).replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _HTML_COMMENT.sub(" ", cleaned)
    cleaned = _FENCED_CODE.sub(" ", cleaned)
    # The HTML form of a code block, which a README uses as often as fences.
    cleaned = _PRE_BLOCK.sub(" ", cleaned)
    # Cell and block boundaries carry meaning that stripping tags would lose:
    # "<td>3.12</td><td>Supported</td>" must not become "3.12Supported".
    cleaned = _TABLE_CELL_END.sub(", ", cleaned)
    cleaned = _BLOCK_END.sub(" ", cleaned)
    # Tags first, then entities: unescaping first would turn "&lt;b&gt;" into a
    # tag that the next step would delete along with the text around it.
    cleaned = strip_tags(cleaned)
    cleaned = html.unescape(cleaned)
    # Badges are images; ordinary links keep their text and lose the URL.
    cleaned = _MARKDOWN_IMAGE.sub(" ", cleaned)
    cleaned = _MARKDOWN_LINK.sub(r"\1", cleaned)
    cleaned = _BARE_URL.sub(" ", cleaned)

    lines = []
    for line in cleaned.split("\n"):
        if _TABLE_DIVIDER.match(line):
            continue
        prefix = _LINE_PREFIX.match(line)
        line = _LINE_PREFIX.sub("", line)
        # A table row reads as a list once the pipes become separators.
        line = line.replace("|", ", ").strip(", ").strip()
        if not line:
            continue
        # Bullets and headings lose their line breaks when the lines are joined.
        # Without punctuation of their own, a changelog reads as one run-on
        # sentence: "dropped 3.8 support Added a --retry flag Fixed a crash".
        if prefix and line[-1] not in ".!?;:,":
            line += ":" if "#" in prefix.group(0) else ";"
        lines.append(line)

    cleaned = " ".join(line for line in lines if line)
    cleaned = _EMPHASIS.sub("", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    # Punctuation left stranded by removed markup, and the run of commas an
    # empty table cell leaves behind.
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"(?:,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"(?:;\s*){2,}", "; ", cleaned)
    cleaned = re.sub(r"[,;]\s*([.;:!?])", r"\1", cleaned)
    cleaned = cleaned.strip(" ,;:-")

    if max_chars is None or len(cleaned) <= max_chars:
        return cleaned
    return _shorten(cleaned, max_chars)


def _shorten(text: str, max_chars: int) -> str:
    """Cut ``text`` at the last sentence end, else the last word, and mark it."""
    window = text[: max_chars + 1]
    sentence_ends = [match.end() for match in _SENTENCE_END.finditer(window)]
    # Only respect a sentence end that keeps a useful amount of the text.
    if sentence_ends and sentence_ends[-1] >= max_chars // 2:
        return window[: sentence_ends[-1]].strip()

    cut = window.rsplit(" ", 1)[0] if " " in window else text[:max_chars]
    return cut.rstrip(" ,;:-") + "…"


def looks_unsummarized(text, max_chars: int = MAX_SUMMARY_CHARS) -> bool:
    """Whether ``text`` still carries markup or length that cleaning would change."""
    if not text:
        return False
    return clean_summary(text, max_chars=max_chars) != str(text).strip()


def summarize(
    text,
    *,
    library: str = "",
    version: str = "",
    max_chars: int = MAX_SUMMARY_CHARS,
    allow_ai: bool = True,
) -> str:
    """Clean ``text``, asking Groq to condense it when it is long."""
    full = clean_summary(text, max_chars=None)
    if not full:
        return ""
    if len(full) <= max_chars:
        return full

    if allow_ai and len(full) > AI_THRESHOLD_CHARS and _ai_available():
        summary = _ai_summary(full, library=library, version=version, max_chars=max_chars)
        if summary:
            return clean_summary(summary, max_chars=max_chars)

    return _shorten(full, max_chars)


def _ai_available() -> bool:
    if not getattr(settings, "LIBTRACK_AI_SUMMARIES", True):
        return False
    if not os.getenv("GROQ_API_KEY"):
        return False
    return _ai_calls_made < AI_CALL_LIMIT


def _ai_summary(text: str, *, library: str, version: str, max_chars: int) -> str:
    global _ai_calls_made
    _ai_calls_made += 1
    try:
        from tracker.utils.groq_analyzer import GroqAnalyzer

        return GroqAnalyzer().summarize_release_notes(
            text, library=library, version=version, max_chars=max_chars
        )
    except Exception as exc:
        # A summary is a nicety; never fail a check run over one.
        logger.warning("AI summary unavailable for %s %s: %s", library, version, exc)
        return ""


def reset_ai_budget() -> None:
    """Allow AI summaries again; used by tests and long-lived processes."""
    global _ai_calls_made
    _ai_calls_made = 0
