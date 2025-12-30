"""
Tests for version validation utilities.
"""

import pytest
from tracker.utils.version_validator import VersionValidator


class TestVersionValidator:
    """Test VersionValidator class."""
    
    def test_valid_semantic_versions(self):
        """Test that valid semantic versions pass validation."""
        valid_versions = [
            "1.0.0",
            "2.1.3",
            "0.0.1",
            "1.0.0-alpha",
            "1.0.0-beta.1",
            "1.0.0-rc.2",
            "1.2.3-alpha.1+build.123",
            "10.20.30",
        ]
        
        for version in valid_versions:
            assert VersionValidator.is_valid_semantic_version(version), \
                f"Version '{version}' should be valid"
    
    def test_reject_dates(self):
        """Test that date strings are rejected."""
        date_strings = [
            "2025.12.29",
            "2024.01.15",
            "2023.5.1",
        ]
        
        for date_str in date_strings:
            assert not VersionValidator.is_valid_semantic_version(date_str), \
                f"Date '{date_str}' should be rejected"
    
    def test_reject_years(self):
        """Test that year-only strings are rejected."""
        years = [
            "2024",
            "2025",
            "2023.1",
        ]
        
        for year in years:
            assert not VersionValidator.is_valid_semantic_version(year), \
                f"Year '{year}' should be rejected"
    
    def test_reject_ip_addresses(self):
        """Test that IP addresses are rejected."""
        ips = [
            "127.0.0.1",
            "192.168.1.1",
            "10.0.0.255",
        ]
        
        for ip in ips:
            assert not VersionValidator.is_valid_semantic_version(ip), \
                f"IP '{ip}' should be rejected"
    
    def test_reject_invalid_formats(self):
        """Test that invalid formats are rejected."""
        invalid = [
            "",
            "abc",
            "1",
            "1.",
            ".1.0",
            "v",
        ]
        
        for version in invalid:
            assert not VersionValidator.is_valid_semantic_version(version), \
                f"Invalid '{version}' should be rejected"
    
    def test_is_newer(self):
        """Test version comparison."""
        assert VersionValidator.is_newer("2.0.0", "1.0.0")
        assert VersionValidator.is_newer("1.1.0", "1.0.0")
        assert VersionValidator.is_newer("1.0.1", "1.0.0")
        assert not VersionValidator.is_newer("1.0.0", "2.0.0")
        assert not VersionValidator.is_newer("1.0.0", "1.0.0")
    
    def test_compare(self):
        """Test version comparison."""
        assert VersionValidator.compare("2.0.0", "1.0.0") == 1
        assert VersionValidator.compare("1.0.0", "2.0.0") == -1
        assert VersionValidator.compare("1.0.0", "1.0.0") == 0
    
    def test_normalize(self):
        """Test version normalization."""
        assert VersionValidator.normalize("v2.1.0") == "2.1.0"
        assert VersionValidator.normalize("V1.0.0") == "1.0.0"
        assert VersionValidator.normalize("  2.0.0  ") == "2.0.0"
        assert VersionValidator.normalize("invalid") is None
