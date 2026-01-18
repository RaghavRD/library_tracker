"""
Tests for VersionDetector orchestrator.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date

from tracker.utils.version_detector import VersionDetector
from tracker.utils.registry_adapters import VersionInfo


class TestVersionDetector:
    """Test VersionDetector orchestration logic."""
    
    @pytest.fixture
    def detector(self):
        """Create VersionDetector instance."""
        return VersionDetector(debug=True)
    
    def test_initialization(self, detector):
        """Test that all registries are initialized."""
        assert "pypi" in detector.registries
        assert "npm" in detector.registries
        assert "rubygems" in detector.registries
        assert "cargo" in detector.registries
        assert "nuget" in detector.registries
        assert "maven" in detector.registries
    
    def test_detect_pypi_package(self, detector):
        """Test detection of PyPI package."""
        result = detector.detect_version("requests")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
        assert "pypi.org" in result.source_url
    
    def test_detect_npm_package(self, detector):
        """Test detection of npm package."""
        # Use lodash instead of axios (axios exists on PyPI too)
        result = detector.detect_version("lodash", registry_hint="npm")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
        assert "npmjs.com" in result.source_url
    
    def test_detect_scoped_npm_package(self, detector):
        """Test auto-detection of scoped npm package."""
        result = detector.detect_version("@types/node")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
    
    def test_detect_rubygems_package(self, detector):
        """Test detection of RubyGems package."""
        result = detector.detect_version("rails", registry_hint="rubygems")
        
        assert result is not None
        assert result.version
        assert result.trust_level == 100
    
    def test_registry_hint(self, detector):
        """Test that registry hint is used."""
        # Provide hint for faster detection
        result = detector.detect_version("django", registry_hint="pypi")
        
        assert result is not None
        assert result.version
    
    def test_current_version_comparison(self, detector):
        """Test that current version is checked."""
        # Get actual latest version first
        latest = detector.detect_version("requests")
        
        # Try again with same version as current
        result = detector.detect_version("requests", current_version=latest.version)
        
        # Should return None (not newer)
        assert result is None
    
    def test_invalid_version_filtered(self, detector):
        """Test that invalid versions are filtered out."""
        # Mock a registry to return an invalid version
        mock_info = VersionInfo(
            version="2025.12.31",  # Date, not version
            release_date=date.today(),
            homepage_url="",
            summary="",
            source_url="",
            trust_level=100,
            is_prerelease=False,
        )
        
        with patch.object(detector.registries["pypi"], "get_latest_version", return_value=mock_info):
            result = detector.detect_version("fake-package", registry_hint="pypi")
            
            # Should be filtered out
            assert result is None


class TestRegistryAutoDetection:
    """Test auto-detection of registry types."""
    
    @pytest.fixture
    def detector(self):
        return VersionDetector()
    
    def test_detect_scoped_npm(self, detector):
        """Test scoped npm package detection."""
        registry = detector._detect_registry_from_name("@vue/cli")
        assert registry == "npm"
    
    def test_detect_maven_coordinates(self, detector):
        """Test Maven coordinates detection."""
        registry = detector._detect_registry_from_name("org.springframework:spring-core")
        assert registry == "maven"
    
    def test_no_pattern_match(self, detector):
        """Test package with no clear pattern."""
        registry = detector._detect_registry_from_name("pandas")
        assert registry is None  # Will try all registries
