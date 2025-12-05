#!/usr/bin/env python
"""
Quick demonstration script for the mock data test suite.

This script demonstrates the key scenarios without requiring pytest installation.
Run with: python tracker/tests/quick_demo.py
"""
import os
import sys
import django

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from datetime import datetime, timedelta
from tracker.models import Project, StackComponent, UpdateCache, FutureUpdateCache
from tracker.tests.test_fixtures import (
    ProjectFactory,
    ComponentFactory,
    FutureUpdateFactory,
    UpdateCacheFactory,
    MockDataBuilder
)


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def demo_future_update_detection():
    """Demonstrate future update detection scenario."""
    print_section("SCENARIO 1: Future Update Detection")
    
    # Create project with future notifications enabled
    project = ProjectFactory.create_future_enabled_project(
        project_name='Demo AI Platform',
        developer_emails='demo@example.com'
    )
    print(f"✓ Created project: {project.project_name}")
    print(f"  Notification types: {project.notification_type}")
    
    # Add a component
    component = ComponentFactory.create_library(
        project, name='numpy', version='1.24.0'
    )
    print(f"✓ Added component: {component.name} {component.version}")
    
    # Create a high-confidence future update
    future = FutureUpdateFactory.create_high_confidence_future(
        library='numpy',
        version='2.0.0',
        confidence=95
    )
    print(f"\n✓ Future update detected:")
    print(f"  Library: {future.library}")
    print(f"  Version: {future.version}")
    print(f"  Confidence: {future.confidence}%")
    print(f"  Expected: {future.expected_date}")
    print(f"  Status: {future.status}")
    print(f"  Notification sent: {future.notification_sent}")
    
    # Demonstrate email would be sent
    print(f"\n📧 Email would be sent to: {project.developer_emails}")
    print(f"   Subject: 🔮 Future Update Alert: {future.library} {future.version} Planned")
    print(f"   Content would include:")
    print(f"   - Confidence: {future.confidence}%")
    print(f"   - Expected date: {future.expected_date}")
    print(f"   - Future Update Notice banner")
    print(f"   - Warning: NOT officially released yet")
    
    return project, component, future


def demo_release_scenario():
    """Demonstrate actual release scenario."""
    print_section("SCENARIO 2: Actual Version Release")
    
    # Create project
    project = ProjectFactory.create_basic_project(
        project_name='Demo Web App',
        developer_emails='webapp@example.com'
    )
    print(f"✓ Created project: {project.project_name}")
    
    # Add component
    component = ComponentFactory.create_library(
        project, name='django', version='4.2'
    )
    print(f"✓ Added component: {component.name} {component.version}")
    
    # Create a released update
    released = UpdateCacheFactory.create_major_release(
        project=project,
        library='django',
        version='5.0'
    )
    print(f"\n✓ Version released:")
    print(f"  Library: {released.library}")
    print(f"  Version: {released.version}")
    print(f"  Category: {released.category}")
    print(f"  Release date: {released.release_date}")
    print(f"  Project: {released.project.project_name}")
    
    # Demonstrate email would be sent
    print(f"\n📧 Email would be sent to: {project.developer_emails}")
    print(f"   Subject: {released.library} {released.version} Released")
    print(f"   Content would include:")
    print(f"   - Release summary section")
    print(f"   - Actual release date")
    print(f"   - NO future notice banner")
    print(f"   - Release notes link")
    
    return project, component, released


