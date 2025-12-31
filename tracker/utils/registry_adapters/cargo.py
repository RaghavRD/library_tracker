"""
Cargo (crates.io) registry adapter for Rust packages.

Official API: https://crates.io/data-access
"""

import requests
from datetime import datetime
from typing import Optional, List

from .base import PackageRegistry, VersionInfo, PreReleaseInfo


class CargoRegistry(PackageRegistry):
    """
    Adapter for crates.io (Rust package registry).
    
    Uses the official crates.io API to fetch crate information.
    API endpoint: https://crates.io/api/v1/crates/{crate}
    
    Features:
    - 100% accurate version detection
    - Requires User-Agent header (crates.io policy)
    - Free to use
    - Rate limit: 1 req/sec (burst: 10 req/10sec)
    """
    
    BASE_URL = "https://crates.io/api/v1"
    USER_AGENT = "LibTrack-AI/1.0 (https://github.com/RaghavRD/library_tracker)"
    
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
        Fetch latest version from crates.io.
        
        Args:
            package_name: Rust crate name (e.g., "serde", "tokio")
        
        Returns:
            VersionInfo if crate found, None otherwise
        """
        url = f"{self.BASE_URL}/crates/{package_name}"
        headers = {"User-Agent": self.USER_AGENT}
        
        self._log_debug(f"Fetching from {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            crate = data.get("crate", {})
            if not crate:
                self._log_error(f"No crate data for {package_name}")
                return None
            
            # Get latest version
            newest_version = crate.get("newest_version")
            if not newest_version:
                self._log_error(f"No newest_version for {package_name}")
                return None
            
            # Get version details
            versions = data.get("versions", [])
            latest_version_data = None
            
            for v in versions:
                if v.get("num") == newest_version:
                    latest_version_data = v
                    break
            
            if not latest_version_data:
                self._log_error(f"Version data not found for {newest_version}")
                return None
            
            # Parse release date
            created_at = latest_version_data.get("created_at", "")
            release_date = self._parse_cargo_date(created_at)
            
            # Check if pre-release (yanked or has pre-release suffix)
            is_yanked = latest_version_data.get("yanked", False)
            is_prerelease = "-" in newest_version or is_yanked
            
            # Get homepage and repository
            homepage = crate.get("homepage") or crate.get("repository", "")
            repository = crate.get("repository", "")
            
            # Build changelog URL (often in repository)
            changelog_url = ""
            if repository and "github.com" in repository:
                changelog_url = f"{repository}/releases"
            
            self._log_info(f"Found {package_name} v{newest_version}")
            
            return VersionInfo(
                version=newest_version,
                release_date=release_date,
                homepage_url=homepage,
                summary=crate.get("description", ""),
                source_url=f"https://crates.io/crates/{package_name}/{newest_version}",
                trust_level=100,  # Official crates.io API
                is_prerelease=is_prerelease,
                changelog_url=changelog_url,
            )
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self._log_debug(f"Crate {package_name} not found on crates.io")
                return None
            self._log_error(f"HTTP error fetching {package_name}: {e}")
            raise
        
        except Exception as e:
            self._log_error(f"Error fetching {package_name}: {e}")
            raise
    
    def get_prereleases(self, package_name: str) -> List[PreReleaseInfo]:
        """Get pre-releases from crates.io."""
        url = f"{self.BASE_URL}/{package_name}"
        headers = {"User-Agent": self.USER_AGENT}
        
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            if response.status_code != 200: return []
            
            data = response.json()
            versions = data.get("versions", [])
            prereleases = []
            
            for v in versions:
                # Rust uses SemVer. Pre-releases have a hyphen.
                if "-" in v.get("num", "") and not v.get("yanked"):
                    prereleases.append(PreReleaseInfo(
                        version=v["num"],
                        release_date=self._parse_crate_time(v.get("created_at", "")),
                        prerelease_type="pre", # Simplified
                        summary=f"Crate version {v['num']}",
                        source_url=f"https://crates.io/crates/{package_name}/{v['num']}",
                        trust_level=95,
                        is_published=True
                    ))
            return prereleases
        except Exception:
            return []

    def get_repository_url(self, package_name: str) -> Optional[str]:
        # TODO: Implement Cargo repository extraction
        return None

    def supports_package(self, package_name: str) -> bool:
        """
        Check if crate exists on crates.io.
        
        Makes a lightweight HEAD request.
        """
        url = f"{self.BASE_URL}/crates/{package_name}"
        headers = {"User-Agent": self.USER_AGENT}
        
        try:
            response = requests.head(url, headers=headers, timeout=self.timeout)
            return response.status_code == 200
        except:
            return False
    
    def _parse_cargo_date(self, date_str: str) -> datetime.date:
        """
        Parse crates.io date string to date.
        
        Format: "2024-02-22T14:30:00.123456+00:00"
        """
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.date()
        except Exception as e:
            self._log_error(f"Error parsing date '{date_str}': {e}")
            return datetime.now().date()
