"""
PyPI (Python Package Index) registry adapter.

Official API: https://warehouse.pypa.io/api-reference/json.html
"""

import requests
from datetime import datetime
from typing import Optional
from packaging.version import parse as parse_version

from .base import PackageRegistry, VersionInfo


class PyPIRegistry(PackageRegistry):
    """
    Adapter for PyPI (Python Package Index).
    
    Uses the official PyPI JSON API to fetch package information.
    API endpoint: https://pypi.org/pypi/{package}/json
    
    Features:
    - 100% accurate version detection
    - No authentication required
    - Free to use
    - No documented rate limits (be respectful)
    """
    
    BASE_URL = "https://pypi.org/pypi"
    
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
        Fetch latest version from PyPI.
        
        Args:
            package_name: Python package name (e.g., "pandas", "Django")
        
        Returns:
            VersionInfo if package found, None otherwise
        """
        url = f"{self.BASE_URL}/{package_name}/json"
        self._log_debug(f"Fetching from {url}")
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            # Extract version info
            info = data.get("info", {})
            version = info.get("version")
            
            if not version:
                self._log_error(f"No version found for {package_name}")
                return None
            
            # Get release date from releases data
            releases = data.get("releases", {})
            version_releases = releases.get(version, [])
            
            if not version_releases:
                self._log_error(f"No release data for version {version}")
                return None
            
            # Use first release (usually wheel or sdist)
            first_release = version_releases[0]
            upload_time = first_release.get("upload_time", "")
            
            # Parse release date
            release_date = self._parse_upload_time(upload_time)
            
            # Check if pre-release
            parsed_version = parse_version(version)
            is_prerelease = parsed_version.is_prerelease
            
            # Build changelog URL from project_urls
            project_urls = info.get("project_urls", {})
            changelog_url = (
                project_urls.get("Changelog") or
                project_urls.get("Change Log") or
                project_urls.get("Release Notes") or
                ""
            )
            
            self._log_info(f"Found {package_name} v{version}")
            
            return VersionInfo(
                version=version,
                release_date=release_date,
                homepage_url=info.get("home_page") or info.get("project_url", ""),
                summary=info.get("summary", ""),
                source_url=f"https://pypi.org/project/{package_name}/{version}/",
                trust_level=100,  # Official PyPI API
                is_prerelease=is_prerelease,
                changelog_url=changelog_url,
            )
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self._log_debug(f"Package {package_name} not found on PyPI")
                return None
            self._log_error(f"HTTP error fetching {package_name}: {e}")
            raise
        
        except Exception as e:
            self._log_error(f"Error fetching {package_name}: {e}")
            raise
    
    def supports_package(self, package_name: str) -> bool:
        """
        Check if package exists on PyPI.
        
        Makes a lightweight HEAD request to check existence.
        """
        url = f"{self.BASE_URL}/{package_name}/json"
        
        try:
            response = requests.head(url, timeout=self.timeout)
            return response.status_code == 200
        except:
            return False
    
    def _parse_upload_time(self, upload_time: str) -> datetime.date:
        """
        Parse PyPI upload_time string to date.
        
        Format: "2024-02-22T12:00:00"
        """
        try:
            dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
            return dt.date()
        except Exception as e:
            self._log_error(f"Error parsing date '{upload_time}': {e}")
            # Fallback to today's date
            return datetime.now().date()
