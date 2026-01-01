"""
Audit script for Future Version Detection Pipeline.
Checks API health, Rate Limits, and Registry Heuristics.
"""
import os
import sys
import logging
import requests
import django
from django.conf import settings

# Setup Django standalone
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

from tracker.utils.future_version_detector import FutureVersionDetector
from tracker.utils.github_fetcher import GitHubFetcher

# Configure verbose logging for this script
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit_pipeline")

def check_github_rate_limit():
    print("\n🔍 --- Checking GitHub API Status ---")
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN is NOT set in environment.")
        print("   -> Expect severe rate limiting (60 requests/hour).")
        return
    else:
        print(f"✅ GITHUB_TOKEN is present (starts with {token[:4]}...)")

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            core = data.get("resources", {}).get("core", {})
            limit = core.get("limit")
            remaining = core.get("remaining")
            reset = core.get("reset")
            from datetime import datetime
            reset_time = datetime.fromtimestamp(reset).strftime('%H:%M:%S')
            
            print(f"   Rate Limit: {limit} requests/hour")
            print(f"   Remaining:  {remaining}")
            print(f"   Resets at:  {reset_time}")
            
            if remaining < 10:
                print("⚠️  CRITICAL: GitHub API rate limit nearly exhausted!")
            elif remaining < 100:
                print("⚠️  WARNING: GitHub API rate limit getting low.")
            else:
                print("✅ GitHub API Health: GOOD")
        else:
            print(f"❌ Failed to fetch rate limit. Status: {resp.status_code}")
    except Exception as e:
        print(f"❌ Network error checking GitHub API: {e}")

def audit_registry_detection():
    print("\n🔍 --- Auditing Registry Detection Heuristic ---")
    detector = FutureVersionDetector()
    
    test_cases = [
        ("numpy", "pypi"),
        ("react", "npm"), # False positive in current logic? "react" doesn't start with @
        ("@angular/core", "npm"),
        ("rails", "rubygems"), # Falls back to pypi in current logic?
        ("serde", "cargo"),    # Falls back to pypi?
        ("org.springframework.boot:spring-boot-starter-web", "maven"),
    ]
    
    for name, expected in test_cases:
        detected = detector._detect_registry(name)
        if detected == expected:
            print(f"✅ {name: <40} -> {detected}")
        else:
            if detected == "pypi" and expected != "pypi":
                 print(f"⚠️  {name: <40} -> {detected} (Expected: {expected}) - Fallback triggered")
            else:
                 print(f"❌ {name: <40} -> {detected} (Expected: {expected})")

def deep_check_library(name, current_ver):
    print(f"\n🔍 --- Deep Check: {name} v{current_ver} ---")
    detector = FutureVersionDetector()
    
    # 1. Registry Step
    print(f"1. Registry Scan ({detector._detect_registry(name)})...")
    # Manually invoke internals to see errors
    try:
        reg_key = detector._detect_registry(name)
        registry = detector.registries.get(reg_key)
        if registry:
            prereleases = registry.get_prereleases(name)
            print(f"   Found {len(prereleases)} pre-releases from registry.")
            for p in prereleases[:3]:
                print(f"   - {p.version} ({p.prerelease_type})")
            
            # Repo URL Resolution
            repo_url = registry.get_repository_url(name)
            print(f"   Repository URL resolved: {repo_url}")
            
            if repo_url:
                 print("2. GitHub Ecosystem Scan...")
                 gh_updates = detector.github.get_future_versions(repo_url)
                 print(f"   Found {len(gh_updates)} updates from GitHub.")
                 for u in gh_updates[:3]:
                     print(f"   - {u.version} ({u.prerelease_type}, Source: {u.source_url})")
            else:
                 print("   ⚠️ Skipped GitHub scan (No Repo URL found)")
                 
        else:
            print(f"❌ No registry adapter found for {reg_key}")

    except Exception as e:
        print(f"❌ Exception during deep check: {e}")

if __name__ == "__main__":
    check_github_rate_limit()
    audit_registry_detection()
    # Test a few known libraries
    deep_check_library("pandas", "2.2.0")
    deep_check_library("react", "18.2.0")
