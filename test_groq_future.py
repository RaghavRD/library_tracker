"""
Test script for enhanced Groq analyzer with future updates support.
Tests if Groq correctly returns is_released, confidence, and expected_date fields.
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/Users/raghavdesai/Documents/Projects/LibTrack AI/LibTrack_AI_11Nov')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer
import json

print("=" * 60)
print("Testing Enhanced Groq Analyzer with Future Updates")
print("=" * 60)

# Initialize
serper = SerperFetcher(debug=False)
groq = GroqAnalyzer()

# Test Case 1: Known future update (React 19)
print("\n[Test 1] Testing with React (may have RC/future versions)...")
results = serper.search_library("react")
analysis = groq.analyze("react", results)

print("\nGroq Response:")
print(f"  Library: {analysis.get('library')}")
print(f"  Version: {analysis.get('version')}")
print(f"  Category: {analysis.get('category')}")
print(f"  Is Released: {analysis.get('is_released')}")
print(f"  Confidence: {analysis.get('confidence')}%")
print(f"  Expected Date: {analysis.get('expected_date')}")
print(f"  Release Date: {analysis.get('release_date')}")
print(f"  Summary: {analysis.get('summary', '')[:100]}...")

# Test Case 2: Stable released library (requests)
print("\n" + "=" * 60)
print("\n[Test 2] Testing with requests (should be released)...")
results = serper.search_library("requests", "2.31.0")
analysis = groq.analyze("requests", results)

print("\nGroq Response:")
print(f"  Library: {analysis.get('library')}")
print(f"  Version: {analysis.get('version')}")
print(f"  Category: {analysis.get('category')}")
print(f"  Is Released: {analysis.get('is_released')}")
print(f"  Confidence: {analysis.get('confidence')}%")
print(f"  Expected Date: {analysis.get('expected_date')}")
print(f"  Release Date: {analysis.get('release_date')}")

print("\n" + "=" * 60)
print("✅ Test completed! Verify fields are populated correctly.")
print("=" * 60)
