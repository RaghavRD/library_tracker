"""
VersionFetchService: Fetches the latest version info for libraries.

Purpose:
  Queries official registries (npm, pypi, etc.) to get the latest stable version.
  Falls back to Serper + Groq web search if official APIs fail or are disabled.

Workflow:
  1. For each unique Library, determine its registry type
  2. Call official API (via LibraryUpdateHelper) if enabled
  3. Fall back to Serper + Groq if official API fails
  4. Parse and save version info to Library and LibraryRelease records
"""

import logging
import time
from datetime import datetime
from django.conf import settings
from packaging import version as pkg_version
from packaging.version import InvalidVersion

from tracker.models import Library, LibraryRelease
from tracker.utils.library_update_helper import LibraryUpdateHelper
from tracker.utils.groq_analyzer import GroqAnalyzer
from tracker.utils.serper_fetcher import SerperFetcher

logger = logging.getLogger(__name__)


class VersionFetchService:
    """
    Handles version detection and update for Library records.
    Coordinates between official APIs and fallback Serper+Groq approach.
    """

    def __init__(self, use_official_apis: bool = True, debug: bool = False):
        """
        Initialize the version fetch service.

        Args:
            use_official_apis: If True, use official registry APIs; else fall back to Serper+Groq
            debug: If True, enable verbose logging
        """
        self.use_official_apis = use_official_apis
        self.debug = debug
        self.updated_count = 0
        self.skipped_count = 0
        self.error_count = 0

        # Initialize tools
        if use_official_apis:
            self.helper = LibraryUpdateHelper(use_official_apis=True, debug=debug)
            self.groq = None
            self.serper = None
        else:
            self.helper = None
            self.groq = GroqAnalyzer()
            self.serper = SerperFetcher()

    def fetch_all_libraries(self, stdout_writer=None, owner=None):
        """
        Fetch updates for all unique libraries.

        Args:
            stdout_writer: Optional callable to write status updates

        Returns:
            dict: Summary with counts of updated, skipped, and errored libraries
        """
        self._log(stdout_writer, "Starting version fetch for all libraries...")

        # Get all libraries that are actively used (linked to at least one component)
        libraries = Library.objects.filter(linked_components__isnull=False)
        if owner is not None:
            libraries = libraries.filter(linked_components__project__owner=owner)
        libraries = libraries.distinct()
        count = libraries.count()
        self._log(stdout_writer, f"Fetching {count} unique libraries...")

        for library in libraries:
            self._fetch_library(library, stdout_writer)
            # Rate limiting between requests (configurable)
            rate_limit = getattr(settings, "LIBTRACK_API_RATE_LIMIT_SECONDS", 1.5)
            time.sleep(rate_limit)

        summary = {
            "checked_count": count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
        }
        self._log(
            stdout_writer,
            f"✅ Fetch complete: {self.updated_count} updated, "
            f"{self.skipped_count} skipped, {self.error_count} errors.",
        )
        return summary

    def _fetch_library(self, library: Library, stdout_writer=None):
        """
        Fetch version info for a single library.

        Args:
            library: Library instance to update
            stdout_writer: Optional callable for logging
        """
        self._log(
            stdout_writer,
            f"Checking {library.name} (current: v{library.latest_version or 'unknown'})...",
        )

        # Infer registry type if not set
        if not library.registry_type:
            library.registry_type = self._infer_registry_type(library)
            library.save(update_fields=["registry_type"])

        try:
            # Try official API first
            if self.use_official_apis and self.helper:
                result = self.helper.update_library(
                    library, stdout_writer=stdout_writer
                )
                if result:
                    log_detection = getattr(settings, "LIBTRACK_LOG_DETECTION_METHOD", True)
                    if log_detection:
                        logger.info(
                            f"Version detected for {library.name}: v{library.latest_version}, "
                            f"detection_method=registry_api, registry_type={library.registry_type}"
                        )
                    self.updated_count += 1
                else:
                    self._log(stdout_writer, "ℹ️  No updates found")
                    self.skipped_count += 1
                fallback_rate = getattr(settings, "LIBTRACK_API_RATE_LIMIT_SECONDS", 1.5)
                time.sleep(fallback_rate)
                return

        except Exception as e:
            self._log(
                stdout_writer,
                f"❌ Official API error: {e}. Falling back to Serper+Groq...",
            )
            logger.error(f"Official API error for {library.name}: {e}", exc_info=True)
            # Fall through to Serper+Groq fallback

        # Fallback: Serper + Groq
        self._fetch_with_serper_groq(library, stdout_writer)
        fallback_rate_limit = getattr(settings, "LIBTRACK_API_RATE_LIMIT_SECONDS", 1.5)
        time.sleep(fallback_rate_limit)

    def _fetch_with_serper_groq(self, library: Library, stdout_writer=None):
        """
        Fetch version using Serper web search + Groq analysis.

        Args:
            library: Library instance to update
            stdout_writer: Optional callable for logging
        """
        try:
            # Run web search
            serper_results = self.serper.search_library(
                library.name,
                library.latest_version or "0.0.0",
                component_type=library.component_type,
            )

            # Analyze with Groq
            analysis = self.groq.analyze(library.name, serper_results)

            if analysis.get("error"):
                self._log(stdout_writer, f"⚠️  Groq error: {analysis['error']}")
                self.error_count += 1
                return

            # Extract detected version
            detected_version = analysis.get("version", "")
            if not detected_version:
                self._log(stdout_writer, "ℹ️  No version detected")
                self.skipped_count += 1
                return

            # Skip if it's a future version (not released yet)
            if analysis.get("category") == "future" or not analysis.get("is_released"):
                self._log(
                    stdout_writer,
                    f"ℹ️  Future version detected: {detected_version}. "
                    "Skipping stable update.",
                )
                self.skipped_count += 1
                return

            # Check if detected version is actually newer
            if not self._should_update_version(
                library.latest_version, detected_version, stdout_writer
            ):
                self.skipped_count += 1
                return

            # Save the new version
            self._save_library_version(
                library,
                detected_version,
                analysis,
                stdout_writer,
            )
            log_detection = getattr(settings, "LIBTRACK_LOG_DETECTION_METHOD", True)
            if log_detection:
                logger.info(
                    f"Version detected for {library.name}: v{detected_version}, "
                    f"detection_method=serper_groq, category={analysis.get('category')}"
                )
            self.updated_count += 1

        except Exception as e:
            self._log(stdout_writer, f"❌ Serper+Groq error: {e}")
            logger.error(f"Serper+Groq error for {library.name}: {e}", exc_info=True)
            self.error_count += 1

    def _should_update_version(
        self, current_version: str, detected_version: str, stdout_writer=None
    ) -> bool:
        """
        Check if detected version is newer than current version.

        Args:
            current_version: Currently stored version (may be empty)
            detected_version: Newly detected version
            stdout_writer: Optional callable for logging

        Returns:
            bool: True if we should update to the detected version
        """
        try:
            # Handle empty current version
            if not current_version:
                return True

            # Parse versions and compare
            parsed_new = pkg_version.parse(detected_version)
            parsed_current = pkg_version.parse(current_version)

            if parsed_new > parsed_current:
                return True

            if parsed_new == parsed_current:
                self._log(
                    stdout_writer,
                    f"⏭️  Skipped: same version ({detected_version})",
                )
            else:
                self._log(
                    stdout_writer,
                    f"⏭️  Skipped: older version (detected {detected_version} < "
                    f"current {current_version})",
                )

            return False

        except InvalidVersion as e:
            self._log(
                stdout_writer,
                f"⚠️  Could not compare versions: {e}",
            )
            return False

    def _save_library_version(
        self,
        library: Library,
        detected_version: str,
        analysis: dict,
        stdout_writer=None,
    ):
        """
        Save the detected version to Library and LibraryRelease records.

        Args:
            library: Library instance to update
            detected_version: Detected version string
            analysis: Dict with keys: summary, source, release_date, etc.
            stdout_writer: Optional callable for logging
        """
        # Parse release date
        release_date_str = analysis.get("release_date", "")
        parsed_release_date = self._parse_release_date(release_date_str)

        # Update Library record
        library.latest_version = detected_version
        library.last_checked_at = datetime.now()
        library.save()

        # Save to LibraryRelease history with detection method
        release, created = LibraryRelease.objects.get_or_create(
            library=library,
            version=detected_version,
            defaults={
                "release_date": parsed_release_date,
                "summary": analysis.get("summary", ""),
                "source_url": analysis.get("source", ""),
                "is_security_release": False,
                "detection_source": "serper_groq",  # Track that this was from Serper+Groq fallback
            },
        )

        if not created:
            # Update existing release with new data
            release.summary = analysis.get("summary", "")
            release.source_url = analysis.get("source", "")
            release.release_date = parsed_release_date
            release.save()

        self._log(stdout_writer, f"✅ Updated to v{detected_version}")

    @staticmethod
    def _parse_release_date(release_date_str: str):
        """
        Parse a release date string into a date object.

        Args:
            release_date_str: Date string in various formats

        Returns:
            date object or None if parsing fails
        """
        if not release_date_str:
            return datetime.now().date()

        formats = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%d/%m/%Y",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(release_date_str, fmt)
                return parsed.date()
            except ValueError:
                continue

        # Try ISO format with timezone
        try:
            normalized = release_date_str.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed.date()
        except ValueError:
            pass

        # Default to today if parsing fails
        return datetime.now().date()

    @staticmethod
    def _infer_registry_type(library: Library) -> str:
        """
        Infer the package registry type based on library name and type.

        Args:
            library: Library instance

        Returns:
            str: Registry type (pypi, npm, rubygems, cargo, maven, generic, etc.)
        """
        # NPM: scoped packages or contain slashes
        if library.name.startswith("@") or "/" in library.name:
            return "npm"

        # Maven: contains colons (groupId:artifactId)
        if ":" in library.name:
            return "maven"

        # Languages: skip registry lookup
        if library.component_type == "language":
            return "generic"

        # Common JavaScript frameworks → npm
        js_frameworks = ["react", "vue", "angular", "next", "vite", "svelte"]
        if library.name.lower() in js_frameworks:
            return "npm"

        # Common Ruby gems
        if library.name.lower() in ["rails", "devise", "sinatra"]:
            return "rubygems"

        # Common Rust crates
        if library.name.lower() in ["serde", "tokio", "rand"]:
            return "cargo"

        # Default to Python/PyPI
        return "pypi"

    @staticmethod
    def _log(stdout_writer, message: str):
        """Helper to write log messages if a writer is provided."""
        if stdout_writer:
            stdout_writer(message)
        else:
            logger.info(message)
