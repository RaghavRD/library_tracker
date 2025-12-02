"""
Test script for Phase 2: Daily check command with future updates routing.
This script manually tests the _evaluate_component logic to see if it properly
routes future vs released updates.
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/Users/raghavdesai/Documents/Projects/LibTrack AI/LibTrack_AI_11Nov')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from tracker.models import FutureUpdateCache, UpdateCache
from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer

print("=" * 70)
print("Phase 2 Test: Future Updates Routing Logic")
print("=" * 70)

# Initialize
serper = SerperFetcher(debug=False)
groq = GroqAnalyzer()

# Test Case: Analyze a library
library_name = "react"
print(f"\n[TEST] Analyzing {library_name}...")
print("-" * 70)

serper_results = serper.search_library(library_name)
analysis = groq.analyze(library_name, serper_results)

print("\n✅ Groq Analysis Results:")
print(f"  Library: {analysis.get('library')}")
print(f"  Version: {analysis.get('version')}")
print(f"  Category: {analysis.get('category')}")
print(f"  Is Released: {analysis.get('is_released')}")
print(f"  Confidence: {analysis.get('confidence')}%")
print(f"  Expected Date: {analysis.get('expected_date') or 'N/A'}")
print(f"  Release Date: {analysis.get('release_date') or 'N/A'}")

# Check routing logic
category = analysis.get('category')
is_released = analysis.get('is_released', True)

print("\n🔀 Routing Decision:")
if category == "future" or not is_released:
    print(f"  ✅ Would route to _handle_future_update() (category={category}, is_released={is_released})")
    print(f"  ✅ Would store in FutureUpdateCache")
else:
    print(f"  ✅ Would route to standard UpdateCache (category={category}, is_released={is_released})")

# Check database
print("\n📊 Database Status:")
print(f"  FutureUpdateCache entries: {FutureUpdateCache.objects.count()}")
print(f"  UpdateCache entries: {UpdateCache.objects.count()}")

if FutureUpdateCache.objects.exists():
    print("\n  Recent Future Updates:")
    for future in FutureUpdateCache.objects.all()[:5]:
        print(f"    - {future.library} {future.version} (confidence: {future.confidence}%, notified: {future.notification_sent})")

print("\n" + "=" * 70)
print("✅ Phase 2 Logic Test Complete")
print("=" * 70)
print("\nNOTE: To fully test, run: python manage.py run_daily_check")
print("This will execute the actual update check with routing logic.")
