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
from packaging import version as pkg_version
from packaging.version import InvalidVersion

from tracker.models import Project, UpdateCache
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

            # Check for future updates (from buffer)
            if lib.name in self.fresh_future_updates and "future" in prefs:
                future_payload = self.fresh_future_updates[lib.name]
                updates_to_send.append(future_payload)

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

            # Save to history
            UpdateCache.objects.update_or_create(
                project=component.project,
                library=library.name,
                defaults={
                    "version": library.latest_version,
                    "category": category,
                    "release_date": release_date,
                    "summary": summary,
                    "source": source,
                },
            )

            self._log(
                stdout_writer,
                f"  → {library.name} {library.latest_version} ({category})",
            )

            return {
                "library": library.name,
                "version": library.latest_version,
                "category": category,
                "release_date": release_date,
                "summary": summary,
                "source": source,
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

            # Send email
            success, message = send_update_email(
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

            if success:
                self._log(
                    stdout_writer,
                    f"✅ Sent {len(updates)} update(s) to {project.project_name}",
                )
                self.sent_count += 1
            else:
                self._log(
                    stdout_writer,
                    f"❌ Failed to send email: {message}",
                )
                logger.error(f"Email send failed for {project.project_name}: {message}")
                self.error_count += 1

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
