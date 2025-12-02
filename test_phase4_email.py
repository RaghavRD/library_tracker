"""
Test script for Phase 4: Email template enhancements for future updates.
This creates a sample email to verify the formatting.
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/Users/raghavdesai/Documents/Projects/LibTrack AI/LibTrack_AI_11Nov')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from tracker.utils.send_mail import send_update_email

print("=" * 70)
print("Phase 4 Test: Email Template for Future Updates")
print("=" * 70)

# Test Case 1: Future update email with confidence
print("\n[TEST 1] Future Update Email with Confidence")
print("-" * 70)

mailtrap_key = os.getenv("MAILTRAP_MAIN_KEY")
from_email = os.getenv("MAILTRAP_FROM_EMAIL")

if not mailtrap_key or not from_email:
    print("❌ Mailtrap credentials not found. Set MAILTRAP_MAIN_KEY and MAILTRAP_FROM_EMAIL")
    sys.exit(1)

# Sample future update data
future_updates = [
    {
        "library": "react",
        "version": "20.0.0",
        "category": "future",
        "release_date": "2026-03-15",
        "summary": "New compiler architecture, improved performance, breaking changes to hooks API",
        "source": "https://react.dev/blog/2026/03/react-20-announcement",
        "component_type": "Framework",
        "confidence": 85,  # NEW!
    },
    {
        "library": "nextjs",
        "version": "16.0.0",
        "category": "future",
        "release_date": "TBD",
        "summary": "App router improvements, new caching strategy",
        "source": "https://nextjs.org/blog/roadmap-2026",
        "component_type": "Framework",
        "confidence": 72,  # NEW!
    }
]

print("\n📧 Sending test email to:", from_email)
print(f"   Subject: 🔮 Future Update Alert: react 20.0.0 Planned")
print(f"   Updates: {len(future_updates)}")

success, message = send_update_email(
    mailtrap_api_key=mailtrap_key,
    project_name="LibTrack AI Test Project",
    recipients=[from_email],  # Send to yourself for testing
    library="react",
    version="20.0.0",
    category="future",
    summary="New compiler, improved performance",
    source="https://react.dev/blog",
    release_date="2026-03-15",
    from_email=from_email,
    updates=future_updates,
    future_opt_in=True,  # Indicates user opted in to future updates
)

if success:
    print(f"\n✅ {message}")
    print("\n📬 Check your email inbox for:")
    print("   - Subject: '🔮 Future Update Alert: react 20.0.0 Planned'")
    print("   - Yellow warning disclaimer with confidence")
    print("   - Confidence column in table (85%, 72%)")
    print("   - 'Upcoming planned' wording in intro")
else:
    print(f"\n❌ {message}")

# Test Case 2: Regular released update (no future disclaimer)
print("\n" + "=" * 70)
print("\n[TEST 2] Regular Released Update Email (for comparison)")
print("-" * 70)

released_updates = [
    {
        "library": "django",
        "version": "5.1.0",
        "category": "major",
        "release_date": "2025-12-01",
        "summary": "New features, security improvements",
        "source": "https://django.org/releases/5.1/",
        "component_type": "Framework",
        # NO confidence field for released versions
    }
]

print("\n📧 Sending test email to:", from_email)
print(f"   Subject: django 5.1.0 Released")
print(f"   Updates: {len(released_updates)}")

success2, message2 = send_update_email(
    mailtrap_api_key=mailtrap_key,
    project_name="LibTrack AI Test Project",
    recipients=[from_email],
    library="django",
    version="5.1.0",
    category="major",
    summary="New features, security improvements",
    source="https://django.org/releases/5.1/",
    release_date="2025-12-01",
    from_email=from_email,
    updates=released_updates,
    future_opt_in=False,  # Regular update
)

if success2:
    print(f"\n✅ {message2}")
    print("\n📬 Check your email inbox for:")
    print("   - Subject: 'django 5.1.0 Released'")
    print("   - NO yellow warning disclaimer")
    print("   - NO confidence column")
    print("   - 'Recent update' wording in intro")
else:
    print(f"\n❌ {message2}")

print("\n" + "=" * 70)
print("✅ Email template test complete!")
print("=" * 70)
print("\nCompare both emails to verify:")
print("  1. Different subject lines")
print("  2. Future has disclaimer, regular doesn't")
print("  3. Future has confidence column, regular doesn't")
print("  4. Different introductory text")
