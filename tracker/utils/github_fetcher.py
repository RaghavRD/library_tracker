"""
GitHub API integration for detecting future versions from Releases and Milestones.
"""

import os
import requests
import re
import logging
from typing import List, Optional, Dict
from datetime import datetime
import base64
from django.conf import settings
from tracker.utils.future_version_validator import FutureVersionValidator
from tracker.utils.registry_adapters.base import PreReleaseInfo

logger = logging.getLogger(__name__)

class GitHubFetcher:
    """
    Fetches version information from GitHub API.
    Handles authentication and rate limiting.
    """
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self, token: Optional[str] = None):
        # Try to get token from settings/env if not provided
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "LibTrack-AI-Version-Detector"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def get_future_versions(self, repo_url: str) -> List[PreReleaseInfo]:
        """
        Detect future versions for a GitHub repository.
        Combines results from local methods.
        
        Args:
            repo_url: Full GitHub URL (e.g., https://github.com/facebook/react)
        """
        owner, repo = self._parse_repo_url(repo_url)
        if not owner or not repo:
            return []
            
        detections = []
        
        # 1. Check Releases (for pre-releases)
        detections.extend(self.get_prereleases(owner, repo))
        
        # 2. Check Milestones (for planned versions)
        detections.extend(self.get_open_milestones(owner, repo))
        
        # 3. Check Roadmap File (if no milestones found)
        # (Only checking if we need more info, to save API calls)
        if not detections:
             roadmap = self.detect_roadmap_file(owner, repo)
             if roadmap:
                 detections.append(roadmap)
        
        return detections

    def detect_roadmap_file(self, owner: str, repo: str) -> Optional[PreReleaseInfo]:
        """Look for ROADMAP.md and parse it."""
        candidates = ["ROADMAP.md", "roadmap.md", "PLANS.md", "Roadmap.md"]
        
        for filename in candidates:
            url = f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{filename}"
            try:
                resp = requests.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    content = base64.b64decode(data.get("content", "")).decode("utf-8")
                    
                    # Simple heuristic parsing
                    return PreReleaseInfo(
                        version="Roadmap", # Placeholder
                        release_date=None,
                        prerelease_type="roadmap",
                        summary=f"Found roadmap file: {filename}. Content preview: {content[:100]}...",
                        source_url=data.get("html_url", ""),
                        trust_level=80,
                        is_published=False
                    )
            except Exception:
                continue
        return None

    def get_prereleases(self, owner: str, repo: str) -> List[PreReleaseInfo]:
        """Fetch pre-releases from GitHub Releases API."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/releases"
        results = []
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"GitHub API error {resp.status_code} for {owner}/{repo}")
                return []
                
            releases = resp.json()
            for release in releases:
                if not isinstance(release, dict): continue
                
                # Check if marked as prerelease
                if release.get("prerelease") and not release.get("draft"):
                    tag_name = release.get("tag_name", "")
                    # Strip 'v' prefix
                    version = tag_name.lstrip("v")
                    
                    results.append(PreReleaseInfo(
                        version=version,
                        release_date=self._parse_date(release.get("published_at")),
                        prerelease_type=FutureVersionValidator.classify_prerelease_type(version),
                        summary=release.get("body", "")[:500], # Truncate summary
                        source_url=release.get("html_url", ""),
                        trust_level=95,
                        is_published=True # GitHub Release means it's published/tagged
                    ))
                    
            return results
            
        except Exception as e:
            logger.error(f"Error fetching GitHub releases for {owner}/{repo}: {e}")
            return []

    def get_open_milestones(self, owner: str, repo: str) -> List[PreReleaseInfo]:
        """Fetch open milestones which often represent future versions."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/milestones"
        params = {"state": "open", "sort": "due_on"}
        results = []
        
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            if resp.status_code != 200: return []
            
            milestones = resp.json()
            for ms in milestones:
                if not isinstance(ms, dict): continue
                
                title = ms.get("title", "")
                version = self._extract_version_from_title(title)
                
                if version:
                    results.append(PreReleaseInfo(
                        version=version,
                        release_date=self._parse_date(ms.get("due_on")),
                        prerelease_type="milestone",
                        summary=ms.get("description", "") or f"GitHub Milestone: {title}",
                        source_url=ms.get("html_url", ""),
                        trust_level=85, # Less certain than a release
                        is_published=False
                    ))
                    
            return results
            
        except Exception as e:
            logger.error(f"Error fetching GitHub milestones for {owner}/{repo}: {e}")
            return []

    def _parse_repo_url(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Extract owner and repo from URL."""
        if not url: return None, None
        match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
        if match:
            return match.group(1), match.group(2).removesuffix(".git")
        return None, None

    def _parse_date(self, date_str: str) -> Optional[datetime.date]:
        """Parse GitHub date string."""
        if not date_str: return None
        try:
            # Format: '2025-01-15T10:00:00Z'
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.date()
        except:
            return None

    def _extract_version_from_title(self, title: str) -> Optional[str]:
        """Extract semantic version from milestone title (e.g. 'v2.0', 'Release 3.1')."""
        # Look for patterns like v1.2, 1.2.3, 2.0
        match = re.search(r"v?(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.]+)?)$", title.split()[0])
        if match:
            return match.group(1)
            
        # Or look for any isolate version-like string
        match = re.search(r"\bv?(\d+\.\d+\.\d+)\b", title)
        if match:
            return match.group(1)
            
        return None
