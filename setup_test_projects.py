import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/Users/raghavdesai/Documents/Projects/LibTrack AI/LibTrack_AI_11Nov')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from tracker.models import Project, StackComponent

# Get email for notifications
test_email = os.getenv('MAILTRAP_FROM_EMAIL', 'test@example.com')

print("=" * 80)
print("SETTING UP TEST PROJECTS WITH DIVERSE TECHNOLOGY STACKS")
print("=" * 80)

# Project 1: Modern Frontend SPA
print("\n[1/5] Creating Modern Frontend SPA Project...")
project1, created = Project.objects.get_or_create(
    project_name="E-Commerce Frontend",
    defaults={
        'developer_names': 'Frontend Team',
        'developer_emails': test_email,
        'notification_type': 'major, minor, future',  # All notifications
    }
)

if created:
    print(f"✅ Created: {project1.project_name}")
    # Add frontend stack
    components1 = [
        {'category': 'Language', 'name': 'typescript', 'version': '5.3.3', 'scope': 'dev'},
        {'category': 'Framework', 'name': 'react', 'version': '18.2.0', 'scope': 'core'},
        {'category': 'Framework', 'name': 'nextjs', 'version': '14.0.4', 'scope': 'core'},
        {'category': 'Library', 'name': 'tailwindcss', 'version': '3.4.0', 'scope': 'styling'},
        {'category': 'Library', 'name': 'axios', 'version': '1.6.2', 'scope': 'http'},
        {'category': 'Library', 'name': 'zustand', 'version': '4.4.7', 'scope': 'state'},
    ]
    
    for comp_data in components1:
        StackComponent.objects.create(project=project1, **comp_data)
    print(f"   Added {len(components1)} components")
else:
    print(f"✓ Exists: {project1.project_name}")

# Project 2: Backend API Service
print("\n[2/5] Creating Backend API Service Project...")
project2, created = Project.objects.get_or_create(
    project_name="Payment Gateway API",
    defaults={
        'developer_names': 'Backend Team',
        'developer_emails': test_email,
        'notification_type': 'major',  # Only major updates
    }
)

if created:
    print(f"✅ Created: {project2.project_name}")
    components2 = [
        {'category': 'Language', 'name': 'python', 'version': '3.11.7', 'scope': 'runtime'},
        {'category': 'Framework', 'name': 'django', 'version': '4.2.8', 'scope': 'web'},
        {'category': 'Framework', 'name': 'django-rest-framework', 'version': '3.14.0', 'scope': 'api'},
        {'category': 'Library', 'name': 'celery', 'version': '5.3.4', 'scope': 'tasks'},
        {'category': 'Library', 'name': 'redis', 'version': '5.0.1', 'scope': 'cache'},
        {'category': 'Library', 'name': 'psycopg2', 'version': '2.9.9', 'scope': 'database'},
        {'category': 'Library', 'name': 'stripe', 'version': '7.8.0', 'scope': 'payment'},
    ]
    
    for comp_data in components2:
        StackComponent.objects.create(project=project2, **comp_data)
    print(f"   Added {len(components2)} components")
else:
    print(f"✓ Exists: {project2.project_name}")

# Project 3: Mobile App
print("\n[3/5] Creating Mobile App Project...")
project3, created = Project.objects.get_or_create(
    project_name="Social Media Mobile App",
    defaults={
        'developer_names': 'Mobile Team',
        'developer_emails': test_email,
        'notification_type': 'minor, future',  # Minor and future only
    }
)

if created:
    print(f"✅ Created: {project3.project_name}")
    components3 = [
        {'category': 'Language', 'name': 'javascript', 'version': '14.21.3', 'scope': 'node'},
        {'category': 'Framework', 'name': 'react-native', 'version': '0.73.0', 'scope': 'mobile'},
        {'category': 'Library', 'name': 'react-navigation', 'version': '6.1.9', 'scope': 'routing'},
        {'category': 'Library', 'name': 'expo', 'version': '50.0.0', 'scope': 'tooling'},
        {'category': 'Library', 'name': 'react-native-reanimated', 'version': '3.6.1', 'scope': 'animation'},
        {'category': 'Library', 'name': 'firebase', 'version': '10.7.1', 'scope': 'backend'},
    ]
    
    for comp_data in components3:
        StackComponent.objects.create(project=project3, **comp_data)
    print(f"   Added {len(components3)} components")
else:
    print(f"✓ Exists: {project3.project_name}")

