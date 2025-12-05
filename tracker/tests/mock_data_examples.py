"""
Standalone mock data examples for manual testing.

This script creates realistic mock data scenarios and can be run independently
to test email notifications and data flow.

Usage:
    python manage.py shell < tracker/tests/mock_data_examples.py

Or in Django shell:
    from tracker.tests.mock_data_examples import *
    create_future_update_scenario()
    create_release_scenario()
"""
import os
import django

# Setup Django environment for standalone execution
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from datetime import datetime, timedelta
from tracker.models import Project, StackComponent, UpdateCache, FutureUpdateCache
from tracker.utils.send_mail import send_update_email


def create_future_update_scenario():
    """
    Create a complete scenario for testing future update detection.
    
    Returns:
        dict with created objects
    """
    print("\n" + "="*60)
    print("SCENARIO 1: Future Update Detection")
    print("="*60)
    
    # Create project with future notifications enabled
    project = Project.objects.create(
        project_name='AI Research Platform',
        developer_names='Alice Johnson, Bob Smith',
        developer_emails='alice@example.com, bob@example.com',
        notification_type='major, minor, future'
    )
    print(f"✓ Created project: {project.project_name}")
    
    # Add components
    components = [
        StackComponent.objects.create(
            project=project,
            category='library',
            key='library',
            name='numpy',
            version='1.24.0',
            scope=''
        ),
        StackComponent.objects.create(
            project=project,
            category='library',
            key='library',
            name='pandas',
            version='2.0.3',
            scope=''
        ),
        StackComponent.objects.create(
            project=project,
            category='language',
            key='language',
            name='Python',
            version='3.11',
            scope=''
        )
    ]
    print(f"✓ Created {len(components)} stack components")
    
    # Create future updates
    future_updates = [
        FutureUpdateCache.objects.create(
            library='numpy',
            version='2.0.0',
            confidence=95,
            expected_date=(datetime.now() + timedelta(days=60)).date(),
            features='Complete rewrite with improved performance, new data types, and modern API design',
            source='https://numpy.org/neps/roadmap.html',
            status='confirmed'
        ),
        FutureUpdateCache.objects.create(
            library='pandas',
            version='3.0.0',
            confidence=85,
            expected_date=(datetime.now() + timedelta(days=90)).date(),
            features='Major architectural changes for better memory efficiency and native string dtype',
            source='https://pandas.pydata.org/roadmap',
            status='detected'
        ),
        FutureUpdateCache.objects.create(
            library='Python',
            version='3.13',
            confidence=100,
            expected_date=(datetime.now() + timedelta(days=120)).date(),
            features='JIT compiler, improved error messages, and performance optimizations',
            source='https://peps.python.org/pep-0719/',
            status='confirmed'
        )
    ]
    print(f"✓ Created {len(future_updates)} future update entries")
    
    # Test email notification for future update
    print("\n" + "-"*60)
    print("Testing Future Update Email Notification")
    print("-"*60)
    
    email_updates = [
        {
            'library': 'numpy',
            'version': '2.0.0',
            'category': 'future',
            'category_label': 'Future',
            'release_date': future_updates[0].expected_date.strftime("%Y-%m-%d"),
            'summary': future_updates[0].features,
            'source': future_updates[0].source,
            'component_type': 'library',
            'confidence': future_updates[0].confidence
        },
        {
            'library': 'pandas',
            'version': '3.0.0',
            'category': 'future',
            'category_label': 'Future',
            'release_date': future_updates[1].expected_date.strftime("%Y-%m-%d"),
            'summary': future_updates[1].features,
            'source': future_updates[1].source,
            'component_type': 'library',
            'confidence': future_updates[1].confidence
        }
    ]
    
    success, message = send_update_email(
        mailtrap_api_key=os.getenv('MAILTRAP_MAIN_KEY'),
        project_name=project.project_name,
        recipients=project.developer_emails,
        library='numpy + 1 more',
        version='2.0.0 and upcoming releases',
        category='future',
        summary='See future update details below',
        source='',
        updates=email_updates,
        future_opt_in=True
    )
    
    print(f"Email Status: {'✓ Success' if success else '✗ Failed'}")
    print(f"Message: {message[:200]}")
    
    return {
        'project': project,
        'components': components,
        'future_updates': future_updates,
        'email_status': (success, message)
    }


