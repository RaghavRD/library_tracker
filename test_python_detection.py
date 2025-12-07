#!/usr/bin/env python
"""Test script to debug Python version detection."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer

print("-" * 8)
print("Testing Python Version Detection")
print("-" * 8)

# Test with debug mode
fetcher = SerperFetcher(debug=True)
groq = GroqAnalyzer()

print("\n1. Testing Serper search for Python (language)...")
results = fetcher.search_library("python", "3.11.7", component_type="language")

print(f"\n2. Serper Results:")
print(f"   - Latest version candidate: {results.get('latest_version_candidate', 'NOT FOUND')}")
print(f"   - Number of filtered results: {len(results.get('filtered', []))}")
print(f"   - Number of all results: {len(results.get('results', []))}")

# Show first few results
print(f"\n3. First 3 search results:")
for i, result in enumerate(results.get('results', [])[:3], 1):
    print(f"\n   Result {i}:")
    print(f"   - Title: {result.get('title', 'N/A')}")
    print(f"   - Link: {result.get('link', 'N/A')}")
    print(f"   - Versions found: {result.get('versions_found', [])}")
    print(f"   - Relevance score: {result.get('relevance_score', 0)}")

print(f"\n4. Running Groq analysis...")
analysis = groq.analyze("python", results)

print(f"\n5. Groq Analysis:")
print(f"   - Detected version: {analysis.get('version', 'NOT FOUND')}")
print(f"   - Category: {analysis.get('category', 'N/A')}")
print(f"   - Confidence: {analysis.get('confidence', 0)}")
print(f"   - Source: {analysis.get('source', 'N/A')}")
print(f"   - Summary: {analysis.get('summary', 'N/A')[:200]}...")

print("\n" + "=" * 80)
print("Test Complete")
print("="* 80)