# Project 4: Machine Learning Platform
print("\n[4/5] Creating ML Platform Project...")
project4, created = Project.objects.get_or_create(
    project_name="AI Model Training Platform",
    defaults={
        'developer_names': 'ML Team',
        'developer_emails': test_email,
        'notification_type': 'major, minor',  # Major and minor (no future)
    }
)

if created:
    print(f"✅ Created: {project4.project_name}")
    components4 = [
        {'category': 'Language', 'name': 'python', 'version': '3.11.7', 'scope': 'runtime'},
        {'category': 'Library', 'name': 'tensorflow', 'version': '2.15.0', 'scope': 'ml'},
        {'category': 'Library', 'name': 'pytorch', 'version': '2.1.2', 'scope': 'ml'},
        {'category': 'Library', 'name': 'scikit-learn', 'version': '1.3.2', 'scope': 'ml'},
        {'category': 'Library', 'name': 'pandas', 'version': '2.1.4', 'scope': 'data'},
        {'category': 'Library', 'name': 'numpy', 'version': '1.26.2', 'scope': 'compute'},
        {'category': 'Library', 'name': 'fastapi', 'version': '0.108.0', 'scope': 'api'},
    ]
    
    for comp_data in components4:
        StackComponent.objects.create(project=project4, **comp_data)
    print(f"   Added {len(components4)} components")
else:
    print(f"✓ Exists: {project4.project_name}")

# Project 5: DevOps/Infrastructure
print("\n[5/5] Creating DevOps Infrastructure Project...")
project5, created = Project.objects.get_or_create(
    project_name="Cloud Infrastructure Manager",
    defaults={
        'developer_names': 'DevOps Team',
        'developer_emails': test_email,
        'notification_type': 'future',  # Only future updates
    }
)

if created:
    print(f"✅ Created: {project5.project_name}")
    components5 = [
        {'category': 'Tool', 'name': 'docker', 'version': '24.0.7', 'scope': 'container'},
        {'category': 'Tool', 'name': 'kubernetes', 'version': '1.28.4', 'scope': 'orchestration'},
        {'category': 'Tool', 'name': 'terraform', 'version': '1.6.6', 'scope': 'iac'},
        {'category': 'Tool', 'name': 'ansible', 'version': '2.16.2', 'scope': 'config'},
        {'category': 'Library', 'name': 'prometheus', 'version': '2.48.1', 'scope': 'monitoring'},
        {'category': 'Library', 'name': 'nginx', 'version': '1.25.3', 'scope': 'proxy'},
    ]
    
    for comp_data in components5:
        StackComponent.objects.create(project=project5, **comp_data)
    print(f"   Added {len(components5)} components")
else:
    print(f"✓ Exists: {project5.project_name}")

# Summary
print("\n" + "=" * 80)
print("SETUP COMPLETE!")
print("=" * 80)

all_projects = Project.objects.all()
total_components = StackComponent.objects.count()

print(f"\n📊 Database Summary:")
print(f"   Total Projects: {all_projects.count()}")
print(f"   Total Components: {total_components}")

print("\n📋 Projects Created:")
for idx, proj in enumerate(all_projects, 1):
    comp_count = proj.components.count()
    print(f"\n   {idx}. {proj.project_name}")
    print(f"      Notifications: {proj.notification_type}")
    print(f"      Components: {comp_count}")
    print(f"      Team: {proj.developer_names}")
    
    # Show sample components
    sample_comps = proj.components.all()[:3]
    for comp in sample_comps:
        print(f"        - {comp.name} {comp.version} ({comp.category})")
    if comp_count > 3:
        print(f"        ... and {comp_count - 3} more")

print("\n" + "=" * 80)
print("🎯 NEXT STEPS:")
print("=" * 80)
print("\n1. View Dashboard:")
print("   → http://localhost:8000/dashboard/")
print("   → You should see 5 projects with diverse stacks")

print("\n2. Run Daily Check:")
print("   → python manage.py run_daily_check")
print("   → This will check all libraries and send notifications")

print("\n3. Test Notification Filtering:")
print("   → Project 1: Gets all (major, minor, future)")
print("   → Project 2: Gets only major updates")
print("   → Project 3: Gets minor and future only")
print("   → Project 4: Gets major and minor (no future)")
print("   → Project 5: Gets only future updates")

print("\n4. Check Different Stacks:")
print("   → Frontend: React, Next.js, TailwindCSS")
print("   → Backend: Django, Celery, Redis")
print("   → Mobile: React Native, Expo, Firebase")
print("   → ML: TensorFlow, PyTorch, Pandas")
print("   → DevOps: Docker, Kubernetes, Terraform")

print("\n✅ Test data ready!")
