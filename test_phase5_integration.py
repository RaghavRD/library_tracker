"""
Phase 5: End-to-End Integration Test
Tests the complete future updates flow from detection to email notification.
"""

import os
import sys
import django
from datetime import date, datetime

# Setup Django environment
sys.path.insert(0, '/Users/raghavdesai/Documents/Projects/LibTrack AI/LibTrack_AI_11Nov')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from tracker.models import Project, StackComponent, FutureUpdateCache, UpdateCache
from django.contrib.auth.models import User

print("=" * 80)
print("PHASE 5: END-TO-END INTEGRATION TEST")
print("=" * 80)

# Step 1: Create test user (if needed)
print("\n[Step 1] Setting up test user...")
test_user, created = User.objects.get_or_create(
    username='testuser',
    defaults={'email': 'test@example.com'}
)
if created:
    test_user.set_password('testpass123')
    test_user.save()
    print(f"✅ Created test user: {test_user.username}")
else:
    print(f"✅ Test user exists: {test_user.username}")

# Step 2: Create test project with future notification preference
print("\n[Step 2] Creating test project with future notifications enabled...")
project, created = Project.objects.get_or_create(
    project_name="Future Updates Test Project",
    defaults={
        'developer_names': 'Test Developer',
        'developer_emails': os.getenv('MAILTRAP_FROM_EMAIL', 'test@example.com'),
        'notification_type': 'major, minor, future',  # ✅ Future enabled!
    }
)

if created:
    print(f"✅ Created project: {project.project_name}")
else:
    print(f"✅ Project exists: {project.project_name}")
    # Update to ensure future is enabled
    project.notification_type = 'major, minor, future'
    project.save()

print(f"   Notification preferences: {project.notification_type}")
print(f"   Developers: {project.developer_names}")
print(f"   Emails: {project.developer_emails}")

# Step 3: Add stack components
print("\n[Step 3] Adding stack components...")
components = [
    {'category': 'Framework', 'name': 'react', 'version': '18.0.0', 'scope': 'frontend'},
    {'category': 'Framework', 'name': 'nextjs', 'version': '14.0.0', 'scope': 'fullstack'},
    {'category': 'Framework', 'name': 'django', 'version': '4.2.0', 'scope': 'backend'},
]

for comp_data in components:
    comp, created = StackComponent.objects.get_or_create(
        project=project,
        name=comp_data['name'],
        defaults=comp_data
    )
    status = "created" if created else "exists"
    print(f"   ✅ {comp.name} {comp.version} ({status})")

# Step 4: Manually create a future update entry
print("\n[Step 4] Creating sample future update...")
future_update, created = FutureUpdateCache.objects.get_or_create(
    library='react',
    version='20.0.0',
    defaults={
        'confidence': 88,
        'expected_date': date(2026, 3, 15),
        'features': 'New React Compiler, Improved Server Components, Breaking changes to hooks API, Performance improvements',
        'source': 'https://react.dev/blog/2026/react-20-announcement',
        'status': 'detected',
        'notification_sent': False,
    }
)

if created:
    print(f"✅ Created future update: {future_update}")
else:
    print(f"✅ Future update exists: {future_update}")
    # Reset notification status for testing
    future_update.notification_sent = False
    future_update.notification_sent_at = None
    future_update.save()
    print(f"   Reset notification status for testing")

print(f"   Confidence: {future_update.confidence}%")
print(f"   Expected: {future_update.expected_date}")
print(f"   Status: {future_update.status}")

# Step 5: Check database state
print("\n[Step 5] Database State Check...")
print(f"   Projects: {Project.objects.count()}")
print(f"   Stack Components: {StackComponent.objects.count()}")
print(f"   Future Updates: {FutureUpdateCache.objects.count()}")
print(f"   Update Cache: {UpdateCache.objects.count()}")

# Step 6: Verify notification preferences
print("\n[Step 6] Notification Preference Verification...")
notify_pref = project.notification_type
print(f"   Raw value: '{notify_pref}'")
print(f"   Contains 'future': {'future' in notify_pref}")
print(f"   Contains 'major': {'major' in notify_pref}")
print(f"   Contains 'minor': {'minor' in notify_pref}")

# Step 7: Test scenarios
print("\n[Step 7] Test Scenario Summary...")
print(f"\n   SCENARIO 1: User with 'future' enabled")
print(f"   ✅ Project: {project.project_name}")
print(f"   ✅ Preference: {notify_pref}")
print(f"   ✅ Future update available: react 20.0.0 (88% confidence)")
print(f"   ✅ Expected: Should receive email when run_daily_check executes")

print(f"\n   SCENARIO 2: What will happen in daily check:")
print(f"   1. Groq analyze('react', ...) → is_released=True, version=19.x (current)")
print(f"   2. Update goes to regular UpdateCache")
print(f"   3. To test future: Manually trigger with is_released=False")

print(f"\n   SCENARIO 3: Dashboard display:")
print(f"   1. Visit http://localhost:8000/dashboard/")
print(f"   2. Should see 'Upcoming Future Updates' section")
print(f"   3. Should show: react 20.0.0 with 88% confidence bar")

# Step 8: Create test for released update
print("\n[Step 8] Creating sample released update for comparison...")
released_update, created = UpdateCache.objects.get_or_create(
    library='django',
    defaults={
        'version': '5.1.3',
        'category': 'minor',
        'release_date': '2025-11-28',
        'summary': 'Bug fixes and minor improvements',
        'source': 'https://django.org/releases/5.1.3/',
    }
)

if created:
    print(f"✅ Created released update: {released_update}")
else:
    print(f"✅ Released update exists: {released_update}")

# Step 9: Summary
print("\n" + "=" * 80)
print("TEST SETUP COMPLETE!")
print("=" * 80)

print("\n📋 What to Test Next:")
print("\n1. DASHBOARD TEST:")
print("   → Visit: http://localhost:8000/dashboard/")
print("   → Verify: Yellow 'Upcoming Future Updates' section appears")
print("   → Verify: react 20.0.0 shows with 88% confidence bar")
print("   → Verify: Status badge shows 'Detected' (yellow)")
print("   → Verify: Expected date shows '2026-03-15'")

print("\n2. DAILY CHECK TEST (Manual):")
print("   → Run: python manage.py run_daily_check")
print("   → Watch console for: '[library:react] Future update...'")
print("   → Check email inbox for: '🔮 Future Update Alert: react...'")

print("\n3. EMAIL VERIFICATION:")
print("   → Subject: Should have 🔮 emoji")
print("   → Body: Should have yellow warning box")
print("   → Table: Should have Confidence column (88%)")
print("   → Text: Should say 'upcoming planned'")

print("\n4. MIXED NOTIFICATIONS TEST:")
print("   → Change project notification_type to 'major'")
print("   → Run daily check again")
print("   → Verify: NO future update email (filtered by preference)")

print("\n5. DATABASE VERIFICATION:")
print("   → Check: FutureUpdateCache.notification_sent = True after email")
print("   → Check: notification_sent_at timestamp set")
print("   → Re-run daily check")
print("   → Verify: No duplicate email sent")

print("\n" + "=" * 80)
print("Current State:")
print(f"  Projects: {Project.objects.count()}")
print(f"  Future Updates: {FutureUpdateCache.objects.filter(status__in=['detected', 'confirmed']).count()}")
print(f"  Released Updates: {UpdateCache.objects.count()}")
print("=" * 80)

print("\n✅ Ready for manual verification!")
print("   Start with: http://localhost:8000/dashboard/")
