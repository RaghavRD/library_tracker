"""
RubyGems registry adapter.

Official API: https://guides.rubygems.org/rubygems-org-api/
"""

import requests
from datetime import datetime
from typing import Optional, List

from .base import PackageRegistry, VersionInfo, PreReleaseInfo


class RubyGemsRegistry(PackageRegistry):
    """
    Adapter for RubyGems.org registry.
    
    Uses the official RubyGems API to fetch gem information.
    API endpoint: https://rubygems.org/api/v1/versions/{gem}.json
    
    Features:
    - 100% accurate version detection
    - No authentication required
    - Free to use
    - Rate limit: ~10 requests/second
    """
    
    BASE_URL = "https://rubygems.org/api/v1"
    
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
        Fetch latest version from RubyGems.
        
        Args:
            package_name: Ruby gem name (e.g., "rails", "devise")
        
        Returns:
            VersionInfo if gem found, None otherwise
        """
        # RubyGems versions endpoint returns array of all versions
        url = f"{self.BASE_URL}/versions/{package_name}.json"
        self._log_debug(f"Fetching from {url}")
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            versions = response.json()
            
            if not versions or not isinstance(versions, list):
                self._log_error(f"No versions found for {package_name}")
                return None
            
            # Versions are returned in descending order, latest first
            latest = versions[0]
            
            version_number = latest.get("number")
            if not version_number:
                self._log_error(f"No version number in response")
                return None
            
            # Get gem info for additional metadata
            gem_info = self._get_gem_info(package_name)
            
            # Parse release date
            created_at = latest.get("created_at", "")
            release_date = self._parse_rubygems_date(created_at)
            
            # Check if pre-release (contains letters after numbers)
            is_prerelease = latest.get("prerelease", False)
            
            # Get homepage and summary from gem info
            homepage = gem_info.get("homepage_uri", "") if gem_info else ""
            summary = gem_info.get("info", "") if gem_info else ""
            
            # Get source/documentation URLs
            source_url = f"https://rubygems.org/gems/{package_name}/versions/{version_number}"
            
            self._log_info(f"Found {package_name} v{version_number}")
            
            return VersionInfo(
                version=version_number,
                release_date=release_date,
                homepage_url=homepage,
                summary=summary,
                source_url=source_url,
                trust_level=100,  # Official RubyGems API
                is_prerelease=is_prerelease,
                changelog_url=gem_info.get("changelog_uri", "") if gem_info else "",
            )
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self._log_debug(f"Gem {package_name} not found on RubyGems")
                return None
            self._log_error(f"HTTP error fetching {package_name}: {e}")
            raise
        
        except Exception as e:
            self._log_error(f"Error fetching {package_name}: {e}")
            raise
    
    def _get_gem_info(self, gem_name: str) -> Optional[dict]:
        """
        Fetch additional gem metadata.
        
        API: https://rubygems.org/api/v1/gems/{name}.json
        """
        url = f"{self.BASE_URL}/gems/{gem_name}.json"
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._log_debug(f"Could not fetch gem info: {e}")
            return None
    
    def get_prereleases(self, package_name: str) -> List[PreReleaseInfo]:
        """Get pre-releases from RubyGems."""
        url = f"{self.BASE_URL}/versions/{package_name}.json"
        try:
            response = requests.get(url, timeout=self.timeout)
            if response.status_code == 404: return []
            
            versions = response.json()
            prereleases = []
            
            for v in versions:
                if v.get("prerelease"):
                    prereleases.append(PreReleaseInfo(
                        version=v["number"],
                        release_date=self._parse_rubygems_date(v.get("created_at", "")),
                        prerelease_type="beta" if "beta" in v["number"] else "rc" if "rc" in v["number"] else "pre",
                        summary=v.get("summary", ""),
                        source_url=f"https://rubygems.org/gems/{package_name}/versions/{v['number']}",
                        trust_level=95,
                        is_published=True
                    ))
            return prereleases
        except Exception as e:
            self._log_error(f"RubyGems pre-release error: {e}")
            return []

    def get_repository_url(self, package_name: str) -> Optional[str]:
        """Get source repository URL from gem metadata."""
        gem_info = self._get_gem_info(package_name)
        if not gem_info:
            return None
            
        # Check source_code_uri first
        if source_code := gem_info.get("source_code_uri"):
            return source_code
            
        # Fallback to homepage if it looks like a repo
        if homepage := gem_info.get("homepage_uri"):
            if "github.com" in homepage or "gitlab.com" in homepage:
                return homepage
                
        return None

    def supports_package(self, package_name: str) -> bool:
        """
        Check if gem exists on RubyGems.
        
        Makes a lightweight HEAD request to versions endpoint.
        """
        url = f"{self.BASE_URL}/versions/{package_name}.json"
        
        try:
            response = requests.head(url, timeout=self.timeout)
            return response.status_code == 200
        except:
            return False
    
    def _parse_rubygems_date(self, date_str: str) -> datetime.date:
        """
        Parse RubyGems date string to date.
        
        Format: "2024-02-22T14:30:00.000Z"
        """
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.date()
        except Exception as e:
            self._log_error(f"Error parsing date '{date_str}': {e}")
            return datetime.now().date()
