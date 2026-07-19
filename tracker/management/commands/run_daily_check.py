"""
run_daily_check: Main orchestrator for LibTrack AI daily update checks.

Purpose:
  Coordinates the daily workflow of syncing libraries, fetching updates,
  checking for future versions, scanning security alerts, and notifying projects.

Flow:
  1. Sync: Link all components to central Library entities
  2. Fetch: Get latest versions from official registries/web
  3. Future: Detect upcoming releases
  4. Security: Detect known vulnerabilities via OSV
  5. Notify: Send emails to projects with relevant updates

Services:
  This command uses modular service classes for each responsibility:
  - LibrarySyncService: Syncs StackComponents to Library
  - VersionFetchService: Fetches versions from registries
  - FutureUpdateService: Detects future versions
  - SecurityVulnerabilityService: Detects OSV security findings
  - NotificationService: Sends notifications
"""

import os
import time
import logging
import schedule
from pathlib import Path
from dotenv import load_dotenv
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tracker.services import (
    LibrarySyncService,
    VersionFetchService,
    FutureUpdateService,
    SecurityVulnerabilityService,
    NotificationService,
    DashboardMetricsService,
)
from tracker.models import DailyCheckRun, Project

# Get logger
logger = logging.getLogger('libtrack')

# ✅ Locate .env manually (robust)
BASE_DIR = Path(__file__).resolve().parents[3]
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    print(f"⚠️ .env not found at expected path: {env_path}")

load_dotenv()

DEFAULT_AUTO_RUN_TIME = "09:00"


