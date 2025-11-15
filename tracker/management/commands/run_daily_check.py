import os
import time
import schedule
from time import sleep
from pathlib import Path
from django.db import transaction
from dotenv import load_dotenv, find_dotenv
from packaging import version as pkg_version
from django.core.management.base import BaseCommand

from tracker.utils.google_sheet_manager import GoogleSheetManager
from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer
from tracker.utils.send_mail import send_update_email
from tracker.models import UpdateCache

# ✅ Locate .env manually (robust)
# Go three levels up (utils → tracker → LibTrack_AI)
BASE_DIR = Path(__file__).resolve().parents[3]
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    print(f"⚠️ .env not found at expected path: {env_path}")

load_dotenv()

class Command(BaseCommand):
    help = "Runs daily update check using Serper.dev + Groq and emails relevant updates via Mailtrap"

    def add_arguments(self, parser):
        parser.add_argument(
            "--auto",
            action="store_true",
            help="Run in auto-schedule mode (every day at 9:00 AM)",
        )

    def handle(self, *args, **options):
        if options.get("auto"):
            self.stdout.write(self.style.MIGRATE_HEADING("⏰ Auto mode: will run every day at 9:00 AM"))
            schedule.every().day.at("11:00").do(self.run_daily_check)
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

        # 1️⃣ Load registrations from Google Sheet
        try:
            gsm = GoogleSheetManager()
            regs = gsm.read_all_registrations()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"⚠️ GoogleSheetManager error: {e}"))
            return

        if not regs:
            self.stdout.write("No registrations found.")
            return

        groq = GroqAnalyzer()
        serper = SerperFetcher()

        for reg in regs:
            # Defensive coercion
            project = str(reg.get("project_name", "")).strip()
            emails_raw = reg.get("developer_emails", "")
            notify_pref = str(reg.get("notification_type", "both") or "both").lower()

            libs_raw = str(reg.get("libraries", "") or "")
            vers_raw = str(reg.get("library_versions", "") or "")
            languages_raw = str(reg.get("language_used", "") or "")
            language_versions_raw = str(reg.get("language_version", "") or "")

            emails = [e.strip() for e in str(emails_raw).split(",") if e.strip()]
            libs = [x.strip() for x in libs_raw.split(",") if x.strip()]
            vers = [x.strip() for x in vers_raw.split(",") if x.strip()]
            languages = [x.strip() for x in languages_raw.split(",") if x.strip()]
            language_versions = [x.strip() for x in language_versions_raw.split(",") if x.strip()]

            if not libs or not vers or len(libs) != len(vers):
                self.stdout.write(self.style.WARNING(f"⚠️ Skipping {project}: libs/versions mismatch"))
                continue

            project_updates = []
            project_updates.extend(
                self._process_components(
                    project=project,
                    names=libs,
                    versions=vers,
                    component_type="library",
                    groq=groq,
                    serper=serper,
                    notify_pref=notify_pref,
                )
            )
            project_updates.extend(
                self._process_components(
                    project=project,
                    names=languages,
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
                    project_name=project,
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
                self.stdout.write(f"Project digest for {project}: {ok} -> {info}")
            else:
                self.stdout.write(f"No qualifying updates for {project}.")

        self.stdout.write(self.style.SUCCESS("✅ Daily check completed successfully."))

    def _process_components(
        self,
        project: str,
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
                    f"⚠️ Skipping {project}: {component_type} name/version mismatch",
                )
            )
            return []

        updates: list[dict] = []
        for name, current_version in zip(names, versions):
            update = self._evaluate_component(
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
        name: str,
        current_version: str,
        groq: GroqAnalyzer,
        serper: SerperFetcher,
        notify_pref: str,
        component_type: str,
    ) -> dict | None:
        """Run Serper+Groq for a single component and return an update dict if we should email."""
        serper_results = serper.search_library(name, current_version)
        analysis = groq.analyze(name, serper_results)
        if analysis.get("error"):
            self.stdout.write(self.style.WARNING(f"[{name}] Groq error: {analysis['error']}"))
            return None

        library = analysis.get("library", name)
        version = analysis.get("version", "")
        category = analysis.get("category", "major")
        release_date = analysis.get("release_date", "")
        source = analysis.get("source", "")
        summary = analysis.get("summary", "")
        label = f"{component_type}:{library}"

        with transaction.atomic():
            cache, _ = UpdateCache.objects.select_for_update().get_or_create(
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
            should_send = True

            if should_send:
                if notify_pref == "major" and category != "major":
                    should_send = False
                elif notify_pref == "minor" and category != "minor":
                    should_send = False

            if version and current_version:
                try:
                    if pkg_version.parse(version) <= pkg_version.parse(current_version):
                        self.stdout.write(f"[{label}] Skipped — version {version} not newer than {current_version}")
                        should_send = False
                except Exception:
                    pass

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
