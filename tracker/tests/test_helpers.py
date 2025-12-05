"""
Helper functions for testing LibTrack AI functionality.

This module provides utilities for:
1. Email content validation
2. Notification preference checking
3. Version comparison
4. Mock API response building
"""
import re
from typing import Dict, List, Any
from packaging import version as pkg_version


class EmailContentValidator:
    """Validates email content structure and required elements."""
    
    @staticmethod
    def validate_future_update_email(html_content: str) -> Dict[str, bool]:
        """
        Validate that future update email contains required elements.
        
        Returns:
            dict with validation results for each requirement
        """
        results = {
            'has_future_notice': 'Future Update Notice' in html_content,
            'has_confidence': 'confidence' in html_content.lower() or '%' in html_content,
            'has_planned_text': 'planned' in html_content.lower() or 'upcoming' in html_content.lower(),
            'has_not_released_warning': 'NOT been officially released' in html_content or 'not released' in html_content.lower(),
            'has_library_name': any(lib in html_content.lower() for lib in ['numpy', 'pandas', 'django', 'library']),
            'has_version': bool(re.search(r'\d+\.\d+', html_content)),
            'has_table': '<table' in html_content,
        }
        return results
    
    @staticmethod
    def validate_released_email(html_content: str) -> Dict[str, bool]:
        """
        Validate that released version email contains required elements.
        
        Returns:
            dict with validation results for each requirement
        """
        results = {
            'has_release_summary': 'Release Summary' in html_content or 'released' in html_content.lower(),
            'has_library_name': any(lib in html_content.lower() for lib in ['numpy', 'pandas', 'django', 'library']),
            'has_version': bool(re.search(r'\d+\.\d+', html_content)),
            'has_source_link': 'href=' in html_content,
            'has_table': '<table' in html_content,
            'no_future_notice': 'Future Update Notice' not in html_content,
        }
        return results
    
    @staticmethod
    def extract_confidence_from_email(html_content: str) -> int | None:
        """Extract confidence percentage from email HTML."""
        match = re.search(r'(\d+)%', html_content)
        return int(match.group(1)) if match else None
    
    @staticmethod
    def extract_version_from_email(html_content: str) -> str | None:
        """Extract version number from email HTML."""
        match = re.search(r'(\d+\.\d+(?:\.\d+)?)', html_content)
        return match.group(1) if match else None


class NotificationPreferenceChecker:
    """Utilities for checking notification preferences."""
    
    @staticmethod
    def should_notify_for_category(notify_pref: str, category: str) -> bool:
        """
        Determine if notification should be sent based on preference and category.
        
        Args:
            notify_pref: Comma-separated preference string (e.g., "major, minor, future")
            category: Update category ("major", "minor", "future")
        
        Returns:
            True if notification should be sent
        """
        prefs = [p.strip().lower() for p in notify_pref.split(',')]
        
        # Handle "both" legacy preference
        if 'both' in prefs:
            prefs.extend(['major', 'minor'])
        
        return category.lower() in prefs
    
    @staticmethod
    def parse_notification_types(notify_pref: str) -> List[str]:
        """Parse notification preference string into list of types."""
        if not notify_pref:
            return []
        
        prefs = [p.strip().lower() for p in notify_pref.split(',')]
        
        # Expand "both" to major and minor
        if 'both' in prefs:
            prefs.remove('both')
            prefs.extend(['major', 'minor'])
        
        return list(set(prefs))  # Remove duplicates
    
    @staticmethod
    def is_future_enabled(notify_pref: str) -> bool:
        """Check if future updates are enabled in preferences."""
        return 'future' in notify_pref.lower()


class VersionComparer:
    """Utilities for comparing version numbers."""
    
    @staticmethod
    def is_newer(new_version: str, current_version: str) -> bool:
        """
        Compare two version strings.
        
        Returns:
            True if new_version is newer than current_version
        """
        try:
            return pkg_version.parse(new_version) > pkg_version.parse(current_version)
        except Exception:
            # If parsing fails, do string comparison
            return new_version > current_version
    
    @staticmethod
    def parse_version(version_string: str) -> tuple | None:
        """Parse version string into comparable format."""
        try:
            parsed = pkg_version.parse(version_string)
            return parsed
        except Exception:
            return None
    
    @staticmethod
    def is_valid_version(version_string: str) -> bool:
        """Check if version string is valid."""
        try:
            pkg_version.parse(version_string)
            return True
        except Exception:
            return False


class MockAPIResponseBuilder:
    """Build mock API responses for testing."""
    
    @staticmethod
    def build_serper_response(
        library: str,
        version: str,
        is_future: bool = False,
        num_results: int = 3
    ) -> Dict[str, Any]:
        """
        Build a mock Serper API response.
        
        Args:
            library: Library name
            version: Version number
            is_future: Whether this is a future/planned release
            num_results: Number of search results to include
        
        Returns:
            Mock Serper API response dict
        """
        if is_future:
            results = [
                {
                    "title": f"{library} {version} Development Roadmap",
                    "link": f"https://{library.lower()}.org/roadmap",
                    "snippet": f"Planned features for {library} {version} include performance improvements and new APIs."
                },
                {
                    "title": f"Upcoming: {library} {version}",
                    "link": f"https://github.com/{library.lower()}/milestones/v{version}",
                    "snippet": f"Milestone for version {version}. Expected release Q2 2024."
                }
            ]
        else:
            results = [
                {
                    "title": f"{library} {version} Released",
                    "link": f"https://{library.lower()}.org/releases/{version}",
                    "snippet": f"Official release of {library} {version} with bug fixes and new features."
                },
                {
                    "title": f"What's New in {library} {version}",
                    "link": f"https://{library.lower()}.org/whatsnew/{version}",
                    "snippet": f"Detailed changelog for {library} version {version}."
                }
            ]
        
        return {"organic": results[:num_results]}
    
    @staticmethod
    def build_groq_analysis(
        library: str,
        version: str,
        category: str = "major",
        is_released: bool = True,
        confidence: int = 85
    ) -> Dict[str, Any]:
        """
        Build a mock Groq analysis response.
        
        Args:
            library: Library name
            version: Version number
            category: Update category
            is_released: Whether version is released
            confidence: Confidence percentage (0-100)
        
        Returns:
            Mock Groq analysis dict
        """
        from datetime import datetime, timedelta
        
        analysis = {
            "library": library,
            "version": version,
            "category": category,
            "is_released": is_released,
            "confidence": confidence,
            "summary": f"{'Released' if is_released else 'Planned'} version {version} with improvements.",
            "source": f"https://{library.lower()}.org/releases"
        }
        
        if is_released:
            analysis["release_date"] = datetime.now().strftime("%Y-%m-%d")
            analysis["expected_date"] = ""
        else:
            analysis["release_date"] = ""
            analysis["expected_date"] = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        
        return analysis


def validate_all_email_requirements(html_content: str, is_future: bool = False) -> bool:
    """
    Comprehensive validation of email content.
    
    Args:
        html_content: Email HTML content
        is_future: Whether this is a future update email
    
    Returns:
        True if all requirements are met
    """
    validator = EmailContentValidator()
    
    if is_future:
        results = validator.validate_future_update_email(html_content)
    else:
        results = validator.validate_released_email(html_content)
    
    return all(results.values())
