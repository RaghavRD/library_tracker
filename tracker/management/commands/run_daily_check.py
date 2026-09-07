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
import logging
import time
from pathlib import Path
from dotenv import load_dotenv
from django.conf import settings
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

class Command(BaseCommand):
    """
    Django management command for daily library update checks.
    
    Usage:
      python manage.py run_daily_check              # Run once immediately
      python manage.py run_daily_check --global-run # Run once for every project
    
    Configuration:
      - USE_OFFICIAL_APIS (env): If "true", use official registries; else Serper+Groq
      - MAILTRAP_API_KEY (env): Mailtrap API key for sending emails
      - MAILTRAP_FROM_EMAIL (env): Sender email address
    """

    def add_arguments(self, parser):
        """Add command-line arguments."""
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
        parser.add_argument(
            "--budget-seconds",
            dest="budget_seconds",
            type=float,
            default=None,
            help=(
                "Stop starting new steps once this many seconds have elapsed and finish "
                "as 'partial'. Defaults to settings.LIBTRACK_RUN_BUDGET_SECONDS. "
                "Use 0 for no budget."
            ),
        )

    def handle(self, *args, **options):
        """Run one complete daily check for the requested scope."""
        owner = self._resolve_scope_owner(options)
        self.daily_check_run = self._resolve_daily_check_run(options.get("manual_run_id"))
        self._start_budget(options.get("budget_seconds"))
        self.run_daily_check(owner=owner)

    # ===== Time budget =====

    def _start_budget(self, budget_seconds):
        """
        Arm the wall-clock budget for this run.

        Hosts that cap execution time (Vercel Functions cap at 300s) kill the
        process outright when the cap is hit, which loses all progress and leaves
        the DailyCheckRun stuck as active. Stopping ourselves a little early lets
        us record what did complete and exit as 'partial' instead.
        """
        if budget_seconds is None:
            budget_seconds = getattr(settings, "LIBTRACK_RUN_BUDGET_SECONDS", 0)
        self.budget_seconds = float(budget_seconds or 0)
        self.deadline = time.monotonic() + self.budget_seconds if self.budget_seconds > 0 else None

    def _budget_exhausted(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline

    def _budget_remaining(self):
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())

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
        self.step_timings = {}
        scope_label = f"owner={owner.username}" if owner is not None else "global"
        self.stdout.write(self.style.NOTICE(f"LibTrack AI: Daily check starting ({scope_label})..."))
        if self.deadline is not None:
            self.stdout.write(self.style.NOTICE(f"Time budget: {self.budget_seconds:.0f}s"))
        start_time = timezone.now()
        self._mark_run_started(start_time)

        steps = (
            ("sync", self._step_sync_libraries),
            ("fetch", self._step_fetch_versions),
            ("future", self._step_check_future_versions),
            ("security", self._step_scan_security_vulnerabilities),
            ("notifications", self._step_notify_projects),
            ("snapshots", self._step_record_dashboard_snapshots),
        )

        stopped_before = None
        try:
            for name, step in steps:
                if self._budget_exhausted():
                    stopped_before = name
                    self.stdout.write(
                        self.style.WARNING(
                            f"⏱️  Time budget exhausted; stopping before step '{name}'."
                        )
                    )
                    logger.warning("Daily check stopped before step '%s': time budget exhausted", name)
                    break
                step_started = time.monotonic()
                self.run_summary[name] = step()
                self.step_timings[name] = round(time.monotonic() - step_started, 2)

            duration = (timezone.now() - start_time).total_seconds()
            if stopped_before:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  Daily check partially completed in {duration:.1f}s "
                        f"(stopped before '{stopped_before}')"
                    )
                )
                self._mark_run_finished(
                    status="partial",
                    duration=duration,
                    error=f"Time budget exhausted before step '{stopped_before}'.",
                    stopped_before=stopped_before,
                )
            else:
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

    def _mark_run_finished(self, *, status, duration, error="", stopped_before=None):
        run = getattr(self, "daily_check_run", None)
        if not run:
            return
        summary = dict(getattr(self, "run_summary", {}) or {})
        # Per-step timings are what tell you which step is eating the budget.
        summary["timings"] = getattr(self, "step_timings", {})
        if stopped_before:
            summary["stopped_before"] = stopped_before
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
