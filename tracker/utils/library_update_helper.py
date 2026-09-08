"""
Integration helper for VersionDetector in run_daily_check command.

This module provides a wrapper to use VersionDetector with the existing
LibTrack AI command structure.
"""

import os
import logging
from typing import Optional, Dict, Any

from django.utils import timezone

from tracker.utils.version_detector import VersionDetector
from tracker.utils.registry_adapters import VersionInfo
from tracker.models import Library, LibraryRelease

logger = logging.getLogger('libtrack')


class LibraryUpdateHelper:
    """
    Helper class to update libraries using VersionDetector.
    
    Provides a bridge between the new VersionDetector system and the
    existing run_daily_check command structure.
    """
    
    def __init__(self, use_official_apis: bool = True, debug: bool = False):
        """
        Initialize the helper.
        
        Args:
            use_official_apis: Whether to use official APIs (vs Serper+Groq)
            debug: Enable debug logging
        """
        self.use_official_apis = use_official_apis
        self.debug = debug
        
        if use_official_apis:
            self.detector = VersionDetector(timeout=10, debug=debug)
        else:
            self.detector = None
    
    def detect(
        self,
        name: str,
        component_type: str = "library",
        current_version: Optional[str] = None,
        registry_hint: Optional[str] = None,
    ) -> Optional[VersionInfo]:
        """
        Detect the latest version for a package. Network only, no database access.

        Kept free of ORM calls so it can be run from a thread pool: Django
        connections are per-thread, and mixing model writes into worker threads
        would mean managing a connection per worker for no gain.

        Raises whatever the detector raises; callers decide how to record it.
        """
        if not self.use_official_apis or not self.detector:
            return None

        return self.detector.detect_version(
            library_name=name,
            component_type=component_type,
            current_version=current_version,
            registry_hint=registry_hint,
        )

    def apply(
        self,
        library: Library,
        version_info: VersionInfo,
        stdout_writer=None,
    ) -> Dict[str, Any]:
        """
        Persist an already-detected version. Database only, no network access.

        Args:
            library: Library model instance to update
            version_info: Result of a previous :meth:`detect` call
            stdout_writer: Optional writer for console output

        Returns:
            Dict with update information
        """
        library.latest_version = version_info.version
        library.last_checked_at = timezone.now()

        # Store detection metadata if fields exist
        if hasattr(library, 'detection_trust_level'):
            library.detection_trust_level = version_info.trust_level
        if hasattr(library, 'last_api_call_successful'):
            library.last_api_call_successful = True
            library.api_error_message = ""

        library.save()

        # Create or update LibraryRelease
        release, created = LibraryRelease.objects.get_or_create(
            library=library,
            version=version_info.version,
            defaults={
                "release_date": version_info.release_date,
                "summary": version_info.summary,
                "source_url": version_info.source_url,
                "is_security_release": False,
            }
        )

        if not created:
            # Update existing release
            release.summary = version_info.summary
            release.source_url = version_info.source_url
            release.release_date = version_info.release_date

            # Store detection source if field exists
            if hasattr(release, 'detection_source'):
                release.detection_source = f"api:trust_{version_info.trust_level}"

            release.save()

        if stdout_writer:
            stdout_writer(
                f"✅ Found v{version_info.version} "
                f"(trust: {version_info.trust_level}%) "
                f"from {version_info.source_url[:50]}..."
            )

        return {
            "version": version_info.version,
            "trust_level": version_info.trust_level,
            "source_url": version_info.source_url,
            "updated": True,
        }

    def record_failure(self, library: Library, error: Exception):
        """Persist a failed detection attempt against the library."""
        if hasattr(library, 'last_api_call_successful'):
            library.last_api_call_successful = False
        if hasattr(library, 'api_error_message'):
            library.api_error_message = str(error)[:500]
            library.save()

    def update_library(
        self,
        library: Library,
        stdout_writer=None
    ) -> Optional[Dict[str, Any]]:
        """
        Detect and persist a single library in one call.

        Convenience wrapper over :meth:`detect` and :meth:`apply` for callers
        that are not running detection concurrently.
        """
        if not self.use_official_apis or not self.detector:
            return None

        try:
            version_info = self.detect(
                name=library.name,
                component_type=library.component_type,
                current_version=library.latest_version,
                registry_hint=getattr(library, 'registry_type', None),
            )

            if not version_info:
                if stdout_writer:
                    stdout_writer(f"ℹ️  No updates found")
                return None

            return self.apply(library, version_info, stdout_writer=stdout_writer)

        except Exception as e:
            logger.error(f"Error updating {library.name} with VersionDetector: {e}", exc_info=True)
            self.record_failure(library, e)

            if stdout_writer:
                stdout_writer(f"❌ Error: {str(e)[:100]}")

            return None
