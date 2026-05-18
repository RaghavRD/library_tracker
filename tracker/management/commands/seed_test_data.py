"""
Management command to clear cache and seed test data.
"""

from django.core.management.base import BaseCommand
from tracker.models import Project, StackComponent, Library, LibraryRelease, UpdateCache, FutureUpdateCache

class Command(BaseCommand):
    help = "Clears cache and seeds test data for verification"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("⚠️  Clearing all cache data to verify new implementation..."))
        
        # 1. Clear Update Caches
        UpdateCache.objects.all().delete()
        FutureUpdateCache.objects.all().delete()
        LibraryRelease.objects.all().delete()
        
        # 2. Reset Library versions (don't delete, just reset metadata)
        # This forces a fresh fetch from the registries
        Library.objects.update(
            latest_version="",
            last_checked_at=None,
            detection_trust_level=None,
            registry_type=""
        )
        
        self.stdout.write(self.style.SUCCESS("✅ Cache cleared. System will now re-fetch all versions."))
        
        # 3. Create 3 new test projects with diverse stacks
        self.stdout.write(self.style.NOTICE("🌱 Seeding 3 new test projects..."))
        
        # Project 1: Modern Web Stack (npm + pypi)
        p1, _ = Project.objects.get_or_create(
            project_name="E-Commerce Platform",
            defaults={
                "developer_names": "Alice Dev",
                "developer_emails": "raghavdesai@example.com", # Use user's email for testing
                "notification_type": "major, minor"
            }
        )
        
        # Project 2: Data Science Stack (PyPI heavy)
        p2, _ = Project.objects.get_or_create(
            project_name="AI Analytics Engine",
            defaults={
                "developer_names": "Bob Data",
                "developer_emails": "raghavdesai@example.com",
                "notification_type": "all"
            }
        )
        
        # Project 3: Enterprise Backend (Java/Maven + .NET + Rust)
        p3, _ = Project.objects.get_or_create(
            project_name="Legacy Migration System",
            defaults={
                "developer_names": "Charlie Ent",
                "developer_emails": "raghavdesai@example.com",
                "notification_type": "major"
            }
        )
        
        # Add components to Project 1 (Web)
        self._add_component(p1, "react", "18.2.0", "npm")
        self._add_component(p1, "next", "14.1.0", "npm")
        self._add_component(p1, "tailwindcss", "3.4.1", "npm")
        self._add_component(p1, "django", "5.0.1", "pypi")
        
        # Add components to Project 2 (Data)
        self._add_component(p2, "pandas", "2.1.0", "pypi")
        self._add_component(p2, "numpy", "1.26.0", "pypi")
        self._add_component(p2, "scikit-learn", "1.3.0", "pypi")
        self._add_component(p2, "fastapi", "0.109.0", "pypi")
        
        # Add components to Project 3 (Mixed/Enterprise)
        self._add_component(p3, "org.springframework.boot:spring-boot-starter-web", "3.2.0", "maven") # Maven
        self._add_component(p3, "Newtonsoft.Json", "13.0.1", "nuget") # NuGet
        self._add_component(p3, "serde", "1.0.190", "cargo") # Cargo/Rust
        self._add_component(p3, "rails", "7.1.0", "rubygems") # Ruby
        
        self.stdout.write(self.style.SUCCESS("✅ Test data seeded successfully!"))
        self.stdout.write("Run 'python manage.py run_daily_check' to see the new system in action.")

    def _add_component(self, project, name, version, registry_hint):
        comp, created = StackComponent.objects.get_or_create(
            project=project,
            name=name,
            defaults={
                "version": version,
                "category": "library",
                "key": name.lower(),
                "scope": ""
            }
        )
        if not created:
            comp.version = version
            comp.save()
            
        # Ensure library exists with hint
        lib, _ = Library.objects.get_or_create(
            name=name,
            defaults={
                "key": name.lower(),
                "component_type": "library",
                "registry_type": registry_hint
            }
        )
        # Update hint if it was missing
        if not lib.registry_type:
            lib.registry_type = registry_hint
            lib.save()
            
        # Link component
        if not comp.library_ref:
            comp.library_ref = lib
            comp.save()
