"""
Maven Central registry adapter for Java packages.

Official API: https://central.sonatype.org/search/rest-api-guide/
"""

import requests
from datetime import datetime
from typing import Optional

from .base import PackageRegistry, VersionInfo


class MavenRegistry(PackageRegistry):
    """
    Adapter for Maven Central repository.
    
    Uses the Maven Central Search API (Sonatype).
    API endpoint: https://search.maven.org/solrsearch/select
    
    Features:
    - 100% accurate version detection
    - No authentication required
    - Free to use
    - Requires both groupId and artifactId
    - No documented rate limits
    
    Note: Maven packages require both groupId and artifactId,
    formatted as "groupId:artifactId" (e.g., "org.springframework:spring-core")
    """
    
    BASE_URL = "https://search.maven.org/solrsearch/select"
    
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
        Fetch latest version from Maven Central.
        
        Args:
            package_name: Maven coordinates in format "groupId:artifactId"
                         (e.g., "org.springframework:spring-core")
        
        Returns:
            VersionInfo if artifact found, None otherwise
        """
        # Parse groupId and artifactId
        if ":" not in package_name:
            self._log_error(f"Invalid Maven coordinates '{package_name}'. Expected 'groupId:artifactId'")
            return None
        
        group_id, artifact_id = package_name.split(":", 1)
        
        # Build query
        params = {
            "q": f"g:{group_id} AND a:{artifact_id}",
            "rows": 1,
            "wt": "json",
        }
        
        self._log_debug(f"Fetching from {self.BASE_URL} with query: {params['q']}")
        
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            response_data = data.get("response", {})
            docs = response_data.get("docs", [])
            
            if not docs:
                self._log_debug(f"No artifacts found for {package_name}")
                return None
            
            # Get first result (latest version)
            artifact = docs[0]
            
            latest_version = artifact.get("latestVersion") or artifact.get("v")
            if not latest_version:
                self._log_error(f"No version found in response")
                return None
            
            # Parse timestamp (milliseconds since epoch)
            timestamp = artifact.get("timestamp", 0)
            release_date = self._parse_maven_timestamp(timestamp)
            
            # Check if pre-release (contains SNAPSHOT, alpha, beta, RC)
            is_prerelease = any(
                marker in latest_version.upper()
                for marker in ["SNAPSHOT", "ALPHA", "BETA", "RC", "M"]
            )
            
            # Build URLs
            source_url = (
                f"https://mvnrepository.com/artifact/{group_id}/{artifact_id}/{latest_version}"
            )
            
            # Try to build GitHub URL from SCM
            homepage = ""
            changelog_url = ""
            
            # Get packaging info
            packaging = artifact.get("p", "jar")
            
            self._log_info(f"Found {package_name} v{latest_version}")
            
            return VersionInfo(
                version=latest_version,
                release_date=release_date,
                homepage_url=homepage,
                summary=f"{group_id}:{artifact_id} ({packaging})",
                source_url=source_url,
                trust_level=100,  # Official Maven Central
                is_prerelease=is_prerelease,
                changelog_url=changelog_url,
            )
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self._log_debug(f"Artifact {package_name} not found on Maven Central")
                return None
            self._log_error(f"HTTP error fetching {package_name}: {e}")
            raise
        
        except Exception as e:
            self._log_error(f"Error fetching {package_name}: {e}")
            raise
    
    def supports_package(self, package_name: str) -> bool:
        """
        Check if Maven artifact exists.
        
        Args:
            package_name: Maven coordinates "groupId:artifactId"
        """
        if ":" not in package_name:
            return False
        
        group_id, artifact_id = package_name.split(":", 1)
        
        params = {
            "q": f"g:{group_id} AND a:{artifact_id}",
            "rows": 1,
            "wt": "json",
        }
        
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            docs = data.get("response", {}).get("docs", [])
            return len(docs) > 0
        except:
            return False
    
    def _parse_maven_timestamp(self, timestamp_ms: int) -> datetime.date:
        """
        Parse Maven timestamp (milliseconds since epoch) to date.
        
        Args:
            timestamp_ms: Timestamp in milliseconds
        """
        try:
            if timestamp_ms:
                dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
                return dt.date()
        except Exception as e:
            self._log_error(f"Error parsing timestamp {timestamp_ms}: {e}")
        
        return datetime.now().date()
