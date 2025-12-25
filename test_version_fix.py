#!/usr/bin/env python
"""
Quick test script to verify the version comparison fix.
Tests only animejs and react to save API quota.
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack.settings')
django.setup()

from tracker.models import Library
from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer
from packaging import version as pkg_version
from datetime import datetime

def test_library_update(library_name):
    """Test update logic for a single library"""
    print(f"\n{'='*60}")
    print(f"Testing: {library_name}")
    print('='*60)
    
    # Get library from DB
    library = Library.objects.filter(name=library_name).first()
    if not library:
        print(f"❌ Library '{library_name}' not found in database")
        return
    
    print(f"Current stored version: {library.latest_version or 'empty'}")
    
    # Fetch update
    serper = SerperFetcher()
    groq = GroqAnalyzer()
    
    print("Calling Serper...")
    serper_results = serper.search_library(library_name, library.latest_version, component_type=library.component_type)
    
    print(f"Serper candidate: {serper_results.get('latest_version_candidate', 'N/A')}")
    
    print("Calling Groq...")
    analysis = groq.analyze(library_name, serper_results)
    
    detected_version = analysis.get('version', '')
    print(f"Groq detected version: {detected_version}")
    
    if not detected_version:
        print("⚠️  No version detected by Groq")
        return
    
    # Apply version comparison logic
    should_update = False
    reason = ""
    
    if not library.latest_version:
        should_update = True
        reason = "No previous version stored"
    else:
        try:
            parsed_new = pkg_version.parse(detected_version)
            parsed_current = pkg_version.parse(library.latest_version)
            
            if parsed_new > parsed_current:
                should_update = True
                reason = f"Newer version ({detected_version} > {library.latest_version})"
            elif parsed_new == parsed_current:
                reason = f"Same version ({detected_version} == {library.latest_version})"
            else:
                reason = f"Older version ({detected_version} < {library.latest_version})"
        except Exception as e:
            reason = f"Comparison failed: {e}"
    
    print(f"\nDecision: {'✅ UPDATE' if should_update else '⏭️  SKIP'}")
    print(f"Reason: {reason}")
    
    if should_update:
        library.latest_version = detected_version
        library.last_checked_at = datetime.now()
        library.save()
        print(f"✅ Saved to database: {detected_version}")
    
    # Verify
    library.refresh_from_db()
    print(f"\nFinal stored version: {library.latest_version}")

if __name__ == "__main__":
    print("LibTrack AI - Version Comparison Test")
    print("Testing version update logic for animejs and react\n")
    
    # Test animejs
    test_library_update("animejs")
    
    # Test react  
    test_library_update("react")
    
    print("\n" + "="*60)
    print("Test Complete!")
    print("="*60)
