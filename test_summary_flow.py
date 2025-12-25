"""
Quick test to verify summary/source flow through the system.
This simulates the daily check flow with debug output.
"""
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')

import django
django.setup()

from tracker.models import Library, LibraryRelease, Project
from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer
from packaging import version as pkg_version
from datetime import datetime

print("="*60)
print("Testing Summary/Source Flow")
print("="*60)

# Step 1: Update a library (simulating _update_libraries)
lib_name = "django"
lib = Library.objects.filter(name=lib_name).first()

if not lib:
    print(f"Library '{lib_name}' not found")
    sys.exit(1)

print(f"\n1. FETCH PHASE - Updating {lib.name}")
print(f"   Current version: {lib.latest_version}")

serper = SerperFetcher()
groq = GroqAnalyzer()

results = serper.search_library(lib.name, lib.latest_version)
analysis = groq.analyze(lib.name, results)

detected_version = analysis.get("version", "")
summary_text = analysis.get("summary", "")
source_url = analysis.get("source", "")

print(f"\n   Groq Analysis:")
print(f"   - Version: {detected_version}")
print(f"   - Summary: {summary_text[:100]}..." if summary_text else "   - Summary: EMPTY")
print(f"   - Source: {source_url}" if source_url else "   - Source: EMPTY")

# Simulate the update logic
if detected_version:
    try:
        should_update = not lib.latest_version or pkg_version.parse(detected_version) > pkg_version.parse(lib.latest_version)
        
        if should_update:
            print(f"\n   ✅ Updating library to {detected_version}")
            lib.latest_version = detected_version
            lib.last_checked_at = datetime.now()
            lib.save()
            
            release, created = LibraryRelease.objects.get_or_create(
                library=lib,
                version=detected_version,
                defaults={
                    "release_date": datetime.now().date(),
                    "summary": summary_text,
                    "source_url": source_url,
                    "is_security_release": False
                }
            )
            
            if not created:
                release.summary = summary_text
                release.source_url = source_url
                release.save()
            
            print(f"   LibraryRelease {'created' if created else 'updated'}")
        else:
            print(f"   ⏭️  Skipped (not newer)")
    except Exception as e:
        print(f"   ❌ Error: {e}")

# Step 2: Verify retrieval (simulating _notify_projects)
print(f"\n2. NOTIFY PHASE - Checking what projects would receive")

project = Project.objects.first()
if not project:
    print("   No projects found")
    sys.exit(1)

print(f"   Project: {project.project_name}")

for comp in project.components.all():
    if comp.library_ref and comp.library_ref.name == lib_name:
        lib_ref = comp.library_ref
        print(f"\n   Component: {comp.name}")
        print(f"   - Component version: {comp.version}")
        print(f"   - Library latest: {lib_ref.latest_version}")
        
        if lib_ref.latest_version and pkg_version.parse(lib_ref.latest_version) > pkg_version.parse(comp.version):
            release = lib_ref.releases.filter(version=lib_ref.latest_version).first()
            
            print(f"   - Update available: YES")
            print(f"   - LibraryRelease found: {release is not None}")
            
            if release:
                print(f"   - Summary in DB: {release.summary[:100]}..." if release.summary else "   - Summary in DB: EMPTY")
                print(f"   - Source in DB: {release.source_url}" if release.source_url else "   - Source in DB: EMPTY")
                
                # This is what goes in the email
                email_summary = release.summary if release else "New version available"
                email_source = release.source_url if release else ""
                
                print(f"\n   EMAIL WILL CONTAIN:")
                print(f"   - Summary: {email_summary[:100]}..." if email_summary else "   - Summary: DEFAULT TEXT")
                print(f"   - Source: {email_source}" if email_source else "   - Source: NO LINK")
            else:
                print("   - ⚠️ NO LibraryRelease found for this version!")
                print("   - Email will use default text")

print("\n" + "="*60)
print("Test Complete")
print("="*60)
