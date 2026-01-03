"""
run_daily_check: Main orchestrator for LibTrack AI daily update checks.

Purpose:
  Coordinates the daily workflow of syncing libraries, fetching updates,
  checking for future versions, and notifying projects.

Flow:
  1. Sync: Link all components to central Library entities
  2. Fetch: Get latest versions from official registries/web
  3. Future: Detect upcoming releases
  4. Notify: Send emails to projects with relevant updates

Services:
  This command uses modular service classes for each responsibility:
  - LibrarySyncService: Syncs StackComponents to Library
  - VersionFetchService: Fetches versions from registries
  - FutureUpdateService: Detects future versions
  - NotificationService: Sends notifications
"""

import os
import time
import logging
import schedule
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from django.core.management.base import BaseCommand, CommandError

from tracker.services import (
    LibrarySyncService,
    VersionFetchService,
    FutureUpdateService,
    NotificationService,
)

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
            self.run_daily_check()

    def run_daily_check(self):
        """
        Execute the daily check workflow.
        
        Steps:
          1. Sync: Link all components to Library entities
          2. Fetch: Get latest versions from registries
          3. Future: Check for upcoming releases
          4. Notify: Send emails to projects
        """
        self.stdout.write(self.style.NOTICE("LibTrack AI: Daily check starting..."))
        start_time = datetime.now()

        try:
            # ===== STEP 1: Sync Libraries =====
            self._step_sync_libraries()

            # ===== STEP 2: Fetch Updates =====
            self._step_fetch_versions()

            # ===== STEP 3: Check Future Versions =====
            self._step_check_future_versions()

            # ===== STEP 4: Notify Projects =====
            self._step_notify_projects()

            # Summary
            duration = (datetime.now() - start_time).total_seconds()
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Daily check completed in {duration:.1f}s"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Daily check failed: {e}"))
            logger.error(f"Daily check error: {e}", exc_info=True)

    # ===== STEP 1: Library Sync =====

    def _step_sync_libraries(self):
        """Step 1: Sync StackComponents to Library entities."""
        self.stdout.write(self.style.MIGRATE_HEADING("1. Syncing Libraries..."))
        service = LibrarySyncService()
        service.sync_all_libraries(stdout_writer=self.stdout.write)

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
        service.fetch_all_libraries(stdout_writer=self.stdout.write)

    # ===== STEP 3: Future Version Detection =====

    def _step_check_future_versions(self):
        """Step 3: Check for future/planned versions."""
        self.stdout.write(self.style.MIGRATE_HEADING("3. Checking Future Versions..."))
        
        from tracker.models import Library
        
        service = FutureUpdateService()
        
        # Get all active libraries
        libraries = Library.objects.filter(linked_components__isnull=False).distinct()
        
        for library in libraries:
            payload = service.check_future_versions(library, stdout_writer=self.stdout.write)
            
            # Buffer future updates for notification step
            if payload and payload.get("category") == "future":
                service.fresh_future_updates[library.name] = payload
        
        # Share buffer with notification service (will use in step 4)
        self.fresh_future_updates = service.fresh_future_updates

    # ===== STEP 4: Notification =====

    def _step_notify_projects(self):
        """Step 4: Send notifications to projects about relevant updates."""
        self.stdout.write(self.style.MIGRATE_HEADING("4. Notifying Projects..."))
        
        # Check for required Mailtrap credentials
        mailtrap_key = os.getenv("MAILTRAP_API_KEY")
        sender_email = os.getenv("MAILTRAP_FROM_EMAIL")

        if not mailtrap_key or not sender_email:
            self.stdout.write(
                self.style.ERROR("❌ Missing Mailtrap credentials (MAILTRAP_API_KEY, MAILTRAP_FROM_EMAIL)")
            )
            return

        service = NotificationService(
            mailtrap_key=mailtrap_key,
            sender_email=sender_email
        )
        
        # Pass buffered future updates from step 3
        service.fresh_future_updates = getattr(self, 'fresh_future_updates', {})
        
        service.notify_all_projects(stdout_writer=self.stdout.write)

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
