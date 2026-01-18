"""
Tests for registry adapter base classes and utilities.
"""

import pytest
from datetime import date
from tracker.utils.registry_adapters.base import VersionInfo, PackageRegistry


class TestVersionInfo:
    """Test VersionInfo dataclass."""
    
    def test_valid_version_info(self):
        """Test creating valid VersionInfo."""
        info = VersionInfo(
            version="2.1.0",
            release_date=date(2024, 2, 22),
            homepage_url="https://example.com",
            summary="Test package",
            source_url="https://pypi.org/project/test",
            trust_level=100,
            is_prerelease=False,
            changelog_url="https://example.com/changelog",
        )
        
        assert info.version == "2.1.0"
        assert info.trust_level == 100
        assert not info.is_prerelease
    
    def test_invalid_trust_level_too_high(self):
        """Test that trust_level > 100 raises error."""
        with pytest.raises(ValueError, match="trust_level must be 0-100"):
            VersionInfo(
                version="1.0.0",
                release_date=date(2024, 1, 1),
                homepage_url="",
                summary="",
                source_url="",
                trust_level=150,  # Invalid
                is_prerelease=False,
            )
    
    def test_invalid_trust_level_negative(self):
        """Test that negative trust_level raises error."""
        with pytest.raises(ValueError, match="trust_level must be 0-100"):
            VersionInfo(
                version="1.0.0",
                release_date=date(2024, 1, 1),
                homepage_url="",
                summary="",
                source_url="",
                trust_level=-10,  # Invalid
                is_prerelease=False,
            )


class DummyRegistry(PackageRegistry):
    """Dummy registry for testing abstract base class."""
    
    def get_latest_version(self, package_name):
        return None
    
    def supports_package(self, package_name):
        return True

    def get_prereleases(self, package_name):
        return []

    def get_repository_url(self, package_name):
        return "https://github.com/example/repo"


class TestPackageRegistry:
    """Test PackageRegistry base class."""
    
    def test_initialization(self):
        """Test registry initialization."""
        registry = DummyRegistry(timeout=15, debug=True)
        assert registry.timeout == 15
        assert registry.debug is True
    
    def test_default_timeout(self):
        """Test default timeout value."""
        registry = DummyRegistry()
        assert registry.timeout == 10
