import logging
import os
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from django.template.loader import render_to_string
from django.templatetags.static import static
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BREVO_BASE = "https://api.brevo.com/v3/smtp/email"


def _message_id(response) -> str | None:
    """Brevo returns the accepted message id in the body, not a header."""
    try:
        return response.json().get("messageId")
    except Exception:
        return None


def _empty_severity_counts() -> dict[str, int]:
    return {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}


def _safe_url(value: str) -> str:
    value = (value or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _email_logo_url() -> str:
    configured_url = os.getenv("LIBTRACK_EMAIL_LOGO_URL", "").strip()
    if configured_url:
        return configured_url

    logo_path = static("tracker/images/libtrack.png")
    public_base_url = os.getenv("LIBTRACK_PUBLIC_BASE_URL", "").strip()
    if public_base_url:
        return urljoin(public_base_url.rstrip("/") + "/", logo_path.lstrip("/"))
    return logo_path


def _legacy_digest(
    project_name: str,
    updates: list[dict],
    *,
    future_opt_in: bool,
) -> dict:
    """Keep direct callers compatible while using the project digest template."""
    packages = []
    for entry in updates:
        is_future = entry.get("category") == "future"
        packages.append(
            {
                "library": entry.get("library", "Unknown"),
                "installed_version": entry.get("from_version") or "-",
                "latest_version": "-" if is_future else entry.get("version", "-"),
                "future_version": entry.get("version", "-") if is_future else "-",
                "status": "Future update" if is_future else f"{entry.get('category', 'Update').title()} update",
                "status_color": "#175cd3" if is_future else "#b54708",
                "security": "Clear",
                "security_color": "#067647",
                "security_count": 0,
                "detected_on": entry.get("release_date") or entry.get("expected_date") or "-",
                "release_summary": "" if is_future else entry.get("summary", ""),
                "release_date": entry.get("release_date", ""),
                "release_source": "" if is_future else _safe_url(entry.get("source", "")),
                "future_summary": entry.get("summary", "") if is_future else "",
                "future_source": _safe_url(entry.get("source", "")) if is_future else "",
                "future_confidence": entry.get("confidence") if is_future else None,
                "future_expected_date": entry.get("expected_date") or entry.get("release_date") or "TBD",
                "security_findings": [],
                "security_findings_hidden": 0,
                "is_actionable": True,
            }
        )

    severity_counts = _empty_severity_counts()
    return {
        "project_name": project_name,
        "packages": packages,
        "package_details": packages,
        "hidden_package_count": 0,
        "total_packages": len(packages),
        "outdated_packages": sum(entry.get("category") != "future" for entry in updates),
        "up_to_date_packages": 0,
        "future_enabled": future_opt_in or any(entry.get("category") == "future" for entry in updates),
        "future_packages": sum(entry.get("category") == "future" for entry in updates),
        "updates_count": len(updates),
        "health_score": 100,
        "health_label": "Current digest",
        "health_color": "#175cd3",
        "security_status": "No active findings",
        "security_color": "#067647",
        "active_security_count": 0,
        "affected_packages": 0,
        "fixes_available": 0,
        "severity_counts": severity_counts,
        "severity_segments": [
            {"label": "Clear", "count": 0, "width": 100, "color": "#12b76a"}
        ],
        "scan_date": "Current notification cycle",
    }


def _email_subject(
    project_name: str,
    library: str,
    version: str,
    category: str,
    digest: dict,
) -> str:
    security_count = digest.get("active_security_count", 0)
    update_count = digest.get("updates_count", 0)
    if category == "security":
        return f"{project_name}: {security_count} security finding(s) need attention"
    if update_count > 1:
        suffix = f" and {security_count} security finding(s)" if security_count else ""
        return f"{project_name}: {update_count} package updates{suffix}"
    if category == "future":
        return f"{library} {version} Planned - {project_name}"
    return f"{library} {version} Released - {project_name}"


def send_update_email(
    api_key: str | None,
    project_name: str,
    recipients: Iterable[str] | str,
    library: str,
    version: str,
    category: str,
    summary: str | None,
    source: str,
    release_date: str | None = None,
    from_email: str | None = None,
    timeout: int = 15,
    updates: list[dict] | None = None,
    future_opt_in: bool = False,
    digest: dict | None = None,
) -> dict:
    """Send one project update and security digest through Brevo."""
    api_key = api_key or getattr(settings, "BREVO_API_KEY", "")
    from_addr = from_email or getattr(settings, "BREVO_FROM_EMAIL", "")

    if not api_key or not from_addr:
        return {
            "success": False,
            "status_text": "Missing BREVO_API_KEY or BREVO_FROM_EMAIL",
            "http_status": None,
            "response_text": None,
            "error": "missing_credentials",
            "request_id": None,
        }

    if isinstance(recipients, str):
        recipients = [item.strip() for item in recipients.split(",") if item.strip()]
    recipients = list(recipients or [])
    if not recipients:
        return {
            "success": False,
            "status_text": "No valid recipients provided",
            "http_status": None,
            "response_text": None,
            "error": "no_recipients",
            "request_id": None,
        }

    updates_payload = updates or [
        {
            "library": library,
            "version": version,
            "category": category,
            "release_date": release_date or "Unknown",
            "summary": summary or "No summary provided.",
            "source": source,
        }
    ]
    digest = digest or _legacy_digest(
        project_name,
        updates_payload,
        future_opt_in=future_opt_in,
    )
    subject = _email_subject(project_name, library, version, category, digest)
    context = {
        "project_name": project_name,
        "digest": digest,
        "subject": subject,
        "brand_logo_url": _email_logo_url(),
    }
    html_content = render_to_string("tracker/emails/project_update.html", context)
    text_content = render_to_string("tracker/emails/project_update.txt", context)

    payload_category = "Security Alerts" if category == "security" else "Project Updates"
    sender_name = getattr(settings, "BREVO_FROM_NAME", "LibTrack AI")
    payload = {
        "sender": {"email": from_addr, "name": sender_name},
        "to": [{"email": recipient} for recipient in recipients],
        # Brevo rewrites the From domain when the sender is a free address such
        # as gmail.com, so replies need an explicit destination to land on.
        "replyTo": {"email": from_addr, "name": sender_name},
        "subject": subject,
        "htmlContent": html_content,
        "textContent": text_content,
        "tags": [payload_category],
    }

    test_mode = getattr(settings, "LIBTRACK_EMAIL_TEST_MODE", True)
    if test_mode:
        logger.info("TEST_MODE: email would be sent with subject=%s", subject)
        print(f"\n--- EMAIL HTML START: {project_name} | {subject} ---")
        print(html_content)
        print(f"--- EMAIL HTML END: {project_name} | {subject} ---\n")
        return {
            "success": True,
            "status_text": "Email would be sent in TEST_MODE",
            "http_status": None,
            "response_text": None,
            "error": None,
            "request_id": None,
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content,
        }

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        response = requests.post(BREVO_BASE, headers=headers, json=payload, timeout=timeout)
        success = 200 <= response.status_code < 300
        status_text = f"Brevo: {response.status_code}"
        response_text = response.text
        request_id = _message_id(response)

        if getattr(settings, "LIBTRACK_LOG_HTTP_STATUS", True):
            logger.info(
                "Brevo email send: status=%s message_id=%s recipients=%s project=%s",
                response.status_code,
                request_id,
                len(recipients),
                project_name,
            )
        if not success:
            logger.warning(
                "Brevo email failed: status=%s message_id=%s response=%s",
                response.status_code,
                request_id,
                response_text[:200],
            )
        return {
            "success": success,
            "status_text": status_text,
            "http_status": response.status_code,
            "response_text": response_text,
            "error": None if success else "http_error",
            "request_id": request_id,
        }
    except Exception as exc:
        logger.error("Brevo exception: %s", exc, exc_info=True)
        return {
            "success": False,
            "status_text": "Brevo exception",
            "http_status": None,
            "response_text": None,
            "error": str(exc),
            "request_id": None,
        }
