import requests
from typing import Iterable

from django.conf import settings

# Brevo transactional email endpoint
BREVO_BASE = "https://api.brevo.com/v3/smtp/email"


def send_confidence_update_email(
    api_key: str | None,
    project_name: str,
    recipients: Iterable[str] | str,
    library: str,
    version: str,
    old_confidence: int,
    new_confidence: int,
    change_reason: str,
    expected_date: str | None,
    summary: str,
    source: str,
    from_email: str | None = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    """
    Send an email notification when future update confidence increases significantly.
    
    Args:
        api_key: Brevo API key (if None, uses BREVO_API_KEY from settings)
        project_name: Name of the project
        recipients: Iterable of emails or comma-separated string of emails
        library: Library name (e.g., 'Python')
        version: Version string (e.g., '3.15.0')
        old_confidence: Previous confidence level (0-100)
        new_confidence: New confidence level (0-100)
        change_reason: Reason for the confidence increase
        expected_date: Expected release date
        summary: Summary of planned features
        source: URL to announcement/roadmap
        from_email: Sender email (if None, uses BREVO_FROM_EMAIL from settings)
        timeout: HTTP request timeout in seconds
    
    Returns:
        (success: bool, status_text: str)
    """
    
    api_key = api_key or getattr(settings, "BREVO_API_KEY", "")
    from_addr = from_email or getattr(settings, "BREVO_FROM_EMAIL", "")
    
    if not api_key or not from_addr:
        return (
            False,
            "❌ Missing BREVO_API_KEY or BREVO_FROM_EMAIL",
        )
    
    # Normalize recipients
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]
    
    recipients = list(recipients or [])
    if not recipients:
        return False, "❌ No valid recipients provided"
    
    # Calculate confidence increase
    confidence_increase = new_confidence - old_confidence
    confidence_emoji = "📈" if confidence_increase >= 20 else "🔺"
    
    subject = f"{confidence_emoji} Confidence Update: {library} {version} ({old_confidence}% → {new_confidence}%)"
    
    # Build HTML content
    html_content = f"""
    <div style="font-family:Inter,system-ui,-apple-system,sans-serif;font-size:14px;color:#111;line-height:1.5">
        <p style="margin:0 0 16px;">Hello Team,</p>
        <p style="margin:0 0 16px;">
            LibTrack AI has detected increased confidence for a previously announced future update 
            affecting the <strong>{project_name}</strong> project.
        </p>
        
        <div style="background:#f8fafc;border-left:4px solid #3b82f6;padding:16px;margin:0 0 24px;border-radius:4px;">
            <h3 style="margin:0 0 12px;font-size:18px;color:#1e40af;">{library} {version}</h3>
            <div style="display:grid;gap:12px;">
                <div>
                    <strong style="color:#64748b;">Confidence Change:</strong>
                    <div style="margin-top:6px;">
                        <span style="background:#ef4444;color:white;padding:4px 12px;border-radius:4px;font-weight:600;display:inline-block;">
                            {old_confidence}%
                        </span>
                        <span style="margin:0 12px;color:#64748b;">→</span>
                        <span style="background:#22c55e;color:white;padding:4px 12px;border-radius:4px;font-weight:600;display:inline-block;">
                            {new_confidence}%
                        </span>
                        <span style="margin-left:12px;color:#22c55e;font-weight:600;">
                            +{confidence_increase}%
                        </span>
                    </div>
                </div>
                
                <div>
                    <strong style="color:#64748b;">Reason for Update:</strong>
                    <p style="margin:6px 0 0;color:#111;">{change_reason}</p>
                </div>
                
                {f'<div><strong style="color:#64748b;">Expected Release:</strong> <span style="color:#111;">{expected_date}</span></div>' if expected_date else ''}
            </div>
        </div>
        
        <p style="margin:0 0 12px;"><strong>Planned Features:</strong></p>
        <p style="margin:0 0 16px;color:#475569;">{summary}</p>
        
        <a href='{source}' 
           target='_blank' 
           rel='noopener'
           style="display:inline-block;background:#3b82f6;color:white;padding:10px 20px;text-decoration:none;border-radius:6px;font-weight:600;margin:0 0 24px;">
            View Official Announcement
        </a>
        
        <p style="margin:16px 0;color:#64748b;font-size:13px;">
            💡 <em>Higher confidence means more reliable sources have confirmed this update. 
            We'll continue monitoring and notify you when it's officially released.</em>
        </p>
        
        <p style="margin:16px 0;">
            Stay prepared by scheduling necessary upgrades or compatibility checks. 
            This is an automated notification — do not reply to this message.
        </p>
        <p style="margin:0;">Best regards,<br/><strong>LibTrack AI</strong></p>
        <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;"/>
        <p style="color:#666;font-size:12px;margin:0;">Automated notification powered by LibTrack AI.</p>
    </div>
    """
    
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    sender_name = getattr(settings, "BREVO_FROM_NAME", "LibTrack AI")
    payload = {
        "sender": {"email": from_addr, "name": sender_name},
        "to": [{"email": r} for r in recipients],
        "replyTo": {"email": from_addr, "name": sender_name},
        "subject": subject,
        "htmlContent": html_content,
        "tags": ["Confidence Updates"],
    }
    
    if getattr(settings, "LIBTRACK_EMAIL_TEST_MODE", True):
        print("TEST_MODE: Confidence Update Email subject:", subject)
        print("TEST_MODE: Old confidence:", old_confidence, "New:", new_confidence, "Change:", change_reason[:50])
        return True, "🧪 Confidence update email would be sent in TEST_MODE"
    
    try:
        resp = requests.post(BREVO_BASE, headers=headers, json=payload, timeout=timeout)
        ok = 200 <= resp.status_code < 300
        status_text = f"Brevo: {resp.status_code} - {resp.text[:200]}"
        if ok:
            print(f"✅ Confidence update email sent: {status_text}")
        else:
            print(f"❌ Confidence update email failed: {status_text}")
        return ok, status_text
    except Exception as e:
        return False, f"Brevo exception: {e}"


# Existing send_update_email function follows...
