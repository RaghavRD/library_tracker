#!/usr/bin/env python
"""
Example: Dual Notification Flow - Future Update → Released Version

This example demonstrates how developers receive TWO separate emails:
1. First email when future update is detected (upcoming version)
2. Second email when that version is actually released

Run with: python tracker/tests/example_dual_notification_flow.py
"""
import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from tracker.models import Project, StackComponent, UpdateCache, FutureUpdateCache
from tracker.utils.send_mail import send_update_email


def print_header(text):
    """Print formatted header."""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80 + "\n")


def print_email_preview(email_type, subject, content_points):
    """Print email preview."""
    print(f"\n📧 {email_type}")
    print("-" * 80)
    print(f"Subject: {subject}")
    print(f"\nContent includes:")
    for point in content_points:
        print(f"  • {point}")
    print("-" * 80)


def example_dual_notification_flow():
    """
    Complete example showing both email notifications.
    
    Timeline:
    - Day 1: Future update detected → Email 1 sent
    - Day 45: Version actually released → Email 2 sent
    """
    
    print_header("Dual Notification Flow Example")
    
    print("SCENARIO: pandas library upgrade from 2.0.0 to 3.0.0")
    print("Developer: alice@company.com")
    print("Notification preference: major, minor, future\n")
    
    # ========================================================================
    # CLEANUP: Remove old test data to avoid UNIQUE constraint errors
    # ========================================================================
    print_header("CLEANUP")
    print("Removing old test data...")
    
    # Delete existing pandas 3.0.0 entries if they exist
    deleted_future = FutureUpdateCache.objects.filter(
        library='pandas', 
        version='3.0.0'
    ).delete()
    
    deleted_released = UpdateCache.objects.filter(
        library='pandas', 
        version='3.0.0'
    ).delete()
    
    # Delete old test projects
    deleted_projects = Project.objects.filter(
        project_name__in=['Data Analytics Platform', 'Demo AI Platform']
    ).delete()
    
    print(f"✓ Cleaned up: {deleted_future[0]} future updates, "
          f"{deleted_released[0]} releases, {deleted_projects[0]} projects")
    
    # ========================================================================
    # SETUP: Create project and component
    # ========================================================================
    print_header("SETUP")
    
    project = Project.objects.create(
        project_name='Data Analytics Platform',
        developer_names='Alice Johnson',
        developer_emails='alice@company.com',
        notification_type='major, minor, future'  # ← Important: future enabled!
    )
    print(f"✓ Created project: {project.project_name}")
    
    component = StackComponent.objects.create(
        project=project,
        category='library',
        key='library',
        name='pandas',
        version='2.0.0',
        scope=''
    )
    print(f"✓ Current version in project: {component.name} {component.version}")
    
    
    # ========================================================================
    # DAY 1: FUTURE UPDATE DETECTED
    # ========================================================================
    print_header("DAY 1 - December 5, 2025 (Today)")
    print("LibTrack AI detects pandas 3.0.0 is planned (not yet released)")
    
    # Create future update entry
    future_update = FutureUpdateCache.objects.create(
        library='pandas',
        version='3.0.0',
        confidence=92,
        expected_date=(datetime.now() + timedelta(days=45)).date(),
        features='Major rewrite with improved performance, new nullable integer dtype, '
                 'better memory efficiency, and native string arrays',
        source='https://pandas.pydata.org/roadmap/',
        status='confirmed',
        notification_sent=False
    )
    
    print(f"\n✓ Future update detected:")
    print(f"  Library: {future_update.library}")
    print(f"  Version: {future_update.version}")
    print(f"  Confidence: {future_update.confidence}%")
    print(f"  Expected release: {future_update.expected_date}")
    print(f"  Status: {future_update.status}")
    
    
    # ========================================================================
    # EMAIL 1: FUTURE UPDATE NOTIFICATION
    # ========================================================================
    print("\n" + "─" * 80)
    print("SENDING EMAIL 1: Future Update Alert")
    print("─" * 80)
    
    email1_updates = [{
        'library': 'pandas',
        'version': '3.0.0',
        'category': 'future',
        'category_label': 'Future',
        'release_date': future_update.expected_date.strftime("%Y-%m-%d"),
        'summary': future_update.features,
        'source': future_update.source,
        'component_type': 'library',
        'confidence': future_update.confidence
    }]
    
    success1, message1 = send_update_email(
        mailtrap_api_key=os.getenv('MAILTRAP_MAIN_KEY'),
        project_name=project.project_name,
        recipients=project.developer_emails,
        library='pandas',
        version='3.0.0',
        category='future',
        summary=future_update.features,
        source=future_update.source,
        updates=email1_updates,
        future_opt_in=True
    )
    
    # Mark as notified
    future_update.notification_sent = True
    future_update.notification_sent_at = datetime.now()
    future_update.save()
    
    print(f"✓ Email sent: {success1}")
    
    # Show what the email looks like
    print_email_preview(
        "EMAIL 1 - Future Update Alert",
        f"🔮 Future Update Alert: pandas 3.0.0 Planned",
        [
            "Yellow banner: 'Future Update Notice (confidence: 92%)'",
            "Warning: 'This is a planned/upcoming release that has NOT been officially released yet'",
            "Expected release date: " + future_update.expected_date.strftime("%Y-%m-%d"),
            "Confidence percentage: 92%",
            "Planned features summary",
            "Note: 'You'll receive another notification when this version is officially released'"
        ]
    )
    
    print(f"\n💡 Alice now knows pandas 3.0.0 is coming and can start planning the upgrade!")
    
    
    # ========================================================================
    # DAY 45: VERSION ACTUALLY RELEASED
    # ========================================================================
    print_header("DAY 45 - January 19, 2026 (45 days later)")
    print("pandas 3.0.0 is officially released!")
    
    # Create the actual release entry
    released_update = UpdateCache.objects.create(
        project=project,
        library='pandas',
        version='3.0.0',
        category='major',
        release_date=datetime.now().strftime("%Y-%m-%d"),
        summary='pandas 3.0.0 has been officially released with major performance improvements, '
                'new nullable integer dtype, better memory management, and native string arrays.',
        source='https://pandas.pydata.org/docs/whatsnew/v3.0.0.html'
    )
    
    # Link the future prediction to the actual release
    future_update.promoted_to_release = released_update
    future_update.status = 'released'
    future_update.save()
    
    print(f"\n✓ Version released:")
    print(f"  Library: {released_update.library}")
    print(f"  Version: {released_update.version}")
    print(f"  Category: {released_update.category}")
    print(f"  Release date: {released_update.release_date}")
    
    print(f"\n✓ Future prediction updated:")
    print(f"  Status: {future_update.status}")
    print(f"  Promoted to: UpdateCache#{released_update.id}")
    print(f"  Relationship verified: {released_update.future_predictions.first() == future_update}")
    
    
    # ========================================================================
    # EMAIL 2: ACTUAL RELEASE NOTIFICATION
    # ========================================================================
    print("\n" + "─" * 80)
    print("SENDING EMAIL 2: Release Notification")
    print("─" * 80)
    
    email2_updates = [{
        'library': 'pandas',
        'version': '3.0.0',
        'category': 'major',
        'category_label': 'Major',
        'release_date': released_update.release_date,
        'summary': released_update.summary,
        'source': released_update.source,
        'component_type': 'library'
    }]
    
    success2, message2 = send_update_email(
        mailtrap_api_key=os.getenv('MAILTRAP_MAIN_KEY'),
        project_name=project.project_name,
        recipients=project.developer_emails,
        library='pandas',
        version='3.0.0',
        category='major',
        summary=released_update.summary,
        source=released_update.source,
        release_date=released_update.release_date,
        updates=email2_updates,
        future_opt_in=False  # This is now an actual release
    )
    
    print(f"✓ Email sent: {success2}")
    
    # Show what the email looks like
    print_email_preview(
        "EMAIL 2 - Release Notification",
        f"pandas 3.0.0 Released",
        [
            "Standard release format (NO yellow future notice banner)",
            "Actual release date: " + released_update.release_date,
            "Release summary with full details",
            "Link to official release notes",
            "Category: Major",
            "Clear indication this is now officially available"
        ]
    )
    
    print(f"\n💡 Alice now knows the version is officially released and can proceed with upgrade!")
    
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    print_header("SUMMARY: Complete Notification Flow")
    
    print("Timeline:")
    print(f"  📅 Day 1  - Future update detected (confidence: {future_update.confidence}%)")
    print(f"            └─> 📧 Email 1: Future Update Alert sent")
    print(f"  📅 Day 45 - Version officially released")
    print(f"            └─> 📧 Email 2: Release Notification sent")
    
    print("\n\nDeveloper Experience:")
    print("  1️⃣  Receives future alert → Can start planning upgrade")
    print("  2️⃣  45 days to prepare, test, and plan migration")
    print("  3️⃣  Receives release notification → Can execute upgrade")
    print("  4️⃣  Both emails linked in database for tracking")
    
    print("\n\nDatabase State:")
    print(f"  • FutureUpdateCache: {FutureUpdateCache.objects.filter(library='pandas', version='3.0.0').count()} entry")
    print(f"    - Status: {future_update.status}")
    print(f"    - Notification sent: {future_update.notification_sent}")
    print(f"    - Promoted to release: ✓")
    
    print(f"\n  • UpdateCache: {UpdateCache.objects.filter(library='pandas', version='3.0.0').count()} entry")
    print(f"    - Category: {released_update.category}")
    print(f"    - Has future prediction link: ✓")
    
    print("\n\n✅ Complete dual notification flow demonstrated!\n")
    
    return {
        'project': project,
        'component': component,
        'future_update': future_update,
        'released_update': released_update,
        'email1_status': success1,
        'email2_status': success2
    }


