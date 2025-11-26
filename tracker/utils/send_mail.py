import os
import requests
from typing import Iterable
from dotenv import load_dotenv

load_dotenv()

# Mailtrap Transactional/Bulk API endpoint
MAILTRAP_BASE = "https://bulk.api.mailtrap.io/api/send"


def send_update_email(
    mailtrap_api_key: str | None,
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
    updates: list[dict[str, str]] | None = None,
    future_opt_in: bool = False,
) -> tuple[bool, str]:
    """
    Send an HTML email via Mailtrap's Bulk (Transactional) API.

    Args:
        mailtrap_api_key: Mailtrap API key (if None, uses MAILTRAP_API_KEY from .env)
        project_name: Name of the project
        recipients: Iterable of emails or comma-separated string of emails
        library: Library name (e.g., 'numpy')
        version: Version string (e.g., '2.2.3')
        category: 'major', 'minor', or 'mix'
        summary: Short release summary text
        source: URL to official release notes
        release_date: Release date string used when no update list is provided
        from_email: Sender email (if None, uses MAILTRAP_FROM_EMAIL from .env)
        timeout: HTTP request timeout in seconds
        updates: Optional list of per-library update dicts for tabular formatting
        future_opt_in: True when registration enabled future update notifications

    Returns:
        (success: bool, status_text: str)
    """

    api_key = mailtrap_api_key or os.getenv("MAILTRAP_MAIN_KEY")
    from_addr = from_email or os.getenv("MAILTRAP_FROM_EMAIL")

    if not api_key or not from_addr:
        return (
            False,
            "❌ Missing MAILTRAP_API_KEY or MAILTRAP_FROM_EMAIL in .env",
        )

    # Normalize recipients (support both list and comma-separated string)
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    recipients = list(recipients or [])
    if not recipients:
        return False, "❌ No valid recipients provided"

    # subject_prefix = (
    #     "[Major Update]"
    #     if category.lower() == "major"
    #     else "[Minor Update]"
    #     if category.lower() == "minor"
    #     else "[Update]"
    # )
    subject = f"{library} {version} Released"

    updates_payload = updates or [
        {
            "library": library,
            "version": version,
            "category": category,
            "category_label": "Future" if future_opt_in else (category.title() if category else "Update"),
            "release_date": release_date or "Unknown",
            "summary": summary or "No summary provided.",
            "source": source,
            "component_type": "library",
        }
    ]

    table_rows_html = "".join(
        f"""
                <tr>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('library', 'Unknown')}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('component_type', 'library').title()}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('version', 'n/a')}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('category_label') or entry.get('category', 'n/a')}</td>
                    <td style="padding:8px;border:1px solid #dfe3e7;">{entry.get('release_date', 'Unknown')}</td>
                </tr>
        """
        for entry in updates_payload
    )

    summary_sections: list[str] = []
    for entry in updates_payload:
        entry_source = entry.get("source") or ""
        link_html = (
            f"<a href='{entry_source}' target='_blank' rel='noopener'>Read release notes</a>"
            if entry_source
            else "<span style='color:#999'>Source link not provided.</span>"
        )
        summary_sections.append(
            f"""
            <div style="margin:0 0 16px;">
                <p style="margin:0 0 6px;"><strong>{entry.get('library', 'Unknown')} {entry.get('version', '')}</strong></p>
                <p style="margin:0 0 6px;">{entry.get('summary', 'No summary provided.')}</p>
                {link_html}
            </div>
            """
        )

    summary_blocks = "".join(summary_sections) or "<p>No summary details were provided for these releases.</p>"
    future_notice_html = ""
    if future_opt_in:
        future_notice_html = """
        <div style="margin:16px 0;padding:12px 16px;border-left:4px solid #f0ad4e;background:#fff8e5;">
            <strong>Future update notice:</strong>
            Future update notifications will only be sent when the respective language or library's new release is officially announced on its official website.
        </div>
        """

    html_content = f"""
    <div style="font-family:Inter,system-ui,-apple-system,sans-serif;font-size:14px;color:#111;line-height:1.5">
        <p style="margin:0 0 16px;">Hello Team,</p>
        <p style="margin:0 0 16px;">
            LibTrack AI detected recent update activity impacting the <strong>{project_name}</strong> project.
            Please review the details below and plan follow-up actions as needed.
        </p>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin:0 0 16px;">
            <thead>
                <tr style="background:#f0f4f8;text-align:left;">
                    <th style="padding:8px;border:1px solid #dfe3e7;">Library</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Type</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Version</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Category</th>
                    <th style="padding:8px;border:1px solid #dfe3e7;">Release Date</th>
                </tr>
            </thead>
            <tbody>
                {table_rows_html}
            </tbody>
        </table>
        <p style="margin:0 0 12px;"><strong>Release Summary</strong></p>
        {summary_blocks}
        {future_notice_html}
        <p style="margin:16px 0;">
            Kindly schedule upgrades or mitigations as appropriate. as this is automated notification. Do not reply to this message.
        </p>
        <p style="margin:0;">Best regards,<br/><strong>LibTrack AI</strong></p>
        <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;"/>
        <p style="color:#666;font-size:12px;margin:0;">Automated notification powered by LibTrack AI.</p>
    </div>
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # print(f"Headers:-------- {headers}")

    # Mailtrap Bulk API payload
    payload_category = "Future Updates" if future_opt_in else "Library Updates"
    payload = {
        "from": {"email": from_addr, "name": "LibTrack AI"},
        "to": [{"email": r} for r in recipients],
        "subject": subject,
        "html": html_content,
        "category": payload_category,
    }

    is_test = os.getenv("TEST_MODE", default=True)
    if is_test:
        print(f"Payload:-------- {html_content}")
        return True, "Test email sent"

    try:
        resp = requests.post(MAILTRAP_BASE, headers=headers, json=payload, timeout=timeout)
        ok = 200 <= resp.status_code < 300
        status_text = f"Mailtrap: {resp.status_code} - {resp.text[:250]}"
        return ok, status_text
    except Exception as e:
        return False, f"Mailtrap exception: {e}"


# from tracker.utils.send_mail import send_update_email  # adjust import path if different

# ok, info = send_update_email(
#     mailtrap_api_key=None,  # will use MAILTRAP_API_KEY from .env
#     project_name="LibTrack AI Test Project",
#     recipients="raghavdesai774@gmail.com",
#     library="pandas",
#     version="2.2.3",
#     category="major",
#     summary="Big performance & bug fixes release.",
#     source="https://pandas.pydata.org/docs/whatsnew/index.html",
#     from_email=None,  # will use MAILTRAP_FROM_EMAIL from .env
# )

# print("status:", ok)
# print("INFO:", info)
