"""
Integration tests for all remaining registry adapters.

Tests RubyGems, Cargo, NuGet, and Maven with real API calls.
"""

import pytest
from tracker.utils.registry_adapters.rubygems import RubyGemsRegistry
from tracker.utils.registry_adapters.cargo import CargoRegistry
from tracker.utils.registry_adapters.nuget import NuGetRegistry
from tracker.utils.registry_adapters.maven import MavenRegistry


class TestRubyGemsRegistry:
    """Test RubyGems registry adapter with real API calls."""
    
    @pytest.fixture
    def registry(self):
        return RubyGemsRegistry(debug=True)
    
    def test_get_rails_version(self, registry):
        """Test fetching rails gem."""
        result = registry.get_latest_version("rails")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
        assert "rubygems.org" in result.source_url
    
    def test_nonexistent_gem(self, registry):
        """Test that nonexistent gem returns None."""
        result = registry.get_latest_version("this-gem-does-not-exist-xyz123")
        assert result is None


class TestCargoRegistry:
    """Test Cargo/crates.io registry adapter with real API calls."""
    
    @pytest.fixture
    def registry(self):
        return CargoRegistry(debug=True)
    
    def test_get_serde_version(self, registry):
        """Test fetching serde crate."""
        result = registry.get_latest_version("serde")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
        assert "crates.io" in result.source_url
    
    def test_nonexistent_crate(self, registry):
        """Test that nonexistent crate returns None."""
        result = registry.get_latest_version("this-crate-does-not-exist-xyz123")
        assert result is None


class TestNuGetRegistry:
    """Test NuGet registry adapter with real API calls."""
    
    @pytest.fixture
    def registry(self):
        return NuGetRegistry(debug=True)
    
    def test_get_newtonsoft_json_version(self, registry):
        """Test fetching Newtonsoft.Json package."""
        result = registry.get_latest_version("Newtonsoft.Json")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
        assert "nuget.org" in result.source_url
    
    def test_nonexistent_package(self, registry):
        """Test that nonexistent package returns None."""
        result = registry.get_latest_version("ThisPackageDoesNotExist12345")
        assert result is None


class TestMavenRegistry:
    """Test Maven Central registry adapter with real API calls."""
    
    @pytest.fixture
    def registry(self):
        return MavenRegistry(debug=True)
    
    def test_get_spring_core_version(self, registry):
        """Test fetching spring-core artifact."""
        result = registry.get_latest_version("org.springframework:spring-core")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
        assert "mvnrepository.com" in result.source_url
    
    def test_invalid_coordinates(self, registry):
        """Test that invalid coordinates return None."""
        result = registry.get_latest_version("invalid-no-colon")
        assert result is None
    
    def test_nonexistent_artifact(self, registry):
        """Test that nonexistent artifact returns None."""
        result = registry.get_latest_version("com.nonexistent:artifact123")
        assert result is None
