"""
Base classes and data structures for package registry adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """
    Standardized version information returned by all registry adapters.
    
    Attributes:
        version: Semantic version string (e.g., "2.2.1")
        release_date: Date when this version was released
        homepage_url: Project homepage URL
        summary: Brief description of the package/library
        source_url: URL to the source where this info was fetched
        trust_level: Confidence level 0-100 (100 = official registry API)
        is_prerelease: Whether this is a pre-release version (alpha, beta, rc)
        changelog_url: Optional URL to changelog/release notes
    """
    version: str
    release_date: date
    homepage_url: str
    summary: str
    source_url: str
    trust_level: int
    is_prerelease: bool
    changelog_url: Optional[str] = None
    
    def __post_init__(self):
        """Validate trust level range."""
        if not 0 <= self.trust_level <= 100:
            raise ValueError(f"trust_level must be 0-100, got {self.trust_level}")


class PackageRegistry(ABC):
    """
    Abstract base class for package manager registry adapters.
    
    Each registry (PyPI, npm, RubyGems, etc.) should implement this interface
    to provide a consistent way to fetch version information.
    """
    
    def __init__(self, timeout: int = 10, debug: bool = False):
        """
        Initialize registry adapter.
        
        Args:
            timeout: HTTP request timeout in seconds
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        
        if self.debug:
            logger.setLevel(logging.DEBUG)
    
    @abstractmethod
    def get_latest_version(self, package_name: str) -> Optional[VersionInfo]:
        """
        Fetch the latest stable version of a package.
        
        Args:
            package_name: Name of the package (e.g., "pandas", "react")
        
        Returns:
            VersionInfo object if found, None if package doesn't exist
        
        Raises:
            requests.RequestException: For network/API errors
            ValueError: For invalid package names
        """
        pass
    
    @abstractmethod
    def supports_package(self, package_name: str) -> bool:
        """
        Check if this registry can handle the given package.
        
        Args:
            package_name: Name of the package
        
        Returns:
            True if this registry supports this package
        """
        pass
    
    def _log_debug(self, message: str):
        """Log debug message if debug mode enabled."""
        if self.debug:
            logger.debug(f"[{self.__class__.__name__}] {message}")
    
    def _log_info(self, message: str):
        """Log info message."""
        logger.info(f"[{self.__class__.__name__}] {message}")
    
    def _log_error(self, message: str):
        """Log error message."""
        logger.error(f"[{self.__class__.__name__}] {message}")
