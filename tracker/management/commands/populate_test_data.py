"""
Management command to populate the development database with sample test data.
Usage: python manage.py populate_test_data
"""
from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from tracker.models import Project, StackComponent, UpdateCache, FutureUpdateCache


class Command(BaseCommand):
    help = 'Populate database with sample test data for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing test data before populating',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing test data...'))
            FutureUpdateCache.objects.filter(library__in=['pandas', 'numpy', 'django', 'requests', 'scikit-learn']).delete()
            UpdateCache.objects.filter(library__in=['pandas', 'numpy', 'django', 'requests']).delete()
            StackComponent.objects.filter(project__project_name='Sample Test Project').delete()
            Project.objects.filter(project_name='Sample Test Project').delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing test data'))

        # Create a sample project
        project, created = Project.objects.get_or_create(
            project_name='Sample Test Project',
            defaults={
                'developer_names': 'John Doe, Jane Smith',
                'developer_emails': 'john@example.com, jane@example.com',
                'notification_type': 'major, minor, future'
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created project: {project.project_name}'))
        else:
            self.stdout.write(self.style.WARNING(f'Project already exists: {project.project_name}'))

        # Create stack components
        libraries = [
            ('numpy', '1.24.0'),
            ('pandas', '2.0.0'),
            ('django', '4.2.0'),
            ('requests', '2.30.0'),
            ('scikit-learn', '1.3.0'),
        ]
        
        for lib_name, lib_version in libraries:
            component, created = StackComponent.objects.get_or_create(
                project=project,
                name=lib_name,
                defaults={
                    'category': 'library',
                    'key': 'library',
                    'version': lib_version,
                    'scope': ''
                }
            )
            if created:
                self.stdout.write(f'  ✓ Added library: {lib_name} v{lib_version}')

        # Create some released updates (UpdateCache)
        released_updates = [
            {
                'library': 'numpy',
                'version': '2.0.0',
                'category': 'major',
                'summary': 'Major release with breaking changes and performance improvements',
                'source': 'https://numpy.org/releases/2.0.0',
                'release_date': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            },
            {
                'library': 'pandas',
                'version': '2.1.0',
                'category': 'minor',
                'summary': 'Minor release with bug fixes and new features',
                'source': 'https://pandas.pydata.org/releases/2.1.0',
                'release_date': (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')
            },
            {
                'library': 'requests',
                'version': '2.31.0',
                'category': 'minor',
                'summary': 'Security updates and bug fixes',
                'source': 'https://requests.readthedocs.io/releases/2.31.0',
                'release_date': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            }
        ]

        for update_data in released_updates:
            update, created = UpdateCache.objects.get_or_create(
                project=project,
                library=update_data['library'],
                version=update_data['version'],
                defaults={
                    'category': update_data['category'],
                    'summary': update_data['summary'],
                    'source': update_data['source'],
                    'release_date': update_data['release_date']
                }
            )
            if created:
                self.stdout.write(f'  ✓ Added released update: {update_data["library"]} v{update_data["version"]}')

        # Create future updates (FutureUpdateCache)
        future_updates = [
            {
                'library': 'pandas',
                'version': '3.0.0',
                'confidence': 95,
                'expected_date': (datetime.now() + timedelta(days=120)).date(),
                'features': 'Major overhaul with new API and performance improvements',
                'source': 'https://pandas.pydata.org/roadmap',
                'status': 'detected'
            },
            {
                'library': 'django',
                'version': '5.0',
                'confidence': 88,
                'expected_date': (datetime.now() + timedelta(days=60)).date(),
                'features': 'Async support improvements and new ORM features',
                'source': 'https://djangoproject.com/roadmap',
                'status': 'detected'
            },
            {
                'library': 'scikit-learn',
                'version': '1.4.0',
                'confidence': 92,
                'expected_date': (datetime.now() + timedelta(days=45)).date(),
                'features': 'New estimators and improved GPU support',
                'source': 'https://scikit-learn.org/roadmap',
                'status': 'detected'
            },
            {
                'library': 'numpy',
                'version': '2.1.0',
                'confidence': 85,
                'expected_date': (datetime.now() + timedelta(days=90)).date(),
                'features': 'Enhanced array operations and better memory management',
                'source': 'https://numpy.org/roadmap',
                'status': 'confirmed'  # Higher status
            }
        ]

        for future_data in future_updates:
            future, created = FutureUpdateCache.objects.get_or_create(
                library=future_data['library'],
                version=future_data['version'],
                defaults={
                    'confidence': future_data['confidence'],
                    'expected_date': future_data['expected_date'],
                    'features': future_data['features'],
                    'source': future_data['source'],
                    'status': future_data['status'],
                    'notification_sent': False
                }
            )
            if created:
                self.stdout.write(f'  ✓ Added future update: {future_data["library"]} v{future_data["version"]} (confidence: {future_data["confidence"]}%)')

        self.stdout.write(self.style.SUCCESS('\n✅ Successfully populated test data!'))
        self.stdout.write(self.style.SUCCESS(f'   - Project: {project.project_name}'))
        self.stdout.write(self.style.SUCCESS(f'   - Libraries: {len(libraries)}'))
        self.stdout.write(self.style.SUCCESS(f'   - Released Updates: {len(released_updates)}'))
        self.stdout.write(self.style.SUCCESS(f'   - Future Updates: {len(future_updates)}'))
        self.stdout.write(self.style.SUCCESS('\nYou can now view this data on your dashboard!'))