def demo_future_to_released_transition():
    """Demonstrate future → released transition."""
    print_section("SCENARIO 3: Future → Released Transition")
    
    # Build the scenario
    scenario = MockDataBuilder.build_future_to_released_scenario()
    project = scenario['project']
    future = scenario['future_update']
    
    print(f"✓ Project: {project.project_name}")
    print(f"✓ Component: {scenario['library']} {scenario['current_version']}")
    
    # Show future update state
    print(f"\n📅 STEP 1: Future update detected")
    print(f"  Library: {future.library}")
    print(f"  Version: {future.version}")
    print(f"  Confidence: {future.confidence}%")
    print(f"  Status: {future.status}")
    print(f"  Expected: {future.expected_date}")
    
    # Mark as notified
    future.notification_sent = True
    future.notification_sent_at = datetime.now()
    future.save()
    print(f"\n  → Future update notification sent!")
    
    # Simulate release
    print(f"\n🚀 STEP 2: Version officially released")
    released = UpdateCacheFactory.create_update_cache(
        project=project,
        library=future.library,
        version=future.version,
        category='major'
    )
    print(f"  Library: {released.library}")
    print(f"  Version: {released.version}")
    print(f"  Category: {released.category}")
    print(f"  Release date: {released.release_date}")
    
    # Link future to released
    print(f"\n🔗 STEP 3: Linking future prediction to release")
    future.promoted_to_release = released
    future.status = 'released'
    future.save()
    
    print(f"  Future status: {future.status}")
    print(f"  Promoted to: UpdateCache#{released.id}")
    print(f"  Relationship verified: {released.future_predictions.first() == future}")
    
    print(f"\n  → Release notification sent!")
    print(f"\n✅ Complete lifecycle tracking:")
    print(f"   1. Future update detected ({future.confidence}% confidence)")
    print(f"   2. Future notification sent")
    print(f"   3. Version actually released")
    print(f"   4. Release notification sent")
    print(f"   5. Future and release linked for tracking")
    
    return scenario, released


def demo_notification_preferences():
    """Demonstrate notification preference filtering."""
    print_section("SCENARIO 4: Notification Preference Testing")
    
    # Create projects with different preferences
    projects = [
        ProjectFactory.create_major_only_project(project_name='Major Only Project'),
        ProjectFactory.create_basic_project(
            project_name='Major+Minor Project',
            notification_type='major, minor'
        ),
        ProjectFactory.create_future_enabled_project(
            project_name='All Updates Project',
            notification_type='major, minor, future'
        )
    ]
    
    for proj in projects:
        print(f"\n✓ {proj.project_name}")
        print(f"  Preferences: {proj.notification_type}")
        print(f"  Would receive:")
        
        prefs = [p.strip() for p in proj.notification_type.split(',')]
        if 'major' in prefs:
            print(f"    - Major updates ✓")
        if 'minor' in prefs:
            print(f"    - Minor updates ✓")
        if 'future' in prefs:
            print(f"    - Future updates ✓")
    
    return projects


def main():
    """Run all demonstrations."""
    print("\n" + "="*70)
    print("  LibTrack AI - Mock Data Test Suite Demonstration")
    print("="*70)
    print("\nThis script demonstrates the test scenarios without requiring pytest.")
    print("All data is created in the database and can be viewed via Django admin.")
    
    try:
        # Run demonstrations
        p1, c1, f1 = demo_future_update_detection()
        p2, c2, r1 = demo_release_scenario()
        scenario, r2 = demo_future_to_released_transition()
        projects = demo_notification_preferences()
        
        # Summary
        print_section("Summary")
        print(f"\n✅ Successfully demonstrated all scenarios!")
        print(f"\nDatabase entries created:")
        print(f"  - Projects: {Project.objects.count()}")
        print(f"  - Components: {StackComponent.objects.count()}")
        print(f"  - Future updates: {FutureUpdateCache.objects.count()}")
        print(f"  - Released updates: {UpdateCache.objects.count()}")
        
        print(f"\n📝 Next steps:")
        print(f"  1. View created data in Django admin")
        print(f"  2. Install pytest: pip install -r requirements.txt")
        print(f"  3. Run full test suite: pytest tracker/tests/ -v")
        print(f"  4. Try standalone examples: python tracker/tests/mock_data_examples.py")
        
        print("\n" + "="*70)
        
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
