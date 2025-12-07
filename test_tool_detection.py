#!/usr/bin/env python
"""Test script to verify Docker and Kubernetes tool detection."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer

def test_tool_detection(tool_name, current_version):
    print("-" * 80)
    print(f"Testing {tool_name.upper()} Version Detection")
    print("-" * 80)
    
    fetcher = SerperFetcher(debug=True)
    groq = GroqAnalyzer()
    
    print(f"\n1. Testing Serper search for {tool_name} (tool)...")
    results = fetcher.search_library(tool_name, current_version, component_type="tool")
    
    print(f"\n2. Serper Results:")
    print(f"   - Latest version candidate: {results.get('latest_version_candidate', 'NOT FOUND')}")
    print(f"   - Number of results: {len(results.get('results', []))}")
    
    # Show first result
    if results.get('results'):
        first = results['results'][0]
        print(f"\n3. Top Result:")
        print(f"   - Title: {first.get('title', 'N/A')}")
        print(f"   - Link: {first.get('link', 'N/A')}")
        print(f"   - Versions found: {first.get('versions_found', [])}")
        print(f"   - Score: {first.get('relevance_score', 0)}")
    
    print(f"\n4. Running Groq analysis...")
    analysis = groq.analyze(tool_name, results)
    
    print(f"\n5. Groq Analysis:")
    print(f"   - Detected version: {analysis.get('version', 'NOT FOUND')}")
    print(f"   - Category: {analysis.get('category', 'N/A')}")
    print(f"   - Source: {analysis.get('source', 'N/A')}")
    print("\n")

# Test multiple tools
print("=" * 80)
print("TOOL/SERVICE/CLI VERSION DETECTION TEST")
print("=" * 80)
print()

test_tool_detection("docker", "24.0.0")
test_tool_detection("kubernetes", "1.28.0")
test_tool_detection("nginx", "1.24.0")

print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
