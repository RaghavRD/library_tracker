"""
Integration tests for npm registry adapter.

These tests make real API calls to npm registry.
"""

import pytest
from tracker.utils.registry_adapters.npm import NpmRegistry


class TestNpmRegistry:
    """Test npm registry adapter with real API calls."""
    
    @pytest.fixture
    def registry(self):
        """Create npm registry instance."""
        return NpmRegistry(debug=True)
    
    def test_get_react_version(self, registry):
        """Test fetching react package."""
        result = registry.get_latest_version("react")
        
        assert result is not None
        assert result.version  # Should have a version
        assert result.trust_level == 100
        assert result.source_url.startswith("https://www.npmjs.com/package/react")
        assert not result.is_prerelease  # react latest should be stable
    
    def test_get_express_version(self, registry):
        """Test fetching express package."""
        result = registry.get_latest_version("express")
        
        assert result is not None
        assert result.version
        assert result.summary  # Express has a description
        assert result.trust_level == 100
    
    def test_scoped_package(self, registry):
        """Test fetching scoped package (@vue/cli)."""
        result = registry.get_latest_version("@vue/cli")
        
        assert result is not None
        assert result.version
        assert "@vue/cli" in result.source_url
    
    def test_scoped_types_package(self, registry):
        """Test fetching @types/* package."""
        result = registry.get_latest_version("@types/node")
        
        assert result is not None
        assert result.version
        assert "@types/node" in result.source_url
    
    def test_nonexistent_package(self, registry):
        """Test that nonexistent package returns None."""
        result = registry.get_latest_version("this-npm-package-does-not-exist-xyz123")
        
        assert result is None
    
    def test_supports_package(self, registry):
        """Test package existence check."""
        assert registry.supports_package("react") is True
        assert registry.supports_package("nonexistent-pkg-xyz") is False
    
    def test_prerelease_detection(self, registry):
        """Test pre-release version detection (semver with hyphen)."""
        result = registry.get_latest_version("axios")
        
        # is_prerelease should be a boolean
        assert isinstance(result.is_prerelease, bool)
        
        # If version has a hyphen, it should be marked as prerelease
        if "-" in result.version:
            assert result.is_prerelease is True
        else:
            assert result.is_prerelease is False