def create_release_scenario():
    """
    Create a complete scenario for testing actual release notifications.
    
    Returns:
        dict with created objects
    """
    print("\n" + "="*60)
    print("SCENARIO 2: Actual Version Release")
    print("="*60)
    
    # Create project
    project = Project.objects.create(
        project_name='E-Commerce Backend',
        developer_names='Carol Davis, David Wilson',
        developer_emails='carol@example.com, david@example.com',
        notification_type='major, minor'
    )
    print(f"✓ Created project: {project.project_name}")
    
    # Add components
    components = [
        StackComponent.objects.create(
            project=project,
            category='library',
            key='library',
            name='django',
            version='4.2',
            scope=''
        ),
        StackComponent.objects.create(
            project=project,
            category='library',
            key='library',
            name='requests',
            version='2.30.0',
            scope=''
        )
    ]
    print(f"✓ Created {len(components)} stack components")
    
    # Create update cache entries (actual releases)
    updates = [
        UpdateCache.objects.create(
            project=project,
            library='django',
            version='5.0',
            category='major',
            release_date=datetime.now().strftime("%Y-%m-%d"),
            summary='Major release with async ORM support, improved admin interface, and Python 3.10+ requirement',
            source='https://docs.djangoproject.com/en/5.0/releases/5.0/'
        ),
        UpdateCache.objects.create(
            project=project,
            library='requests',
            version='2.31.0',
            category='minor',
            release_date=datetime.now().strftime("%Y-%m-%d"),
            summary='Bug fixes and security improvements',
            source='https://github.com/psf/requests/releases/tag/v2.31.0'
        )
    ]
    print(f"✓ Created {len(updates)} update cache entries")
    
    # Test email notification for released versions
    print("\n" + "-"*60)
    print("Testing Released Version Email Notification")
    print("-"*60)
    
    email_updates = [
        {
            'library': 'django',
            'version': '5.0',
            'category': 'major',
            'category_label': 'Major',
            'release_date': updates[0].release_date,
            'summary': updates[0].summary,
            'source': updates[0].source,
            'component_type': 'library'
        },
        {
            'library': 'requests',
            'version': '2.31.0',
            'category': 'minor',
            'category_label': 'Minor',
            'release_date': updates[1].release_date,
            'summary': updates[1].summary,
            'source': updates[1].source,
            'component_type': 'library'
        }
    ]
    
    success, message = send_update_email(
        mailtrap_api_key=os.getenv('MAILTRAP_MAIN_KEY'),
        project_name=project.project_name,
        recipients=project.developer_emails,
        library='django + 1 more',
        version='5.0 and additional releases',
        category='mix',
        summary='See release details below',
        source='',
        updates=email_updates,
        future_opt_in=False
    )
    
    print(f"Email Status: {'✓ Success' if success else '✗ Failed'}")
    print(f"Message: {message[:200]}")
    
    return {
        'project': project,
        'components': components,
        'updates': updates,
        'email_status': (success, message)
    }


def create_transition_scenario():
    """
    Create a scenario showing future update → released transition.
    
    Returns:
        dict with created objects showing the transition
    """
    print("\n" + "="*60)
    print("SCENARIO 3: Future → Released Transition")
    print("="*60)
    
    # Create project
    project = Project.objects.create(
        project_name='Data Science Platform',
        developer_names='Eve Martinez',
        developer_emails='eve@example.com',
        notification_type='major, minor, future'
    )
    print(f"✓ Created project: {project.project_name}")
    
    # Add component
    component = StackComponent.objects.create(
        project=project,
        category='library',
        key='library',
        name='scikit-learn',
        version='1.3.0',
        scope=''
    )
    print(f"✓ Created component: {component.name} {component.version}")
    
    # Step 1: Detect future update
    future_update = FutureUpdateCache.objects.create(
        library='scikit-learn',
        version='1.4.0',
        confidence=92,
        expected_date=(datetime.now() + timedelta(days=45)).date(),
        features='New estimators, improved performance, enhanced documentation',
        source='https://scikit-learn.org/dev/whats_new.html',
        status='confirmed',
        notification_sent=True,
        notification_sent_at=datetime.now()
    )
    print(f"✓ Step 1: Future update detected and notified")
    print(f"  Library: {future_update.library} {future_update.version}")
    print(f"  Confidence: {future_update.confidence}%")
    print(f"  Expected: {future_update.expected_date}")
    
    # Step 2: Version is released
    released_update = UpdateCache.objects.create(
        project=project,
        library='scikit-learn',
        version='1.4.0',
        category='major',
        release_date=datetime.now().strftime("%Y-%m-%d"),
        summary=future_update.features,
        source='https://scikit-learn.org/stable/whats_new/v1.4.html'
    )
    print(f"\n✓ Step 2: Version officially released")
    print(f"  Library: {released_update.library} {released_update.version}")
    print(f"  Category: {released_update.category}")
    
    # Step 3: Link future to released
    future_update.promoted_to_release = released_update
    future_update.status = 'released'
    future_update.save()
    print(f"\n✓ Step 3: Future update promoted to released")
    print(f"  Status: {future_update.status}")
    print(f"  Linked to: UpdateCache#{released_update.id}")
    
    return {
        'project': project,
        'component': component,
        'future_update': future_update,
        'released_update': released_update,
        'relationship': released_update.future_predictions.first() == future_update
    }


def run_all_scenarios():
    """Run all mock data scenarios."""
    print("\n" + "="*60)
    print("LibTrack AI - Mock Data Examples")
    print("="*60)
    
    scenario1 = create_future_update_scenario()
    scenario2 = create_release_scenario()
    scenario3 = create_transition_scenario()
    
    print("\n" + "="*60)
    print("Summary")
    print("="*60)
    print(f"✓ Created {Project.objects.count()} projects")
    print(f"✓ Created {StackComponent.objects.count()} components")
    print(f"✓ Created {FutureUpdateCache.objects.count()} future updates")
    print(f"✓ Created {UpdateCache.objects.count()} released updates")
    print("\nAll scenarios completed successfully!")
    
    return {
        'scenario1_future': scenario1,
        'scenario2_release': scenario2,
        'scenario3_transition': scenario3
    }


if __name__ == '__main__':
    # Run all scenarios when executed as a script
    results = run_all_scenarios()
