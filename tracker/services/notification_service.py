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

import logging
import time
from datetime import datetime
from django.utils import timezone
from packaging import version as pkg_version
from packaging.version import InvalidVersion
from django.conf import settings

from tracker.models import Project, UpdateCache, FutureUpdateCache, NotificationRecord
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

    def notify_all_projects(self, stdout_writer=None):
        """
        Check all projects and send notifications for relevant updates.

        Args:
            stdout_writer: Optional callable for logging

        Returns:
            dict: Summary with counts of sent, skipped, and errored notifications
        """
        self._log(stdout_writer, "Starting project notifications...")

        # Get all projects with their components and linked libraries
        projects = Project.objects.prefetch_related(
            "components__library_ref"
        ).all()
        count = projects.count()
        self._log(stdout_writer, f"Checking {count} projects...")

        for project in projects:
            self._notify_project(project, stdout_writer)

        summary = {
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

        # Collect all relevant updates for this project
        updates_to_send = []

        for component in project.components.all():
            lib = component.library_ref
            if not lib:
                continue

            # Check for future updates (from buffer), respecting confidence threshold
            if lib.name in self.fresh_future_updates and "future" in prefs:
                future_payload = self.fresh_future_updates[lib.name]
                # Only include if confidence meets project threshold
                confidence = future_payload.get("confidence", 0)
                if confidence >= project.min_confidence_threshold:
                    updates_to_send.append(future_payload)
                else:
                    self._log(
                        stdout_writer,
                        f"  ⏭️  Skipped {lib.name} future update: "
                        f"confidence {confidence}% < threshold {project.min_confidence_threshold}%"
                    )

            # Check for stable release updates
            stable_update = self._check_stable_update(lib, component, prefs, stdout_writer)
            if stable_update:
                updates_to_send.append(stable_update)

        # Send email if there are updates
        if updates_to_send:
            self._send_email(project, emails, updates_to_send, stdout_writer)
        else:
            self._log(stdout_writer, f"{project.project_name}: no new updates")
            self.skipped_count += 1

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
            # Build subject line
            first_update = updates[0]
            if len(updates) > 1:
                subject_library = f"{first_update['library']} + {len(updates) - 1} others"
            else:
                subject_library = first_update["library"]

            # Determine category (mix if multiple types)
            categories = {u.get("category") for u in updates}
            if len(categories) > 1:
                category = "mix"
            else:
                category = categories.pop() if categories else "major"

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

                # Record attempt as NotificationRecord
                try:
                    nr = NotificationRecord.objects.create(
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

                            # If this update corresponds to a FutureUpdateCache entry, mark it as notified
                            try:
                                fud = FutureUpdateCache.objects.filter(
                                    library=upd.get("library", ""), version=upd.get("version", "")
                                ).first()
                                if fud:
                                    fud.notification_sent = True
                                    fud.notification_sent_at = timezone.now()
                                    fud.save(update_fields=["notification_sent", "notification_sent_at"])
                            except Exception:
                                logger.exception("Failed to mark FutureUpdateCache as notified")

                        except Exception as e:
                            logger.exception(f"Failed to create UpdateCache for {upd.get('library')}: {e}")

                    self._log(
                        stdout_writer,
                        f"✅ Sent {len(updates)} update(s) to {project.project_name}",
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
