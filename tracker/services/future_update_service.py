"""
FutureUpdateService: Detects and manages future/planned versions.

Purpose:
  Identifies upcoming releases, beta versions, RCs, and roadmap items.
  Uses official registry pre-releases (Tier 1) and GitHub (Tier 2) detectors.

Workflow:
  1. For each library, check registry for pre-release versions
  2. Check GitHub releases and milestones
  3. Save detected versions to FutureUpdateCache with confidence scores
  4. Track state transitions (detected → confirmed → released → cancelled)
"""

import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from django.db import models

from tracker.models import FutureUpdateCache, FutureUpdateHistory
from tracker.utils.future_version_detector import FutureVersionDetector

logger = logging.getLogger(__name__)


class FutureUpdateService:
    """
    Detects and manages future/planned versions of libraries.
    Handles lifecycle from detection to release.
    """

    # Configuration: minimum confidence to notify users about a future version
    MIN_CONFIDENCE_THRESHOLD = 70

    # Configuration: minimum confidence increase to re-notify users
    MIN_CONFIDENCE_INCREASE = 15

    def __init__(self):
        """Initialize the future update service."""
        self.detector = FutureVersionDetector(timeout=10)
        self.detected_count = 0
        self.updated_count = 0
        self.error_count = 0
        # Buffer for future updates to be sent as notifications
        self.fresh_future_updates = {}

    def deduplicate_future_updates(self, library_name: str, stdout_writer=None):
        """
        Deduplicate future updates for a library by merging similar versions.
        Collapses duplicate (library, version) pairs and merges confidence.

        Args:
            library_name: Library to deduplicate
            stdout_writer: Optional callable for logging
        """
        try:
            # Get all future updates for this library
            duplicates = FutureUpdateCache.objects.filter(
                library=library_name
            ).values("version").annotate(count=models.Count("id")).filter(count__gt=1)
            
            if not duplicates:
                return  # No duplicates
            
            for dup in duplicates:
                version = dup["version"]
                # Get all copies of this version
                copies = FutureUpdateCache.objects.filter(
                    library=library_name, version=version
                ).order_by("created_at")
                
                if copies.count() <= 1:
                    continue
                
                # Keep the oldest (first detected), merge into it
                primary = copies.first()
                secondary_copies = list(copies[1:])
                
                # Merge confidence: take the max
                merged_confidence = max([c.confidence for c in copies])
                
                if merged_confidence > primary.confidence:
                    # Record the change
                    try:
                        FutureUpdateHistory.objects.create(
                            future_update=primary,
                            library=library_name,
                            version=version,
                            old_confidence=primary.confidence,
                            new_confidence=merged_confidence,
                            change_reason="source_confirmed",
                            change_notes="Merged duplicate detections and increased confidence",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record merge history: {e}")
                    
                    primary.confidence = merged_confidence
                    primary.confirmation_count += len(secondary_copies)
                    primary.save()
                
                # Delete secondary copies
                for copy in secondary_copies:
                    copy.delete()
                
                self._log(
                    stdout_writer,
                    f"   🔀 Deduplicated {library_name} {version}: "
                    f"merged {len(secondary_copies)} copies, confidence now {merged_confidence}%"
                )
        except Exception as e:
            logger.warning(f"Deduplication error for {library_name}: {e}")

    def check_future_versions(self, library, stdout_writer=None):
        """
        Check for future versions of a library.

        Args:
            library: Library instance to check
            stdout_writer: Optional callable for logging

        Returns:
            dict: Payload for notification (or None if not worth notifying)
        """
        self._log(stdout_writer, f"🔮 Checking future versions for {library.name}...")

        try:
            # Use current latest version as baseline for comparison
            current_version = library.latest_version or "0.0.0"

            # Detect all future version candidates (Tier 1 + Tier 2)
            candidates = self.detector.detect_future_versions(
                library.name,
                current_version,
                registry_type=library.registry_type,
            )

            if not candidates:
                self._log(stdout_writer, "   ℹ️  No future versions detected")
                return None

            # Use the highest confidence candidate
            best = candidates[0]
            self._log(
                stdout_writer,
                f"   ✅ Future version: {best.version} "
                f"({best.prerelease_type}, {best.trust_level}% confidence)",
            )

            # Save to FutureUpdateCache and get notification payload
            payload = self._handle_future_update(
                library_name=library.name,
                version=best.version,
                confidence=best.trust_level,
                expected_date=str(best.release_date) if best.release_date else "",
                summary=best.summary,
                source=best.source_url,
                prerelease_type=best.prerelease_type,
                detection_method=best.detection_method,
                stdout_writer=stdout_writer,
            )

            return payload

        except Exception as e:
            self._log(
                stdout_writer,
                f"   ❌ Error checking future versions: {e}",
            )
            logger.error(f"Future version check error for {library.name}: {e}")
            self.error_count += 1
            return None

    def _handle_future_update(
        self,
        library_name: str,
        version: str,
        confidence: int,
        expected_date: str,
        summary: str,
        source: str,
        prerelease_type: str,
        detection_method: str,
        stdout_writer=None,
    ) -> dict | None:
        """
        Handle detection of a future version.
        Saves to DB and returns notification payload if confidence is high enough.

        Args:
            library_name: Name of the library
            version: Detected version string
            confidence: Confidence score (0-100)
            expected_date: Expected release date (YYYY-MM-DD or empty)
            summary: Description of planned features/changes
            source: URL to announcement/roadmap
            prerelease_type: Type of pre-release (alpha, beta, rc, etc.)
            detection_method: How it was detected (registry_prerelease, github_release, etc.)
            stdout_writer: Optional callable for logging

        Returns:
            dict: Notification payload if confidence >= threshold, else None
        """
        # Check confidence threshold
        if confidence < self.MIN_CONFIDENCE_THRESHOLD:
            self._log(
                stdout_writer,
                f"   ℹ️  Confidence too low ({confidence}% < {self.MIN_CONFIDENCE_THRESHOLD}%). "
                f"Not notifying.",
            )
            return None

        # Parse expected date
        parsed_date = None
        if expected_date:
            try:
                parsed_date = datetime.strptime(expected_date, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                self._log(stdout_writer, f"   ⚠️  Could not parse date: {expected_date}")

        # Get or create FutureUpdateCache entry
        future_cache, created = FutureUpdateCache.objects.get_or_create(
            library=library_name,
            version=version,
            defaults={
                "confidence": confidence,
                "expected_date": parsed_date,
                "features": summary,
                "source": source,
                "status": "detected",
                "notification_sent": False,
                "prerelease_type": prerelease_type,
                "detection_method": detection_method,
                "confirmation_count": 1,
            },
        )

        # If already notified, check if confidence increased significantly
        if not created and future_cache.notification_sent:
            return self._handle_confidence_increase(
                future_cache, confidence, summary, source, parsed_date, stdout_writer
            )

        # Update existing entry with new info
        if not created:
            updated = self._update_future_cache(
                future_cache,
                confidence,
                summary,
                source,
                parsed_date,
                stdout_writer,
            )
            if updated:
                self.updated_count += 1
            else:
                return None

        if created:
            self.detected_count += 1

        # Return notification payload
        return {
            "future_update_id": future_cache.id,
            "library": library_name,
            "version": version,
            "category": "future",
            "confidence": confidence,
            "expected_date": expected_date or "TBD",
            "summary": summary or "Upcoming release detected.",
            "source": source or "",
            "prerelease_type": prerelease_type,
            "detection_method": detection_method,
        }

    def _handle_confidence_increase(
        self,
        future_cache: FutureUpdateCache,
        new_confidence: int,
        summary: str,
        source: str,
        parsed_date,
        stdout_writer=None,
    ) -> dict | None:
        """
        Handle when confidence increases for an already-notified future update.

        Args:
            future_cache: FutureUpdateCache instance
            new_confidence: New confidence score
            summary: Updated summary
            source: Updated source URL
            parsed_date: Parsed date or None
            stdout_writer: Optional callable for logging

        Returns:
            dict: Notification payload if increase is significant, else None
        """
        old_confidence = future_cache.confidence
        confidence_increase = new_confidence - old_confidence

        # Only re-notify if confidence increase is significant
        if confidence_increase < self.MIN_CONFIDENCE_INCREASE:
            self._log(
                stdout_writer,
                f"   ℹ️  Confidence increased slightly ({old_confidence}% → {new_confidence}%). "
                f"Not re-notifying.",
            )
            return None

        # Significant increase—update and re-notify
        self._log(
            stdout_writer,
            f"   📈 Confidence surge: {old_confidence}% → {new_confidence}% "
            f"(+{confidence_increase}%)",
        )

        future_cache.previous_confidence = old_confidence
        future_cache.confidence = new_confidence
        if summary:
            future_cache.features = summary
        if source:
            future_cache.source = source
        if parsed_date:
            future_cache.expected_date = parsed_date
        future_cache.last_change_reason = (
            f"Confidence increased from {old_confidence}% to {new_confidence}%"
        )
        future_cache.save()
        
        # Record history of confidence change
        try:
            FutureUpdateHistory.objects.create(
                future_update=future_cache,
                library=future_cache.library,
                version=future_cache.version,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                change_reason="source_confirmed",
                change_notes=f"Confidence surge detected (+{confidence_increase}%)",
                detection_method=future_cache.detection_method,
            )
        except Exception as e:
            logger.warning(f"Failed to record confidence history: {e}")

        self.updated_count += 1

        return {
            "future_update_id": future_cache.id,
            "library": future_cache.library,
            "version": future_cache.version,
            "category": "future",
            "confidence": new_confidence,
            "old_confidence": old_confidence,
            "expected_date": str(future_cache.expected_date) or "TBD",
            "summary": future_cache.features,
            "source": future_cache.source,
            "detection_method": future_cache.detection_method,
        }

    def _update_future_cache(
        self,
        future_cache: FutureUpdateCache,
        confidence: int,
        summary: str,
        source: str,
        parsed_date,
        stdout_writer=None,
    ) -> bool:
        """
        Update an existing FutureUpdateCache entry with new information.

        Args:
            future_cache: FutureUpdateCache instance to update
            confidence: New confidence score
            summary: New summary
            source: New source URL
            parsed_date: New expected date or None
            stdout_writer: Optional callable for logging

        Returns:
            bool: True if any updates were made
        """
        updated = False
        changes = []

        # Check for confidence increase
        if confidence > future_cache.confidence:
            future_cache.previous_confidence = future_cache.confidence
            future_cache.confidence = confidence
            updated = True
            changes.append(f"confidence: {future_cache.previous_confidence}% → {confidence}%")

        # Check for summary update
        if summary and summary != future_cache.features:
            future_cache.features = summary
            updated = True
            changes.append("summary updated")

        # Check for source update
        if source and source != future_cache.source:
            future_cache.source = source
            updated = True
            changes.append(f"source: {source.split('/')[-1] if '/' in source else source}")

        # Check for date update
        if parsed_date and parsed_date != future_cache.expected_date:
            future_cache.expected_date = parsed_date
            updated = True
            changes.append(f"expected_date: {parsed_date}")

        if updated:
            future_cache.last_change_reason = "; ".join(changes)
            future_cache.save()
            self._log(
                stdout_writer,
                f"   ✏️  Updated entry: {', '.join(changes)}",
            )

        return updated

    @staticmethod
    def _log(stdout_writer, message: str):
        """Helper to write log messages if a writer is provided."""
        if stdout_writer:
            stdout_writer(message)
        else:
            logger.info(message)
