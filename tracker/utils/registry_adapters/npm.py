"""
npm (Node Package Manager) registry adapter.

Official API: https://github.com/npm/registry/blob/master/docs/REGISTRY-API.md
"""

import requests
import urllib.parse
from datetime import datetime
from typing import Optional

from .base import PackageRegistry, VersionInfo


class NpmRegistry(PackageRegistry):
    """
    Adapter for npm (Node Package Manager) registry.
    
    Uses the official npm registry API to fetch package information.
    API endpoint: https://registry.npmjs.org/{package}
    
    Features:
    - 100% accurate version detection
    - No authentication required
    - Free to use
    - Handles scoped packages (@vue/cli, @types/node)
    - No documented rate limits
    """
    
    BASE_URL = "https://registry.npmjs.org"
    
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
        Fetch latest version from npm registry.
        
        Args:
            package_name: npm package name (e.g., "react", "@vue/cli")
        
        Returns:
            VersionInfo if package found, None otherwise
        """
        # URL encode package name (important for scoped packages)
        encoded_name = urllib.parse.quote(package_name, safe='')
        url = f"{self.BASE_URL}/{encoded_name}"
        
        self._log_debug(f"Fetching from {url}")
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            # Check if package is deprecated
            if data.get("deprecated"):
                self._log_info(f"Package {package_name} is deprecated: {data['deprecated']}")
            
            # Get latest version from dist-tags
            dist_tags = data.get("dist-tags", {})
            latest_version = dist_tags.get("latest")
            
            if not latest_version:
                self._log_error(f"No 'latest' dist-tag for {package_name}")
                return None
            
            # Get version metadata
            versions = data.get("versions", {})
            version_data = versions.get(latest_version, {})
            
            if not version_data:
                self._log_error(f"No metadata for version {latest_version}")
                return None
            
            # Get release date from time object
            time_data = data.get("time", {})
            release_time = time_data.get(latest_version, "")
            release_date = self._parse_npm_time(release_time)
            
            # Check if pre-release (semver: contains hyphen)
            is_prerelease = "-" in latest_version
            
            # Get homepage
            homepage = (
                version_data.get("homepage") or
                data.get("homepage") or
                ""
            )
            
            # Get repository URL for changelog
            repository = version_data.get("repository", {})
            if isinstance(repository, dict):
                repo_url = repository.get("url", "")
            else:
                repo_url = str(repository)
            
            # Clean up git URLs
            changelog_url = self._extract_github_url(repo_url)
            
            self._log_info(f"Found {package_name} v{latest_version}")
            
            return VersionInfo(
                version=latest_version,
                release_date=release_date,
                homepage_url=homepage,
                summary=version_data.get("description", ""),
                source_url=f"https://www.npmjs.com/package/{package_name}/v/{latest_version}",
                trust_level=100,  # Official npm registry
                is_prerelease=is_prerelease,
                changelog_url=changelog_url,
            )
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self._log_debug(f"Package {package_name} not found on npm")
                return None
            self._log_error(f"HTTP error fetching {package_name}: {e}")
            raise
        
        except Exception as e:
            self._log_error(f"Error fetching {package_name}: {e}")
            raise
    
    def supports_package(self, package_name: str) -> bool:
        """
        Check if package exists on npm registry.
        
        Makes a lightweight HEAD request to check existence.
        """
        encoded_name = urllib.parse.quote(package_name, safe='')
        url = f"{self.BASE_URL}/{encoded_name}"
        
        try:
            response = requests.head(url, timeout=self.timeout)
            return response.status_code == 200
        except:
            return False
    
    def _parse_npm_time(self, time_str: str) -> datetime.date:
        """
        Parse npm time string to date.
        
        Format: "2024-02-22T14:30:00.000Z"
        """
        try:
            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            return dt.date()
        except Exception as e:
            self._log_error(f"Error parsing date '{time_str}': {e}")
            return datetime.now().date()
    
    def _extract_github_url(self, repo_url: str) -> str:
        """
        Extract clean GitHub URL from repository field.
        
        Converts:
        - "git+https://github.com/facebook/react.git"
        - "git://github.com/facebook/react.git"
        To:
        - "https://github.com/facebook/react"
        """
        if not repo_url:
            return ""
        
        # Remove git+ prefix
        url = repo_url.replace("git+", "")
        
        # Replace git:// with https://
        url = url.replace("git://", "https://")
        
        # Remove .git suffix
        url = url.rstrip("/").removesuffix(".git")
        
        return url
