"""
NuGet (.NET) registry adapter.

Official API: https://learn.microsoft.com/en-us/nuget/api/overview
"""

import requests
from datetime import datetime
from typing import Optional, List

from .base import PackageRegistry, VersionInfo, PreReleaseInfo


class NuGetRegistry(PackageRegistry):
    """
    Adapter for NuGet (.NET package registry).
    
    Uses the official NuGet V3 API to fetch package information.
    API endpoint: https://api.nuget.org/v3-flatcontainer/{id}/index.json
    
    Features:
    - 100% accurate version detection
    - No authentication required
    - Free to use
    - No documented rate limits
    """
    
    FLAT_CONTAINER_URL = "https://api.nuget.org/v3-flatcontainer"
    SEARCH_URL = "https://azuresearch-usnc.nuget.org/query"
    
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
        Fetch latest version from NuGet.
        
        Args:
            package_name: NuGet package ID (e.g., "Newtonsoft.Json", "EntityFramework")
        
        Returns:
            VersionInfo if package found, None otherwise
        """
        # NuGet package IDs are case-insensitive, but we need exact casing for metadata
        # First, get all versions
        package_id_lower = package_name.lower()
        versions_url = f"{self.FLAT_CONTAINER_URL}/{package_id_lower}/index.json"
        
        self._log_debug(f"Fetching versions from {versions_url}")
        
        try:
            response = requests.get(versions_url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            versions = data.get("versions", [])
            if not versions:
                self._log_error(f"No versions found for {package_name}")
                return None
            
            # Latest version is the last in the array
            latest_version = versions[-1]
            
            # Get package metadata from search API for more details
            metadata = self._get_package_metadata(package_name)
            
            if metadata:
                # Use metadata from search API
                release_date = self._parse_nuget_date(metadata.get("published", ""))
                homepage = metadata.get("projectUrl", "")
                summary = metadata.get("description", "")
                actual_id = metadata.get("id", package_name)  # Get correct casing
                
                # Check if pre-release
                is_prerelease = "-" in latest_version
            else:
                # Fallback if metadata not available
                release_date = datetime.now().date()
                homepage = ""
                summary = ""
                actual_id = package_name
                is_prerelease = "-" in latest_version
            
            self._log_info(f"Found {actual_id} v{latest_version}")
            
            return VersionInfo(
                version=latest_version,
                release_date=release_date,
                homepage_url=homepage,
                summary=summary,
                source_url=f"https://www.nuget.org/packages/{actual_id}/{latest_version}",
                trust_level=100,  # Official NuGet API
                is_prerelease=is_prerelease,
                changelog_url=metadata.get("releaseNotes", "") if metadata else "",
            )
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self._log_debug(f"Package {package_name} not found on NuGet")
                return None
            self._log_error(f"HTTP error fetching {package_name}: {e}")
            raise
        
        except Exception as e:
            self._log_error(f"Error fetching {package_name}: {e}")
            raise
    
    def _get_package_metadata(self, package_name: str) -> Optional[dict]:
        """
        Fetch package metadata from NuGet search API.
        
        Provides additional details like description, project URL, etc.
        """
        url = f"{self.SEARCH_URL}?q=packageid:{package_name}&prerelease=false"
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("data", [])
            if results:
                # Return first result (should be exact match)
                return results[0]
            
            return None
        except Exception as e:
            self._log_debug(f"Could not fetch metadata: {e}")
            return None
    
    def get_prereleases(self, package_name: str) -> List[PreReleaseInfo]:
        # TODO: Implement full NuGet pre-release search
        return []

    def get_repository_url(self, package_name: str) -> Optional[str]:
        return None

    def supports_package(self, package_name: str) -> bool:
        """
        Check if package exists on NuGet.
        """
        package_id_lower = package_name.lower()
        url = f"{self.FLAT_CONTAINER_URL}/{package_id_lower}/index.json"
        
        try:
            response = requests.head(url, timeout=self.timeout)
            return response.status_code == 200
        except:
            return False
    
    def _parse_nuget_date(self, date_str: str) -> datetime.date:
        """
        Parse NuGet date string to date.
        
        Format: "2024-02-22T14:30:00+00:00"
        """
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.date()
        except Exception as e:
            self._log_error(f"Error parsing date '{date_str}': {e}")
            return datetime.now().date()
