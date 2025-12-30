"""
Version validation utilities.

Provides functions to validate semantic versions and filter out
common false positives like dates, IP addresses, and years.
"""

from packaging.version import parse as pkg_parse, InvalidVersion
import re
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class VersionValidator:
    """
    Validates and compares semantic version strings.
    
    Filters out common false positives:
    - Dates (2025.12.29)
    - Years (2024)
    - IP addresses (127.0.0.1)
    - Build numbers without proper semver format
    """
    
    @staticmethod
    def is_valid_semantic_version(version_str: str) -> bool:
        """
        Validate that a string is a proper semantic version.
        
        Args:
            version_str: Version string to validate
        
        Returns:
            True if valid semantic version, False otherwise
        
        Examples:
            >>> VersionValidator.is_valid_semantic_version("2.1.0")
            True
            >>> VersionValidator.is_valid_semantic_version("2025.12.29")
            False
            >>> VersionValidator.is_valid_semantic_version("127.0.0.1")
            False
        """
        if not version_str or not isinstance(version_str, str):
            return False
        
        try:
            # Must be parseable by packaging library
            parsed = pkg_parse(version_str)
            
            # Split into parts for additional validation
            # Remove pre-release and build metadata for analysis
            base_version = re.sub(r'[-+].*$', '', version_str)
            parts = base_version.split('.')
            
            # Must have at least major.minor
            if len(parts) < 2:
                logger.debug(f"Invalid: too few parts in '{version_str}'")
                return False
            
            # Check if first part looks like a year (2000-2100)
            try:
                major = int(parts[0])
                if 2000 <= major <= 2100:
                    logger.debug(f"Invalid: looks like a year '{version_str}'")
                    return False
            except ValueError:
                # Major version is not a number (e.g., "v1.2.3")
                pass
            
            # Check if it looks like a date (YYYY.MM.DD or YYYY.M.D)
            if len(parts) >= 3:
                try:
                    year, month, day_part = int(parts[0]), int(parts[1]), parts[2]
                    # Extract just the day number (might have -alpha etc)
                    day = int(re.match(r'(\d+)', day_part).group(1))
                    
                    if (1900 <= year <= 2100 and 
                        1 <= month <= 12 and 
                        1 <= day <= 31):
                        logger.debug(f"Invalid: looks like a date '{version_str}'")
                        return False
                except (ValueError, AttributeError):
                    pass
            
            # Check if it looks like an IP address
            if len(parts) == 4:
                try:
                    octets = [int(p) for p in parts]
                    if all(0 <= octet <= 255 for octet in octets):
                        logger.debug(f"Invalid: looks like an IP '{version_str}'")
                        return False
                except ValueError:
                    pass
            
            return True
            
        except InvalidVersion:
            logger.debug(f"Invalid: not parseable '{version_str}'")
            return False
        except Exception as e:
            logger.error(f"Error validating '{version_str}': {e}")
            return False
    
    @staticmethod
    def is_newer(new_version: str, current_version: str) -> bool:
        """
        Check if new_version is newer than current_version.
        
        Args:
            new_version: Version to check
            current_version: Current/existing version
        
        Returns:
            True if new_version > current_version
        
        Examples:
            >>> VersionValidator.is_newer("2.1.0", "2.0.0")
            True
            >>> VersionValidator.is_newer("2.0.0", "2.1.0")
            False
        """
        try:
            new = pkg_parse(new_version)
            current = pkg_parse(current_version)
            return new > current
        except InvalidVersion as e:
            logger.error(f"Invalid version comparison: '{new_version}' vs '{current_version}': {e}")
            return False
    
    @staticmethod
    def compare(version1: str, version2: str) -> int:
        """
        Compare two versions.
        
        Args:
            version1: First version
            version2: Second version
        
        Returns:
            -1 if version1 < version2
             0 if version1 == version2
             1 if version1 > version2
        
        Raises:
            InvalidVersion: If versions cannot be parsed
        """
        v1 = pkg_parse(version1)
        v2 = pkg_parse(version2)
        
        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
        else:
            return 0
    
    @staticmethod
    def normalize(version_str: str) -> Optional[str]:
        """
        Normalize a version string to canonical form.
        
        Args:
            version_str: Version string (may have 'v' prefix, etc.)
        
        Returns:
            Normalized version string, or None if invalid
        
        Examples:
            >>> VersionValidator.normalize("v2.1.0")
            "2.1.0"
            >>> VersionValidator.normalize("2.1")
            "2.1"
        """
        if not version_str:
            return None
        
        # Remove common prefixes
        cleaned = version_str.strip().lower()
        cleaned = re.sub(r'^v', '', cleaned)
        
        try:
            parsed = pkg_parse(cleaned)
            return str(parsed)
        except InvalidVersion:
            return None
