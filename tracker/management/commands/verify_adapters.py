from django.core.management.base import BaseCommand
from tracker.models import Project, StackComponent, Library
from tracker.services.version_fetch_service import VersionFetchService
from tracker.utils.future_version_detector import FutureVersionDetector
import logging

class Command(BaseCommand):
    help = 'Seeds test data for registry adapters and verifies updates'

    def handle(self, *args, **kwargs):
        self.stdout.write("🌱 Seeding test data for registry verification...")
        
        # 1. Create Test Project
        project, created = Project.objects.get_or_create(
            project_name="Registry Adapter Test",
            defaults={
                "developer_names": "Test User",
                "developer_emails": "test@example.com"
            }
        )
        
        # 2. Define Test Components (using older versions to ensure updates are found)
        # Format: (name, installed_version, type)
        components_data = [
            ("rails", "7.0.0", "gem"),               # RubyGems
            ("serde", "1.0.100", "crate"),           # Cargo
            ("org.springframework:spring-core", "5.3.0", "maven"), # Maven
            ("Newtonsoft.Json", "13.0.1", "nuget"),  # NuGet
            ("react", "17.0.0", "npm"),              # NPM (Control)
        ]
        
        detector = VersionFetchService()
        future_detector = FutureVersionDetector()
        
        results = []

        for name, installed_ver, comp_type in components_data:
            self.stdout.write(f"\nProcessing {name} ({comp_type})...")
            
            # Create/Update Component
            comp, created = StackComponent.objects.get_or_create(
                project=project,
                name=name,
                defaults={
                    "version": installed_ver,
                    "category": "Back-end", # Default category
                    "key": name.lower(),
                }
            )
            
            # Ensure Library exists
            library, _ = Library.objects.get_or_create(
                name=name,
                defaults={"key": name.lower(), "component_type": "library"}
            )

            # Fetch Latest Stable
            self.stdout.write(f"  Fetching latest stable version...")
            # Use internal method to fetch just this library
            detector._fetch_library(library, stdout_writer=self.stdout.write)
            
            # Refresh to get latest data
            library.refresh_from_db()
            latest_ver = library.latest_version or "Unknown"
            
            if latest_ver != "Unknown":
                # Update component for future check context
                comp.library_ref = library
                comp.save()
            
            # Detect Future Updates
            self.stdout.write(f"  Detecting future versions...")
            future_updates = future_detector.detect_future_versions(name, latest_ver)
            
            results.append({
                "name": name,
                "type": comp_type,
                "installed": installed_ver,
                "latest_stable": latest_ver,
                "future_candidates": [f"{f.version} ({f.prerelease_type})" for f in future_updates]
            })

        # 3. Report Results
        self.stdout.write("\n" + "="*80)
        self.stdout.write("VERIFICATION RESULTS")
        self.stdout.write("="*80)
        self.stdout.write(f"{'Component':<30} | {'Type':<10} | {'Installed':<10} | {'Latest':<10} | {'Future Versions'}")
        self.stdout.write("-" * 80)
        
        for r in results:
            future_str = ", ".join(r['future_candidates']) if r['future_candidates'] else "None"
            self.stdout.write(f"{r['name']:<30} | {r['type']:<10} | {r['installed']:<10} | {r['latest_stable']:<10} | {future_str}")
        
        self.stdout.write("="*80)