def show_email_comparison():
    """Show side-by-side comparison of both emails."""
    print_header("EMAIL COMPARISON")
    
    print("=" * 80)
    print(f"{'EMAIL 1: FUTURE UPDATE' : ^40} | {'EMAIL 2: ACTUAL RELEASE' : ^40}")
    print("=" * 80)
    
    comparisons = [
        ("Subject", "🔮 Future Update Alert: pandas 3.0.0 Planned", "pandas 3.0.0 Released"),
        ("Banner", "Yellow future notice banner", "No banner"),
        ("Urgency", "Plan ahead - not urgent", "Action needed - can upgrade now"),
        ("Date shown", "Expected: 2026-01-19", "Released: 2026-01-19"),
        ("Confidence", "92% confidence shown", "No confidence (it's released!)"),
        ("Warning", "NOT officially released yet", "Officially available"),
        ("Content focus", "Planned features & roadmap", "Actual release notes"),
        ("Call to action", "Start planning migration", "Proceed with upgrade"),
    ]
    
    for label, email1, email2 in comparisons:
        print(f"{label:15} | {email1:38} | {email2:38}")
    
    print("=" * 80)


if __name__ == '__main__':
    print("""
    ╔════════════════════════════════════════════════════════════════════════════╗
    ║                                                                            ║
    ║     DUAL NOTIFICATION FLOW EXAMPLE                                         ║
    ║     Demonstrates how developers receive TWO emails:                        ║
    ║     1. When future update is detected                                      ║
    ║     2. When that version is actually released                              ║
    ║                                                                            ║
    ╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Run the main example
    result = example_dual_notification_flow()
    
    # Show email comparison
    show_email_comparison()
    
    print("\n" + "="*80)
    print("  To see the actual HTML emails, check your test output or mailtrap inbox")
    print("="*80 + "\n")
