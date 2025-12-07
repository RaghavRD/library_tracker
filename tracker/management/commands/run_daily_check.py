import os
import time
import logging
import schedule
from time import sleep
from pathlib import Path
from django.db import transaction
from dotenv import load_dotenv, find_dotenv
from packaging import version as pkg_version
from packaging.version import InvalidVersion
from django.core.management.base import BaseCommand, CommandError

from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer
from tracker.utils.send_mail import send_update_email
from tracker.models import UpdateCache, Project, FutureUpdateCache

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
    help = "Runs daily update check using Serper.dev + Groq and emails relevant updates via Mailtrap"

    def add_arguments(self, parser):
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
        run_time = options.get("run_time") or DEFAULT_AUTO_RUN_TIME
        if run_time and not self._is_valid_time_format(run_time):
            raise CommandError("Invalid value for --time. Use HH:MM in 24-hour format, e.g. 09:00.")

        if options.get("auto"):
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"⏰ Auto mode: will run every day at {run_time}")
            )
            schedule.every().day.at(run_time).do(self.run_daily_check)
            while True:
                schedule.run_pending()
                time.sleep(30)
        else:
            self.run_daily_check()

    def run_daily_check(self):
        self.stdout.write(self.style.NOTICE("LibTrack AI: Daily check starting..."))

        mailtrap_key = os.getenv("MAILTRAP_MAIN_KEY")
        sender_email = os.getenv("MAILTRAP_FROM_EMAIL")

        if not mailtrap_key or not sender_email:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Missing Mailtrap credentials.\n"
                    f"MAILTRAP_MAIN_KEY={bool(mailtrap_key)} | MAILTRAP_FROM_EMAIL={bool(sender_email)}"
                )
            )
            return

        projects = Project.objects.prefetch_related("components").all()
        if not projects:
            self.stdout.write("No registrations found.")
            return

        groq = GroqAnalyzer()
        serper = SerperFetcher()

        for project in projects:
            project_name = (project.project_name or "").strip() or "Unnamed Project"
            
            # ===== Print project header with separators =====
            self.stdout.write("\n" + "-"*8)
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"📦 Processing Project: {project_name}")
            )
            self.stdout.write("-"*8 + "\n")
            
            emails = [e.strip() for e in (project.developer_emails or "").split(",") if e.strip()]
            notify_pref = str(project.notification_type or "both").lower()

            components = list(project.components.all())
            library_components = [comp for comp in components if comp.key != "language"]
            language_components = [comp for comp in components if comp.key == "language"]

            lib_pairs = [
                (comp.name.strip(), comp.version.strip())
                for comp in library_components
                if comp.name and comp.version
            ]
            language_pairs = [
                (comp.name.strip(), comp.version.strip())
                for comp in language_components
                if comp.name and comp.version
            ]

            lib_names = [name for name, _ in lib_pairs]
            lib_versions = [version for _, version in lib_pairs]
            language_names = [name for name, _ in language_pairs]
            language_versions = [version for _, version in language_pairs]

            project_updates = []
            project_updates.extend(
                self._process_components(
                    project=project,
                    project_name=project_name,
                    names=lib_names,
                    versions=lib_versions,
                    component_type="library",
                    groq=groq,
                    serper=serper,
                    notify_pref=notify_pref,
                )
            )
            project_updates.extend(
                self._process_components(
                    project=project,
                    project_name=project_name,
                    names=language_names,
                    versions=language_versions,
                    component_type="language",
                    groq=groq,
                    serper=serper,
                    notify_pref=notify_pref,
                )
            )

            if project_updates:
                categories = {update["category"] for update in project_updates}
                aggregate_category = categories.pop() if len(categories) == 1 else "mix"

                if len(project_updates) == 1:
                    first = project_updates[0]
                    subject_library = first["library"]
                    subject_version = first["version"]
                    summary_text = first["summary"]
                    source_link = first["source"]
                else:
                    subject_library = f"{project_updates[0]['library']} + {len(project_updates) - 1} more"
                    subject_version = f"{project_updates[0]['version']} and additional releases"
                    summary_text = "See release summaries below."
                    source_link = ""

                ok, info = send_update_email(
                    mailtrap_api_key=mailtrap_key,
                    project_name=project_name,
                    recipients=emails,
                    library=subject_library,
                    version=subject_version,
                    category=aggregate_category,
                    summary=summary_text,
                    source=source_link,
                    release_date=project_updates[0].get("release_date"),
                    updates=project_updates,
                    from_email=str(sender_email),
                )
                self.stdout.write(f"Project digest for {project_name}: {ok} -> {info}")
            else:
                self.stdout.write(f"No qualifying updates for {project_name}.")
            
            # ===== Add spacing after project completion =====
            self.stdout.write(self.style.SUCCESS(f"✅ Completed processing for: {project_name}"))

        self.stdout.write(self.style.SUCCESS("✅ Daily check completed successfully."))

    def _process_components(
        self,
        project: Project,
        project_name: str,
        names: list[str],
        versions: list[str],
        *,
        component_type: str,
        groq: GroqAnalyzer,
        serper: SerperFetcher,
        notify_pref: str,
    ) -> list[dict]:
        """Evaluate a set of components (libraries or languages) and return update payloads."""
        if not names:
            return []

        if not versions or len(names) != len(versions):
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️ Skipping {project_name}: {component_type} name/version mismatch",
                )
            )
            return []

        updates: list[dict] = []
        for name, current_version in zip(names, versions):
            update = self._evaluate_component(
                project=project,
                name=name,
                current_version=current_version,
                groq=groq,
                serper=serper,
                notify_pref=notify_pref,
                component_type=component_type,
            )
            if update:
                updates.append(update)
            sleep(1.5)
        return updates

    def _evaluate_component(
        self,
        *,
        project: Project,
        name: str,
        current_version: str,
        groq: GroqAnalyzer,
        serper: SerperFetcher,
        notify_pref: str,
        component_type: str,
    ) -> dict | None:
        """Run Serper+Groq for a single component and return an update dict if we should email."""
        serper_results = serper.search_library(name, current_version, component_type=component_type)
        
        # Log Serper's version candidate for debugging
        candidate = serper_results.get("latest_version_candidate", "")
        if candidate:
            logger.info(f"[{component_type}:{name}] Serper found version candidate: {candidate}")
        
        analysis = groq.analyze(name, serper_results)
        
        # Log Groq's detected version
        detected_version = analysis.get("version", "")
        if detected_version:
            logger.info(f"[{component_type}:{name}] Groq detected version: {detected_version}")
        
        if analysis.get("error"):
            self.stdout.write(self.style.WARNING(f"[{name}] Groq error: {analysis['error']}"))
            return None

        library = analysis.get("library", name)
        version = analysis.get("version", "")
        category = analysis.get("category", "major")
        
        # ===== NEW: Extract future update fields =====
        is_released = analysis.get("is_released", True)
        confidence = analysis.get("confidence", 50)
        expected_date = analysis.get("expected_date", "")
        
        release_date = analysis.get("release_date", "")
        source = analysis.get("source", "")
        summary = analysis.get("summary", "")
        label = f"{component_type}:{library}"
        
        # ===== NEW: Route to future update handler if not released =====
        if category == "future" or not is_released:
            return self._handle_future_update(
                library=library,
                version=version,
                confidence=confidence,
                expected_date=expected_date,
                summary=summary,
                source=source,
                notify_pref=notify_pref,
                label=label,
                component_type=component_type,
            )

        with transaction.atomic():
            cache, _ = UpdateCache.objects.select_for_update().get_or_create(
                project=project,
                library=library,
                defaults={
                    "version": version or "",
                    "category": category,
                    "release_date": release_date or "",
                    "summary": summary or "",
                    "source": source or "",
                },
            )

            should_send = False
            if version and version != cache.version:
                should_send = True
            elif category == "major" and cache.category != "major":
                should_send = True

            if should_send:
                if notify_pref == "major" and category != "major":
                    should_send = False
                elif notify_pref == "minor" and category != "minor":
                    should_send = False

            if version and current_version:
                try:
                    parsed_new = pkg_version.parse(version)
                    parsed_current = pkg_version.parse(current_version)
                    
                    if parsed_new <= parsed_current:
                        logger.info(
                            f"[{label}] Skipped - version {version} not newer than current {current_version} "
                            f"(Serper candidate: {serper_results.get('latest_version_candidate', 'N/A')})"
                        )
                        should_send = False
                except InvalidVersion as e:
                    logger.warning(
                        f"[{label}] Invalid version format - new: '{version}', current: '{current_version}'. "
                        f"Error: {e}. Skipping version comparison."
                    )
                    # Continue processing - let other checks determine if we should send
                except Exception as e:
                    logger.error(
                        f"[{label}] Unexpected error during version comparison: {e}",
                        exc_info=True
                    )
                    # Continue processing despite error

            if should_send:
                cache.version = version or cache.version
                cache.category = category
                cache.release_date = release_date or cache.release_date
                cache.summary = summary or cache.summary
                cache.source = source or cache.source
                cache.save()

                return {
                    "library": library,
                    "version": version or current_version or "unknown",
                    "category": category,
                    "release_date": release_date or "Unknown",
                    "summary": summary or "No summary.",
                    "source": source or "",
                    "component_type": component_type,
                }

        self.stdout.write(f"[{label}] No email (no new version or filtered by preference).")
        return None

    def _handle_future_update(
        self,
        library: str,
        version: str,
        confidence: int,
        expected_date: str,
        summary: str,
        source: str,
        notify_pref: str,
        label: str,
        component_type: str,
    ) -> dict | None:
        """Handle detection of future/planned updates."""
        
        # ===== Check if user wants future updates =====
        if "future" not in notify_pref:
            self.stdout.write(f"[{label}] Future update detected but user opted out (notify_pref={notify_pref}).")
            return None
        
        # ===== Confidence threshold - only send high confidence future updates =====
        MIN_CONFIDENCE = 70  # Configurable threshold
        if confidence < MIN_CONFIDENCE:
            self.stdout.write(
                f"[{label}] Future update confidence too low ({confidence}% < {MIN_CONFIDENCE}%). "
                f"Version {version}, source: {source[:50] if source else 'N/A'}"
            )
            return None
        
        # ===== Store in FutureUpdateCache =====
        from datetime import datetime
        
        with transaction.atomic():
            # Parse expected_date if provided
            parsed_date = None
            if expected_date:
                try:
                    parsed_date = datetime.strptime(expected_date, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    self.stdout.write(f"[{label}] Could not parse expected_date: {expected_date}")
            
            future_cache, created = FutureUpdateCache.objects.get_or_create(
                library=library,
                version=version,
                defaults={
                    "confidence": confidence,
                    "expected_date": parsed_date,
                    "features": summary,
                    "source": source,
                    "status": "detected",
                    "notification_sent": False,
                }
            )
            
            # If already notified, don't send again
            if not created and future_cache.notification_sent:
                self.stdout.write(
                    f"[{label}] Future update already notified on "
                    f"{future_cache.notification_sent_at.strftime('%Y-%m-%d') if future_cache.notification_sent_at else 'unknown date'}."
                )
                return None
            
            # Update if confidence increased or info changed
            if not created:
                update_needed = False
                if confidence > future_cache.confidence:
                    future_cache.confidence = confidence
                    update_needed = True
                if summary and summary != future_cache.features:
                    future_cache.features = summary
                    update_needed = True
                if source and source != future_cache.source:
                    future_cache.source = source
                    update_needed = True
                if parsed_date and parsed_date != future_cache.expected_date:
                    future_cache.expected_date = parsed_date
                    update_needed = True
                
                if update_needed:
                    future_cache.save()
                    self.stdout.write(f"[{label}] Updated existing future update entry with new info.")
            
            # Mark as notified
            future_cache.notification_sent = True
            future_cache.notification_sent_at = datetime.now()
            future_cache.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{label}] ✅ Future update notification prepared: v{version} "
                    f"(confidence: {confidence}%, expected: {expected_date or 'TBD'})"
                )
            )
            
            return {
                "library": library,
                "version": version,
                "category": "future",
                "release_date": expected_date or "TBD",
                "summary": summary or "Upcoming release detected.",
                "source": source or "",
                "component_type": component_type,
                "confidence": confidence,
            }

    @staticmethod
    def _is_valid_time_format(value: str) -> bool:
        """Return True if time is HH:MM in 24h format."""
        try:
            time.strptime(value, "%H:%M")
            return True
        except (TypeError, ValueError):
            return False
