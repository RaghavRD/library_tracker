"""
NotificationService: Sends notifications to projects about updates.

Purpose:
  Compares project tech stacks against latest library versions.
  Assembles and sends email notifications based on user preferences.

Workflow:
  1. For each project, compare component versions against latest Library versions
  2. Filter based on user notification preferences (major/minor/future)
  3. Build email payload with update details
  4. Send via Mailtrap/Sender
"""

import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from packaging import version as pkg_version
from packaging.version import InvalidVersion

from tracker.models import (
    FutureUpdateCache,
    NotificationRecord,
    Project,
    ProjectFutureNotification,
    SecurityVulnerability,
    UpdateCache,
    UpdateEvent,
)
from tracker.services.dashboard_metrics_service import DashboardMetricsService
from tracker.utils.send_mail import send_update_email

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Handles detection of relevant updates and sending notifications to projects.
    """

    def __init__(self, mailtrap_key: str, sender_email: str):
        """
        Initialize notification service.

        Args:
            mailtrap_key: Mailtrap API key for sending emails
            sender_email: Sender email address
        """
        self.mailtrap_key = mailtrap_key
        self.sender_email = sender_email
        self.sent_count = 0
        self.skipped_count = 0
        self.error_count = 0
        # Buffer for future updates to include in notifications
        self.fresh_future_updates = {}
        self.daily_check_run = None

    def notify_all_projects(self, stdout_writer=None, owner=None, daily_check_run=None):
        """
        Check all projects and send notifications for relevant updates.

        Args:
            stdout_writer: Optional callable for logging

        Returns:
            dict: Summary with counts of sent, skipped, and errored notifications
        """
        self._log(stdout_writer, "Starting project notifications...")

        # Get all projects with their components and linked libraries
        self.daily_check_run = daily_check_run
        projects = Project.objects.prefetch_related(
            "components__library_ref__releases",
            "security_vulnerabilities",
        ).all()
        if owner is not None:
            projects = projects.filter(owner=owner)
        count = projects.count()
        self._log(stdout_writer, f"Checking {count} projects...")

        for project in projects:
            self._notify_project(project, stdout_writer)

        summary = {
            "projects_checked": count,
            "sent_count": self.sent_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
        }
        self._log(
            stdout_writer,
            f"✅ Notifications complete: {self.sent_count} sent, "
            f"{self.skipped_count} skipped, {self.error_count} errors.",
        )
        return summary

    def _notify_project(self, project: Project, stdout_writer=None):
        """
        Check a single project and send notification if there are relevant updates.

        Args:
            project: Project instance to check
            stdout_writer: Optional callable for logging
        """
        # Check if notifications are paused for this project
        if project.notify_paused:
            self._log(
                stdout_writer,
                f"Skipping {project.project_name}: notifications paused",
            )
            self.skipped_count += 1
            return
        
        # Extract recipient emails
        emails = [
            e.strip() for e in (project.developer_emails or "").split(",") if e.strip()
        ]
        if not emails:
            self._log(
                stdout_writer,
                f"Skipping {project.project_name}: no developer emails",
            )
            self.skipped_count += 1
            return

        # Parse notification preferences
        prefs = self._parse_preferences(project.notification_type or "major, minor")

        active_findings = list(
            project.security_vulnerabilities.filter(status="active").order_by("library", "osv_id")
        )
        pending_urgent_findings = [
            finding
            for finding in active_findings
            if self._severity_bucket(finding.severity) in {"critical", "high"}
            and finding.last_notified_signature != self._security_signature(finding)
        ]

        # Collect all relevant updates for this project
        updates_to_send = []
        seen_updates = set()

        for component in project.components.all():
            lib = component.library_ref
            if not lib:
                continue

            # Check for future updates, respecting project-specific delivery state
            if "future" in prefs:
                future_payload = self._check_future_update(project, lib, stdout_writer)
                if future_payload:
                    future_payload.setdefault("from_version", component.version)
                    future_key = (
                        future_payload.get("category"),
                        future_payload.get("library"),
                        future_payload.get("version"),
                    )
                    if future_key not in seen_updates:
                        seen_updates.add(future_key)
                        updates_to_send.append(future_payload)

            # Check for stable release updates
            stable_update = self._check_stable_update(lib, component, prefs, stdout_writer)
            if stable_update:
                stable_key = (
                    stable_update.get("category"),
                    stable_update.get("library"),
                    stable_update.get("version"),
                )
                if stable_key not in seen_updates:
                    seen_updates.add(stable_key)
                    updates_to_send.append(stable_update)

        # Security alerts are delivered by this scheduled cycle, never out-of-band.
        if updates_to_send or pending_urgent_findings:
            digest = self._build_project_digest(
                project,
                prefs=prefs,
                updates=updates_to_send,
                active_findings=active_findings,
            )
            self._send_email(
                project,
                emails,
                updates_to_send,
                digest=digest,
                security_findings_to_mark=pending_urgent_findings,
                stdout_writer=stdout_writer,
            )
        else:
            self._log(stdout_writer, f"{project.project_name}: no new updates")
            self.skipped_count += 1

    def _build_project_digest(
        self,
        project: Project,
        *,
        prefs: set,
        updates: list[dict],
        active_findings: list[SecurityVulnerability],
    ) -> dict:
        """Build the complete package and security state shown in one project email."""
        components = list(project.components.all())
        findings_by_library: dict[str, list[SecurityVulnerability]] = defaultdict(list)
        for finding in active_findings:
            findings_by_library[self._library_key(finding.library)].append(finding)

        future_by_library = self._current_future_updates(project, components, prefs)
        package_states = []
        outdated_count = 0

        for component in components:
            library = component.library_ref
            library_name = library.name if library else component.name
            library_key = self._library_key(library_name)
            latest_version = library.latest_version if library and library.latest_version else "-"
            update_status, update_category = self._package_update_status(
                component.version,
                latest_version,
            )
            is_outdated = update_category in {"major", "minor", "update"}
            if is_outdated:
                outdated_count += 1

            future_update = future_by_library.get(library_key)
            package_findings = findings_by_library.get(library_key, [])
            security_bucket = self._highest_severity(package_findings)
            latest_release = None
            if library:
                latest_release = next(
                    (release for release in library.releases.all() if release.version == latest_version),
                    None,
                )

            detected_candidates = [library.last_checked_at if library else None]
            if future_update:
                detected_candidates.append(future_update.updated_at)
            detected_candidates.extend(finding.last_seen_at for finding in package_findings)
            detected_on = max((value for value in detected_candidates if value), default=None)

            package_states.append(
                {
                    "library": library_name,
                    "component_type": (library.component_type if library else component.category) or "library",
                    "installed_version": component.version or "-",
                    "latest_version": latest_version,
                    "future_version": future_update.version if future_update else "-",
                    "future_enabled": "future" in prefs,
                    "status": update_status,
                    "status_color": self._status_color(update_category),
                    "security": self._severity_label(security_bucket) if package_findings else "Clear",
                    "security_color": self._severity_color(security_bucket),
                    "security_count": len(package_findings),
                    "detected_on": self._format_date(detected_on),
                    "release_summary": (
                        latest_release.summary if latest_release and latest_release.summary else ""
                    ),
                    "release_date": (
                        str(latest_release.release_date)
                        if latest_release and latest_release.release_date
                        else ""
                    ),
                    "release_source": self._safe_url(
                        latest_release.source_url if latest_release else ""
                    ),
                    "future_summary": future_update.features if future_update else "",
                    "future_source": self._safe_url(future_update.source if future_update else ""),
                    "future_confidence": future_update.confidence if future_update else None,
                    "future_expected_date": (
                        str(future_update.expected_date)
                        if future_update and future_update.expected_date
                        else "TBD"
                    ),
                    "security_findings": [
                        self._security_finding_payload(finding) for finding in package_findings[:3]
                    ],
                    "security_findings_hidden": max(0, len(package_findings) - 3),
                    "is_actionable": bool(is_outdated or future_update or package_findings),
                }
            )

        package_states.sort(
            key=lambda item: (
                not item["is_actionable"],
                -self._severity_rank(item["security"]),
                item["library"].casefold(),
            )
        )
        package_limit = getattr(settings, "LIBTRACK_EMAIL_PACKAGE_LIMIT", 20)
        visible_packages = package_states[:package_limit]
        severity_counts = {key: 0 for key in ("critical", "high", "medium", "low", "unknown")}
        for finding in active_findings:
            severity_counts[self._severity_bucket(finding.severity)] += 1

        total_packages = len(package_states)
        active_security_count = len(active_findings)
        health_score = DashboardMetricsService._health_score(
            total_packages,
            outdated_count,
            active_security_count,
        )

        return {
            "project_name": project.project_name,
            "packages": visible_packages,
            "package_details": [item for item in visible_packages if item["is_actionable"]],
            "hidden_package_count": max(0, total_packages - len(visible_packages)),
            "total_packages": total_packages,
            "outdated_packages": outdated_count,
            "up_to_date_packages": max(0, total_packages - outdated_count),
            "future_enabled": "future" in prefs,
            "future_packages": len(future_by_library),
            "updates_count": len(updates),
            "health_score": health_score,
            "health_label": self._health_label(health_score),
            "health_color": self._health_color(health_score),
            "security_status": self._security_health_label(severity_counts),
            "security_color": self._security_health_color(severity_counts),
            "active_security_count": active_security_count,
            "affected_packages": len(findings_by_library),
            "fixes_available": sum(bool(finding.fixed_versions) for finding in active_findings),
            "severity_counts": severity_counts,
            "severity_segments": self._severity_segments(severity_counts),
            "scan_date": timezone.localtime().strftime("%d %b %Y, %I:%M %p"),
        }

    def _current_future_updates(self, project: Project, components: list, prefs: set) -> dict:
        if "future" not in prefs:
            return {}

        library_names = {
            component.library_ref.name
            for component in components
            if component.library_ref and component.library_ref.name
        }
        candidates = FutureUpdateCache.objects.filter(
            library__in=library_names,
            status__in=["detected", "confirmed"],
            confidence__gte=project.min_confidence_threshold,
        ).order_by("library", "-confidence", "-updated_at")

        future_by_library = {}
        for candidate in candidates:
            key = self._library_key(candidate.library)
            future_by_library.setdefault(key, candidate)
        return future_by_library

    @staticmethod
    def _package_update_status(installed: str, latest: str) -> tuple[str, str]:
        if not latest or latest == "-":
            return "Not checked", "unknown"
        try:
            parsed_installed = pkg_version.parse(installed)
            parsed_latest = pkg_version.parse(latest)
            if parsed_latest <= parsed_installed:
                return "Up to date", "current"
            if parsed_latest.major > parsed_installed.major:
                return "Major update", "major"
            return "Minor update", "minor"
        except (InvalidVersion, TypeError):
            if installed == latest:
                return "Up to date", "current"
            return "Update available", "update"

    @classmethod
    def _security_finding_payload(cls, finding: SecurityVulnerability) -> dict:
        bucket = cls._severity_bucket(finding.severity)
        return {
            "osv_id": finding.osv_id,
            "severity": cls._severity_label(bucket),
            "severity_color": cls._severity_color(bucket),
            "summary": finding.summary or finding.details or "Known vulnerability detected.",
            "affected_version": finding.version or "-",
            "fixed_versions": finding.fixed_versions or [],
            "source_url": cls._safe_url(finding.source_url),
        }

    @staticmethod
    def _security_signature(finding: SecurityVulnerability) -> str:
        payload = {
            "severity": finding.severity or "",
            "summary": finding.summary or "",
            "details": finding.details or "",
            "fixed_versions": finding.fixed_versions or [],
            "source_url": finding.source_url or "",
            "status": finding.status,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _mark_security_findings_notified(cls, findings: list[SecurityVulnerability]):
        notified_at = timezone.now()
        for finding in findings:
            finding.last_notified_signature = cls._security_signature(finding)
            finding.last_notified_at = notified_at
            finding.save(update_fields=["last_notified_signature", "last_notified_at", "updated_at"])

    @staticmethod
    def _library_key(value: str) -> str:
        return (value or "").strip().casefold()

    @staticmethod
    def _safe_url(value: str) -> str:
        value = (value or "").strip()
        parsed = urlparse(value)
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""

    @staticmethod
    def _format_date(value) -> str:
        if not value:
            return "-"
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%d %b %Y")

    @staticmethod
    def _severity_bucket(value: str) -> str:
        normalized = (value or "").strip().lower()
        for severity in ("critical", "high", "medium", "low"):
            if severity in normalized:
                return severity
        try:
            score = float(normalized)
        except (TypeError, ValueError):
            return "unknown"
        if score >= 9:
            return "critical"
        if score >= 7:
            return "high"
        if score >= 4:
            return "medium"
        return "low"

    @classmethod
    def _highest_severity(cls, findings: list[SecurityVulnerability]) -> str:
        return max(
            (cls._severity_bucket(finding.severity) for finding in findings),
            key=cls._severity_rank,
            default="unknown",
        )

    @staticmethod
    def _severity_rank(value: str) -> int:
        normalized = (value or "").strip().lower()
        return {"critical": 5, "high": 4, "medium": 3, "low": 2, "unknown": 1}.get(
            normalized,
            0,
        )

    @staticmethod
    def _severity_label(bucket: str) -> str:
        return (bucket or "unknown").title()

    @staticmethod
    def _severity_color(bucket: str) -> str:
        return {
            "critical": "#b42318",
            "high": "#d92d20",
            "medium": "#dc6803",
            "low": "#175cd3",
            "unknown": "#667085",
        }.get((bucket or "unknown").lower(), "#667085")

    @staticmethod
    def _status_color(category: str) -> str:
        return {
            "major": "#b42318",
            "minor": "#b54708",
            "update": "#b54708",
            "current": "#067647",
            "unknown": "#667085",
        }.get(category, "#667085")

    @staticmethod
    def _health_label(score: int) -> str:
        if score >= 90:
            return "Healthy"
        if score >= 70:
            return "Good"
        if score >= 40:
            return "Needs attention"
        return "At risk"

    @staticmethod
    def _health_color(score: int) -> str:
        if score >= 90:
            return "#067647"
        if score >= 70:
            return "#175cd3"
        if score >= 40:
            return "#b54708"
        return "#b42318"

    @staticmethod
    def _security_health_label(counts: dict[str, int]) -> str:
        if counts["critical"]:
            return "Critical action required"
        if counts["high"]:
            return "High risk findings"
        if counts["medium"] or counts["low"] or counts["unknown"]:
            return "Review recommended"
        return "No active findings"

    @staticmethod
    def _security_health_color(counts: dict[str, int]) -> str:
        if counts["critical"]:
            return "#b42318"
        if counts["high"]:
            return "#d92d20"
        if counts["medium"] or counts["low"] or counts["unknown"]:
            return "#b54708"
        return "#067647"

    @classmethod
    def _severity_segments(cls, counts: dict[str, int]) -> list[dict]:
        total = sum(counts.values())
        if total == 0:
            return [{"label": "Clear", "count": 0, "width": 100, "color": "#12b76a"}]
        return [
            {
                "label": cls._severity_label(bucket),
                "count": counts[bucket],
                "width": max(1, round((counts[bucket] / total) * 100)),
                "color": cls._severity_color(bucket),
            }
            for bucket in ("critical", "high", "medium", "low", "unknown")
            if counts[bucket]
        ]

    def _check_future_update(self, project: Project, library, stdout_writer=None) -> dict | None:
        """
        Pick the best future update for a project/library if it has not already
        been successfully delivered to that project.
        """
        candidate_payload = self.fresh_future_updates.get(library.name)
        candidate_cache = None

        if candidate_payload:
            candidate_cache = self._future_cache_for_payload(candidate_payload)
        else:
            candidate_cache = FutureUpdateCache.objects.filter(
                library__iexact=library.name,
                status__in=["detected", "confirmed"],
            ).order_by("-confidence", "-updated_at").first()
            if candidate_cache:
                candidate_payload = self._future_payload_from_cache(candidate_cache)

        if not candidate_payload:
            return None

        confidence = candidate_payload.get("confidence", 0) or 0
        if confidence < project.min_confidence_threshold:
            self._log(
                stdout_writer,
                f"  ⏭️  Skipped {library.name} future update: "
                f"confidence {confidence}% < threshold {project.min_confidence_threshold}%"
            )
            return None

        if candidate_cache and ProjectFutureNotification.objects.filter(
            project=project,
            future_update=candidate_cache,
            success=True,
        ).exists():
            return None

        return candidate_payload

    @staticmethod
    def _future_payload_from_cache(future_cache: FutureUpdateCache) -> dict:
        return {
            "future_update_id": future_cache.id,
            "library": future_cache.library,
            "version": future_cache.version,
            "category": "future",
            "confidence": future_cache.confidence,
            "expected_date": str(future_cache.expected_date) if future_cache.expected_date else "TBD",
            "summary": future_cache.features or "Upcoming release detected.",
            "source": future_cache.source or "",
            "prerelease_type": future_cache.prerelease_type,
            "detection_method": future_cache.detection_method,
        }

    @staticmethod
    def _future_cache_for_payload(payload: dict) -> FutureUpdateCache | None:
        future_update_id = payload.get("future_update_id")
        if future_update_id:
            return FutureUpdateCache.objects.filter(pk=future_update_id).first()

        library = payload.get("library", "")
        version = payload.get("version", "")
        if not library or not version:
            return None
        return FutureUpdateCache.objects.filter(library=library, version=version).first()

    def _record_future_delivery(
        self,
        project: Project,
        updates: list,
        *,
        success: bool,
        attempts: int,
        status_text: str,
    ):
        for upd in updates:
            if upd.get("category") != "future":
                continue

            future_cache = self._future_cache_for_payload(upd)
            if not future_cache:
                continue

            ProjectFutureNotification.objects.update_or_create(
                project=project,
                future_update=future_cache,
                defaults={
                    "success": success,
                    "attempts": attempts,
                    "status_text": status_text or "",
                    "sent_at": timezone.now() if success else None,
                },
            )

            if success:
                future_cache.notification_sent = True
                future_cache.notification_sent_at = timezone.now()
                future_cache.save(update_fields=["notification_sent", "notification_sent_at"])

    def _record_update_event(
        self,
        project: Project,
        update: dict,
        *,
        success: bool,
        sent_at,
        update_cache: UpdateCache | None = None,
    ):
        release_date = update.get("release_date", "")
        if not release_date and update.get("category") == "future":
            release_date = update.get("expected_date", "")

        UpdateEvent.objects.update_or_create(
            project=project,
            library=update.get("library", ""),
            version=update.get("version", ""),
            category=update.get("category", ""),
            defaults={
                "update_cache": update_cache,
                "from_version": update.get("from_version", ""),
                "release_date": release_date,
                "summary": update.get("summary", ""),
                "source": update.get("source", ""),
                "detection_method": update.get("detection_method", "unknown"),
                "notification_success": success,
                "notification_sent_at": sent_at if success else None,
            },
        )

    def _check_stable_update(self, library, component, prefs: set, stdout_writer=None) -> dict | None:
        """
        Check if a library has a stable release newer than the project's component version.

        Args:
            library: Library instance
            component: StackComponent instance (project's component)
            prefs: Set of notification preferences (major, minor, future, all)
            stdout_writer: Optional callable for logging

        Returns:
            dict: Update payload if there's a new release, else None
        """
        # Check if library has a latest version
        if not library.latest_version:
            return None

        try:
            # Compare versions
            parsed_latest = pkg_version.parse(library.latest_version)
            parsed_current = pkg_version.parse(component.version)

            if parsed_latest <= parsed_current:
                return None  # No newer version

            # Determine if it's a major or minor version bump
            category = "major" if parsed_latest.major > parsed_current.major else "minor"

            # Check if project wants this category of update
            if category not in prefs and "all" not in prefs:
                return None  # User doesn't want this type of notification

            # Fetch release details from LibraryRelease if available
            release = library.releases.filter(version=library.latest_version).first()
            summary = release.summary if release else "New version available"
            source = release.source_url if release else ""
            release_date = str(release.release_date) if release else ""

            self._log(
                stdout_writer,
                f"  → {library.name} {library.latest_version} ({category})",
            )

            # Return payload; persist to UpdateCache only after successful send
            return {
                "library": library.name,
                "from_version": component.version,
                "version": library.latest_version,
                "category": category,
                "release_date": release_date,
                "summary": summary,
                "source": source,
                "detection_method": "registry_api" if library.last_api_call_successful else "unknown",
            }

        except InvalidVersion as e:
            self._log(
                stdout_writer,
                f"⚠️  Could not compare versions for {library.name}: {e}",
            )
            logger.warning(f"Invalid version for {library.name}: {e}")
            return None
        except Exception as e:
            self._log(
                stdout_writer,
                f"⚠️  Error checking {library.name}: {e}",
            )
            logger.error(f"Error checking stable update for {library.name}: {e}")
            return None

    def _send_email(
        self,
        project: Project,
        emails: list,
        updates: list,
        *,
        digest: dict,
        security_findings_to_mark: list[SecurityVulnerability],
        stdout_writer=None,
    ):
        """
        Send email notification to project with list of updates.

        Args:
            project: Project instance
            emails: List of recipient email addresses
            updates: List of update payloads to include in email
            stdout_writer: Optional callable for logging
        """
        try:
            first_update = updates[0] if updates else {
                "library": "Security alerts",
                "version": "",
            }
            if len(updates) > 1:
                subject_library = f"{first_update['library']} + {len(updates) - 1} others"
            else:
                subject_library = first_update["library"]

            # Determine category (mix if multiple types)
            categories = {u.get("category") for u in updates}
            if len(categories) > 1:
                category = "mix"
            else:
                category = categories.pop() if categories else "security"

            # Retry sending with exponential backoff
            max_retries = getattr(settings, "LIBTRACK_MAX_NOTIFICATION_RETRIES", 3)
            attempt = 0
            final_result = None
            while attempt < max_retries:
                attempt += 1
                result = send_update_email(
                    mailtrap_api_key=self.mailtrap_key,
                    project_name=project.project_name,
                    recipients=emails,
                    library=subject_library,
                    version=first_update.get("version", "unknown"),
                    category=category,
                    summary="Updates detected in your stack.",
                    source="",
                    release_date="",
                    updates=updates,
                    from_email=self.sender_email,
                    future_opt_in=digest["future_enabled"],
                    digest=digest,
                )

                # support legacy tuple return (bool, message)
                if isinstance(result, tuple) and len(result) >= 2:
                    success = bool(result[0])
                    status_text = str(result[1])
                    http_status = None
                    response_text = None
                    error_text = None
                elif isinstance(result, dict):
                    success = bool(result.get("success"))
                    status_text = result.get("status_text") or ""
                    http_status = result.get("http_status")
                    response_text = result.get("response_text")
                    error_text = result.get("error")
                else:
                    success = False
                    status_text = "unknown response from send_update_email"
                    http_status = None
                    response_text = None
                    error_text = "unknown"

                self._record_future_delivery(
                    project,
                    updates,
                    success=success,
                    attempts=attempt,
                    status_text=status_text,
                )
                sent_at = timezone.now() if success else None
                for upd in updates:
                    self._record_update_event(
                        project,
                        upd,
                        success=success,
                        sent_at=sent_at,
                    )

                # Record attempt as NotificationRecord
                try:
                    nr = NotificationRecord.objects.create(
                        daily_check_run=self.daily_check_run,
                        project=project,
                        library=first_update.get("library", ""),
                        version=first_update.get("version", ""),
                        success=success,
                        attempts=attempt,
                        status_text=status_text or "",
                        http_status=http_status,
                        response_text=response_text or "",
                        error_text=str(error_text) if error_text else "",
                        sent_at=timezone.now() if success else None,
                    )
                    # Log structured notification attempt
                    logger.info(
                        f"Notification record created: project={project.project_name}, "
                        f"library={first_update.get('library')}, success={success}, "
                        f"http_status={http_status}, attempt={attempt}"
                    )
                except Exception:
                    logger.exception("Failed to write NotificationRecord")

                if success:
                    self._mark_security_findings_notified(security_findings_to_mark)
                    # Persist UpdateCache entries for each update upon success
                    for upd in updates:
                        try:
                            uc, _ = UpdateCache.objects.update_or_create(
                                project=project,
                                library=upd.get("library", ""),
                                defaults={
                                    "version": upd.get("version", ""),
                                    "category": upd.get("category", ""),
                                    "release_date": upd.get("release_date", ""),
                                    "summary": upd.get("summary", ""),
                                    "source": upd.get("source", ""),
                                    "detection_method": upd.get("detection_method", "unknown"),
                                },
                            )
                            self._record_update_event(
                                project,
                                upd,
                                success=True,
                                sent_at=timezone.now(),
                                update_cache=uc,
                            )

                        except Exception as e:
                            logger.exception(f"Failed to create UpdateCache for {upd.get('library')}: {e}")

                    self._log(
                        stdout_writer,
                        f"Sent project digest to {project.project_name}: "
                        f"{len(updates)} update(s), "
                        f"{digest['active_security_count']} active security finding(s)",
                    )
                    self.sent_count += 1
                    final_result = True
                    break
                else:
                    self._log(
                        stdout_writer,
                        f"❌ Attempt {attempt} failed to send email: {status_text}",
                    )
                    logger.error(f"Email send failed for {project.project_name}: {status_text}")
                    self.error_count += 1

                    # Backoff before next attempt (do not sleep after last attempt)
                    if attempt < max_retries:
                        backoff = min(2 ** attempt, 30)
                        time.sleep(backoff)

            if not final_result:
                # all attempts failed
                self._log(stdout_writer, f"❌ All {max_retries} attempts failed for {project.project_name}")

        except Exception as e:
            self._log(
                stdout_writer,
                f"❌ Error sending email: {e}",
            )
            logger.error(f"Email send error for {project.project_name}: {e}")
            self.error_count += 1

    @staticmethod
    def _parse_preferences(notification_type: str) -> set:
        """
        Parse notification preference string into a set of categories.

        Args:
            notification_type: Comma-separated string (e.g., "major, minor, future")

        Returns:
            set: Normalized preferences (major, minor, future, all)
        """
        prefs = set()
        for pref in (notification_type or "").split(","):
            pref = pref.strip().lower()
            if pref in {"major", "minor", "future", "all", "both"}:
                if pref == "both":
                    # "both" is shorthand for major + minor
                    prefs.update({"major", "minor"})
                else:
                    prefs.add(pref)
        
        # Default to major + minor if empty
        if not prefs:
            prefs = {"major", "minor"}

        return prefs

    @staticmethod
    def _log(stdout_writer, message: str):
        """Helper to write log messages if a writer is provided."""
        if stdout_writer:
            stdout_writer(message)
        else:
            logger.info(message)
