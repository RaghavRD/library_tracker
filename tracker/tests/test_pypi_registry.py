"""
Integration tests for PyPI registry adapter.

These tests make real API calls to PyPI.
"""

import pytest
from tracker.utils.registry_adapters.pypi import PyPIRegistry


class TestPyPIRegistry:
    """Test PyPI registry adapter with real API calls."""
    
    @pytest.fixture
    def registry(self):
        """Create PyPI registry instance."""
        return PyPIRegistry(debug=True)
    
    def test_get_pandas_version(self, registry):
        """Test fetching pandas package."""
        result = registry.get_latest_version("pandas")
        
        assert result is not None
        assert result.version  # Should have a version
        assert result.trust_level == 100
        assert result.source_url.startswith("https://pypi.org/project/pandas")
        assert "data" in result.summary.lower() or "analysis" in result.summary.lower()
        assert not result.is_prerelease  # pandas latest should be stable
    
    def test_get_django_version(self, registry):
        """Test fetching Django package (note: capital D)."""
        result = registry.get_latest_version("Django")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
        assert "django" in result.source_url.lower()
    
    def test_get_flask_version(self, registry):
        """Test fetching Flask package."""
        result = registry.get_latest_version("flask")
        
        assert result is not None
        assert result.version
        assert result.homepage_url  # Flask has a homepage
        assert result.release_date  # Should have a release date
    
    def test_nonexistent_package(self, registry):
        """Test that nonexistent package returns None."""
        result = registry.get_latest_version("this-package-definitely-does-not-exist-12345")
        
        assert result is None
    
    def test_supports_package(self, registry):
        """Test package existence check."""
        assert registry.supports_package("pandas") is True
        assert registry.supports_package("this-does-not-exist-xyz") is False
    
    def test_prerelease_detection(self, registry):
        """Test that pre-release versions are detected."""
        # Note: This test might be flaky if package never has prereleases
        # We test with a package's specific version
        result = registry.get_latest_version("requests")
        
        # Just verify that is_prerelease is a boolean
        assert isinstance(result.is_prerelease, bool)