class Command(BaseCommand):
    """
    Django management command for daily library update checks.
    
    Usage:
      python manage.py run_daily_check              # Run once immediately
      python manage.py run_daily_check --auto       # Schedule daily at 09:00
      python manage.py run_daily_check --auto --time 14:30  # Schedule at custom time
    
    Configuration:
      - USE_OFFICIAL_APIS (env): If "true", use official registries; else Serper+Groq
      - MAILTRAP_API_KEY (env): Mailtrap API key for sending emails
      - MAILTRAP_FROM_EMAIL (env): Sender email address
    """

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--auto",
            action="store_true",
            help=f"Run in auto-schedule mode (defaults to daily at {DEFAULT_AUTO_RUN_TIME}).",
        )
        parser.add_argument(
            "--time",
            dest="run_time",
            metavar="HH:MM",
            default=DEFAULT_AUTO_RUN_TIME,
            help=f"Time of day (24h) to execute when --auto is used. Defaults to {DEFAULT_AUTO_RUN_TIME}.",
        )
        parser.add_argument(
            "--owner-id",
            dest="owner_id",
            type=int,
            help="Run checks only for projects owned by this user id.",
        )
        parser.add_argument(
            "--global-run",
            action="store_true",
            help="Run checks for every owner/project. This is the default for scheduled cron runs.",
        )
        parser.add_argument(
            "--manual-run-id",
            dest="manual_run_id",
            type=int,
            help="DailyCheckRun id to update while this command executes.",
        )

    def handle(self, *args, **options):
        """
        Main entry point for the command.
        
        Args:
            auto: If True, schedule daily runs instead of running once
            run_time: Time of day to run (HH:MM format, 24-hour)
        """
        run_time = options.get("run_time") or DEFAULT_AUTO_RUN_TIME
        if run_time and not self._is_valid_time_format(run_time):
            raise CommandError("Invalid value for --time. Use HH:MM in 24-hour format, e.g. 09:00.")

        if options.get("auto"):
            # Schedule to run daily at the specified time
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"⏰ Auto mode: will run every day at {run_time}")
            )
            schedule.every().day.at(run_time).do(self.run_daily_check)
            
            # Keep scheduler running
            while True:
                schedule.run_pending()
                time.sleep(30)
        else:
            # Run once immediately
            owner = self._resolve_scope_owner(options)
            self.daily_check_run = self._resolve_daily_check_run(options.get("manual_run_id"))
            self.run_daily_check(owner=owner)

    def run_daily_check(self, owner=None):
        """
        Execute the daily check workflow.
        
        Steps:
          1. Sync: Link all components to Library entities
          2. Fetch: Get latest versions from registries
          3. Future: Check for upcoming releases
          4. Security: Scan known vulnerabilities
          5. Notify: Send emails to projects
        """
        self.scope_owner = owner
        self.run_summary = {}
        scope_label = f"owner={owner.username}" if owner is not None else "global"
        self.stdout.write(self.style.NOTICE(f"LibTrack AI: Daily check starting ({scope_label})..."))
        start_time = timezone.now()
        self._mark_run_started(start_time)

        try:
            # ===== STEP 1: Sync Libraries =====
            self.run_summary["sync"] = self._step_sync_libraries()

            # ===== STEP 2: Fetch Updates =====
            self.run_summary["fetch"] = self._step_fetch_versions()

            # ===== STEP 3: Check Future Versions =====
            self.run_summary["future"] = self._step_check_future_versions()

            # ===== STEP 4: Security Vulnerability Scan =====
            self.run_summary["security"] = self._step_scan_security_vulnerabilities()

            # ===== STEP 5: Notify Projects =====
            self.run_summary["notifications"] = self._step_notify_projects()

            # ===== STEP 6: Record Dashboard Snapshots =====
            self.run_summary["snapshots"] = self._step_record_dashboard_snapshots()

            # Summary
            duration = (timezone.now() - start_time).total_seconds()
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Daily check completed in {duration:.1f}s"
                )
            )
            self._mark_run_finished(status="success", duration=duration)
            return self.run_summary

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Daily check failed: {e}"))
            logger.error(f"Daily check error: {e}", exc_info=True)
            duration = (timezone.now() - start_time).total_seconds()
            self._mark_run_finished(status="failed", duration=duration, error=str(e))
            return self.run_summary

    # ===== STEP 1: Library Sync =====

    def _step_sync_libraries(self):
        """Step 1: Sync StackComponents to Library entities."""
        self.stdout.write(self.style.MIGRATE_HEADING("1. Syncing Libraries..."))
        service = LibrarySyncService()
        return service.sync_all_libraries(stdout_writer=self.stdout.write, owner=self.scope_owner)

    # ===== STEP 2: Fetch Versions =====

    def _step_fetch_versions(self):
        """
        Step 2: Fetch latest versions for all libraries.
        
        Uses official registries if USE_OFFICIAL_APIS=true; else falls back to Serper+Groq.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("2. Fetching Updates for Libraries..."))
        
        # Check environment setting
        use_official_apis = os.getenv("USE_OFFICIAL_APIS", "true").lower() == "true"
        if use_official_apis:
            self.stdout.write(self.style.SUCCESS("✨ Using official package registry APIs"))
        else:
            self.stdout.write(self.style.WARNING("⚠️  Using legacy Serper+Groq method"))

        service = VersionFetchService(
            use_official_apis=use_official_apis,
            debug=False
        )
        return service.fetch_all_libraries(stdout_writer=self.stdout.write, owner=self.scope_owner)

    # ===== STEP 3: Future Version Detection =====

    def _step_check_future_versions(self):
        """Step 3: Check for future/planned versions."""
        self.stdout.write(self.style.MIGRATE_HEADING("3. Checking Future Versions..."))
        
        from tracker.models import Library
        
        service = FutureUpdateService()
        
        # Get all active libraries
        libraries = Library.objects.filter(linked_components__isnull=False)
        if self.scope_owner is not None:
            libraries = libraries.filter(linked_components__project__owner=self.scope_owner)
        libraries = libraries.distinct()
        
        for library in libraries:
            payload = service.check_future_versions(library, stdout_writer=self.stdout.write)
            
            # Buffer future updates for notification step
            if payload and payload.get("category") == "future":
                service.fresh_future_updates[library.name] = payload
        
        # Share buffer with notification service (will use in step 4)
        self.fresh_future_updates = service.fresh_future_updates
        return {
            "libraries_checked": libraries.count(),
            "future_updates_found": len(service.fresh_future_updates),
        }

    # ===== STEP 4: Security Vulnerability Scan =====

    def _step_scan_security_vulnerabilities(self):
        """Step 4: Scan tracked dependencies for known vulnerabilities."""
        self.stdout.write(self.style.MIGRATE_HEADING("4. Scanning Security Vulnerabilities..."))
        service = SecurityVulnerabilityService()
        return service.scan_all_projects(stdout_writer=self.stdout.write, owner=self.scope_owner)

    # ===== STEP 5: Notification =====

    def _step_notify_projects(self):
        """Step 5: Send notifications to projects about relevant updates."""
        self.stdout.write(self.style.MIGRATE_HEADING("5. Notifying Projects..."))
        
        # Check for required Mailtrap credentials
        mailtrap_key = os.getenv("MAILTRAP_API_KEY")
        sender_email = os.getenv("MAILTRAP_FROM_EMAIL")

        if not mailtrap_key or not sender_email:
            self.stdout.write(
                self.style.ERROR("❌ Missing Mailtrap credentials (MAILTRAP_API_KEY, MAILTRAP_FROM_EMAIL)")
            )
            return {
                "projects_checked": 0,
                "sent_count": 0,
                "skipped_count": 0,
                "error_count": 1,
                "error": "missing_mailtrap_credentials",
            }

        service = NotificationService(
            mailtrap_key=mailtrap_key,
            sender_email=sender_email
        )
        
        # Pass buffered future updates from step 3
        service.fresh_future_updates = getattr(self, 'fresh_future_updates', {})
        
        return service.notify_all_projects(
            stdout_writer=self.stdout.write,
            owner=self.scope_owner,
            daily_check_run=getattr(self, "daily_check_run", None),
        )

    def _step_record_dashboard_snapshots(self):
        """Step 6: Capture per-user dashboard metrics for trend charts."""
        self.stdout.write(self.style.MIGRATE_HEADING("6. Recording Dashboard Snapshots..."))
        count = DashboardMetricsService.record_all_owner_snapshots(owner=self.scope_owner)
        self.stdout.write(self.style.SUCCESS(f"📈 Recorded {count} dashboard snapshot(s)"))
        return {"snapshots_recorded": count}

    def _resolve_scope_owner(self, options):
        owner_id = options.get("owner_id")
        global_run = options.get("global_run")
        if owner_id and global_run:
            raise CommandError("Use either --owner-id or --global-run, not both.")
        if not owner_id:
            return None
        user_model = get_user_model()
        try:
            return user_model.objects.get(pk=owner_id)
        except user_model.DoesNotExist as exc:
            raise CommandError(f"No user found for --owner-id={owner_id}") from exc

    @staticmethod
    def _resolve_daily_check_run(run_id):
        if not run_id:
            return None
        return DailyCheckRun.objects.filter(pk=run_id).first()

    def _mark_run_started(self, started_at):
        run = getattr(self, "daily_check_run", None)
        if not run:
            return
        run.status = "running"
        run.started_at = started_at
        run.scope_owner = self.scope_owner if run.scope == "owner" else None
        run.error_message = ""
        run.save(update_fields=["status", "started_at", "scope_owner", "error_message", "updated_at"])

    def _mark_run_finished(self, *, status, duration, error=""):
        run = getattr(self, "daily_check_run", None)
        if not run:
            return
        summary = getattr(self, "run_summary", {}) or {}
        fetch = summary.get("fetch") or {}
        future = summary.get("future") or {}
        security = summary.get("security") or {}
        notifications = summary.get("notifications") or {}
        project_qs = Project.objects.exclude(owner__isnull=True)
        if self.scope_owner is not None:
            project_qs = project_qs.filter(owner=self.scope_owner)

        run.status = status
        run.finished_at = timezone.now()
        run.duration_seconds = duration
        run.projects_scanned = security.get("projects_scanned") or project_qs.count()
        run.libraries_checked = fetch.get("checked_count") or future.get("libraries_checked") or 0
        run.future_updates_found = future.get("future_updates_found") or 0
        run.security_findings_found = security.get("finding_count") or 0
        run.emails_sent = notifications.get("sent_count") or 0
        run.emails_failed = notifications.get("error_count") or 0
        run.emails_skipped = notifications.get("skipped_count") or 0
        run.emails_attempted = run.emails_sent + run.emails_failed
        run.summary = summary
        run.error_message = error
        run.save(update_fields=[
            "status",
            "finished_at",
            "duration_seconds",
            "projects_scanned",
            "libraries_checked",
            "future_updates_found",
            "security_findings_found",
            "emails_attempted",
            "emails_sent",
            "emails_failed",
            "emails_skipped",
            "summary",
            "error_message",
            "updated_at",
        ])

    @staticmethod
    def _is_valid_time_format(value: str) -> bool:
        """
        Validate time format (HH:MM in 24-hour format).
        
        Args:
            value: Time string to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            time.strptime(value, "%H:%M")
            return True
        except (TypeError, ValueError):
            return False
