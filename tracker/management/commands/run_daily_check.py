import os
import time
import logging
import schedule
from time import sleep
from pathlib import Path
from datetime import datetime
from django.db import transaction
from dotenv import load_dotenv, find_dotenv
from packaging import version as pkg_version
from packaging.version import InvalidVersion
from django.core.management.base import BaseCommand, CommandError

from tracker.utils.serper_fetcher import SerperFetcher
from tracker.utils.groq_analyzer import GroqAnalyzer
from tracker.utils.send_mail import send_update_email
from tracker.models import UpdateCache, Project, FutureUpdateCache, Library, LibraryRelease, StackComponent

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

        mailtrap_key = os.getenv("MAILTRAP_API_KEY")
        sender_email = os.getenv("MAILTRAP_FROM_EMAIL")

        if not mailtrap_key or not sender_email:
            self.stdout.write(self.style.ERROR("❌ Missing Mailtrap credentials."))
            return

        # 1. SYNC: Map all components to central `Library` entities
        self.stdout.write(self.style.MIGRATE_HEADING("1. Syncing Libraries..."))
        self._sync_libraries()
        
        # 2. FETCH: Update each unique Library (Only 1 API call per lib!)
        self.stdout.write(self.style.MIGRATE_HEADING("2. Fetching Updates for Libraries..."))
        self._update_libraries()
        
        # 3. NOTIFY: Check projects against the updated Library data
        self.stdout.write(self.style.MIGRATE_HEADING("3. Notifying Projects..."))
        self._notify_projects(mailtrap_key, sender_email)

        self.stdout.write(self.style.SUCCESS("✅ Daily check completed successfully."))

    def _sync_libraries(self):
        """
        Iterate over all StackComponents that are not linked to a Library.
        Create/Find the Library and link it.
        """
        components = StackComponent.objects.filter(library_ref__isnull=True)
        count = components.count()
        self.stdout.write(f"Found {count} unlinked components.")
        
        for comp in components:
            # Normalize key
            raw_name = comp.name.strip()
            key = raw_name.lower().replace(" ", "-") # Simplified normalization
            
            # Determine type
            ctype = "library"
            if comp.key == "language":
                ctype = "language"
            
            library, created = Library.objects.get_or_create(
                key=key,
                defaults={
                    "name": raw_name,
                    "component_type": ctype
                }
            )
            
            comp.library_ref = library
            comp.save()
            if created:
                self.stdout.write(f"[NEW] Created Library: {library.name}")
    
    def _update_libraries(self):
        """
        Fetch updates for all Libraries.
        """
        groq = GroqAnalyzer()
        serper = SerperFetcher()
        
        # Only check libraries that are actually used (linked to at least one component)
        # to avoid checking libraries that were deleted from all projects.
        libraries = Library.objects.filter(linked_components__isnull=False).distinct()
        self.stdout.write(f"Checking {libraries.count()} unique libraries...")

        for library in libraries:
            self.stdout.write(f"   Checking {library.name} (current: v{library.latest_version or 'unknown'})...")
            
            # Call Serper/Groq
            # We pass library.latest_version as "current_version" to detecting NEWER stuff
            updates = self._evaluate_component(
                project=None, # No project context needed for simple library check
                name=library.name,
                current_version=library.latest_version,
                groq=groq,
                serper=serper,
                notify_pref="all", # Get everything
                component_type=library.component_type,
                is_library_check=True 
            )
            
            # Debug logging to see what Groq returned
            if updates and isinstance(updates, dict):
                detected_version = updates.get("version")
                self.stdout.write(f"[DEBUG] Groq detected version: {detected_version}")
                self.stdout.write(f"[DEBUG] Current stored version: {library.latest_version or 'empty'}")
                
                if detected_version:
                    # ✅ FIX: Only save if the new version is ACTUALLY newer
                    should_update = False
                    skip_reason = ""
                    
                    try:
                        # Handle empty current version
                        if not library.latest_version:
                            should_update = True
                            skip_reason = "no previous version"
                        else:
                            parsed_new = pkg_version.parse(detected_version)
                            parsed_current = pkg_version.parse(library.latest_version)
                            
                            if parsed_new > parsed_current:
                                should_update = True
                            elif parsed_new == parsed_current:
                                skip_reason = f"same version ({detected_version})"
                            else:
                                skip_reason = f"older version (detected {detected_version} < current {library.latest_version})"
                        
                        if should_update:
                            library.latest_version = detected_version
                            library.last_checked_at = datetime.now()
                            library.save()
                            
                            # Extract summary and source from updates
                            summary_text = updates.get("summary", "")
                            source_url = updates.get("source", "")
                            release_date_str = updates.get("release_date", "")
                            
                            # Parse the release date from Groq (format: YYYY-MM-DD or text like "Not Confirmed")
                            parsed_release_date = None
                            if release_date_str:
                                try:
                                    # Try to parse as YYYY-MM-DD
                                    from datetime import datetime as dt
                                    parsed_release_date = dt.strptime(release_date_str, "%Y-%m-%d").date()
                                except (ValueError, TypeError):
                                    # If parsing fails, try other common formats or leave as None
                                    try:
                                        # Try MM/DD/YYYY
                                        parsed_release_date = dt.strptime(release_date_str, "%m/%d/%Y").date()
                                    except (ValueError, TypeError):
                                        # If still fails, use today as fallback only if it looks like a valid recent date
                                        # Otherwise leave as None to avoid showing incorrect dates
                                        self.stdout.write(f"[WARN] Could not parse release_date: {release_date_str}")
                                        parsed_release_date = None
                            
                            # Fallback to today's date only if no date was provided at all
                            if parsed_release_date is None:
                                parsed_release_date = datetime.now().date()
                            
                            # Debug: Show what we're about to save
                            self.stdout.write(f"[DEBUG] Saving LibraryRelease:")
                            self.stdout.write(f"- Summary: {summary_text[:80]}{'...' if len(summary_text) > 80 else ''}" if summary_text else f"- Summary: EMPTY")
                            self.stdout.write(f"- Source: {source_url}" if source_url else f"- Source: EMPTY")
                            self.stdout.write(f"- Release Date: {parsed_release_date} (from Groq: '{release_date_str}')")
                            
                            # Save history
                            release, created = LibraryRelease.objects.get_or_create(
                                library=library,
                                version=detected_version,
                                defaults={
                                    "release_date": parsed_release_date,
                                    "summary": summary_text,
                                    "source_url": source_url,
                                    "is_security_release": False
                                }
                            )
                            
                            if not created:
                                # Update existing release with new data
                                release.summary = summary_text
                                release.source_url = source_url
                                release.release_date = parsed_release_date
                                release.save()
                            
                            self.stdout.write(self.style.SUCCESS(f"✅ Updated to v{detected_version}"))
                        else:
                            self.stdout.write(f"⏭️  Skipped: {skip_reason}")
                            
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"⚠️  Version comparison failed: {e}"))
            else:
                self.stdout.write(f"ℹ️  No update detected by Groq")
            
            sleep(1.5) # Rate limiting

    def _notify_projects(self, mailtrap_key, sender_email):
        """
        Fan-out notifications to projects.
        """
        projects = Project.objects.prefetch_related("components__library_ref").all()
        
        for project in projects:
            project_name = project.project_name
            emails = [e.strip() for e in (project.developer_emails or "").split(",") if e.strip()]
            if not emails:
                continue
                
            updates_to_send = []
            
            for comp in project.components.all():
                lib = comp.library_ref
                if not lib:
                    continue
                
                # Comparison Logic
                # current: comp.version
                # latest: lib.latest_version
                if not lib.latest_version:
                    continue
                
                try:
                    if pkg_version.parse(lib.latest_version) > pkg_version.parse(comp.version):
                        # Use the LibraryRelease metadata if available
                        release = lib.releases.filter(version=lib.latest_version).first()
                        
                        # Debug logging
                        self.stdout.write(f"[NOTIFY] {lib.name} {lib.latest_version}:")
                        if release:
                            self.stdout.write(f"- LibraryRelease found: YES")
                            self.stdout.write(f"- Summary: {release.summary[:80]}{'...' if len(release.summary) > 80 else ''}" if release.summary else "- Summary: EMPTY")
                            self.stdout.write(f"- Source: {release.source_url}" if release.source_url else "- Source: EMPTY")
                        else:
                            self.stdout.write(f"- LibraryRelease found: NO (will use default text)")
                        
                        summary = release.summary if release else "New version available"
                        source = release.source_url if release else ""
                        
                        updates_to_send.append({
                            "library": lib.name,
                            "version": lib.latest_version,
                            "category": "major", # Simplify for now
                            "release_date": str(release.release_date) if release else "",
                            "summary": summary,
                            "source": source
                        })
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"[NOTIFY] Error processing {comp.name}: {e}"))
                    continue

            if updates_to_send:
                self.stdout.write(self.style.SUCCESS(f"Sending {len(updates_to_send)} updates to {project_name}"))
                
                # Re-use existing email function
                # Note: We need to adapt the payload to what send_update_email expects
                # We aggregate everything
                
                category = "mix"
                subject_library = updates_to_send[0]["library"]
                subject_version = updates_to_send[0]["version"]
                if len(updates_to_send) > 1:
                     subject_library += f" + {len(updates_to_send)-1} others"
                
                send_update_email(
                    mailtrap_api_key=mailtrap_key,
                    project_name=project_name,
                    recipients=emails,
                    library=subject_library,
                    version=subject_version,
                    category=category,
                    summary="Updates detected in your stack.",
                    source="",
                    release_date="",
                    updates=updates_to_send,
                    from_email=sender_email
                )

    def _process_components(self, *args, **kwargs):
         # DEPRECATED - Kept empty to satisfy structure if called elsewhere, but we don't use it.
         pass
         
    def _evaluate_component(
        self,
        *,
        project: Project | None,
        name: str,
        current_version: str,
        groq: GroqAnalyzer,
        serper: SerperFetcher,
        notify_pref: str,
        component_type: str,
        is_library_check: bool = False,
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

        if is_library_check:
             return {
                 "library": library,
                 "version": version or current_version or "unknown",
                 "category": category,
                 "release_date": release_date or "Unknown",
                 "summary": summary or "No summary.",
                 "source": source or "",
                 "component_type": component_type,
                 "is_released": is_released
             }

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

        if is_library_check:
             # Just return it to the caller (update_libraries)
             return {
                 "library": library,
                 "version": version or current_version or "unknown",
                 "category": category,
                 "release_date": release_date or "Unknown",
                 "summary": summary or "No summary.",
                 "source": source or "",
                 "component_type": component_type,
                 "is_released": is_released # Pass this through
             }

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
                confidence_increased = False
                old_confidence = future_cache.confidence
                change_reason_parts = []
                
                # Check for confidence increase
                if confidence > future_cache.confidence:
                    confidence_difference = confidence - future_cache.confidence
                    future_cache.previous_confidence = future_cache.confidence
                    future_cache.confidence = confidence
                    update_needed = True
                    confidence_increased = True
                    
                    # Determine reason for confidence increase
                    if source and source != future_cache.source:
                        # Detect source authority upgrade
                        old_source_domain = future_cache.source.split('/')[2] if '/' in future_cache.source else ''
                        new_source_domain = source.split('/')[2] if '/' in source else ''
                        
                        # Check if upgraded to official site
                        official_indicators = ['official', '.org', 'docs.', 'blog.', 'developer.']
                        is_official_upgrade = any(ind in new_source_domain for ind in official_indicators)
                        community_indicators = ['reddit', 'medium', 'dev.to', 'stackoverflow']
                        from_community = any(ind in old_source_domain for ind in community_indicators)
                        
                        if is_official_upgrade and from_community:
                            change_reason_parts.append(f"Featured on official site ({new_source_domain})")
                        elif is_official_upgrade:
                            change_reason_parts.append(f"Now confirmed on {new_source_domain}")
                        else:
                            change_reason_parts.append(f"Additional source found ({new_source_domain})")
                    else:
                        change_reason_parts.append("Increased confidence from same source")
                
                # Check for other updates
                if summary and summary != future_cache.features:
                    future_cache.features = summary
                    update_needed = True
                    if not change_reason_parts:
                        change_reason_parts.append("Updated feature details available")
                
                if source and source != future_cache.source:
                    future_cache.source = source
                    update_needed = True
                
                if parsed_date and parsed_date != future_cache.expected_date:
                    old_date = future_cache.expected_date
                    future_cache.expected_date = parsed_date
                    update_needed = True
                    if old_date and parsed_date < old_date:
                        change_reason_parts.append(f"Release date moved earlier (was {old_date})")
                    elif old_date:
                        change_reason_parts.append(f"Release date updated to {parsed_date}")
                    else:
                        change_reason_parts.append(f"Release date now available: {parsed_date}")
                
                # Save change reason
                if change_reason_parts:
                    future_cache.last_change_reason = "; ".join(change_reason_parts)
                
                if update_needed:
                    future_cache.save()
                    self.stdout.write(f"[{label}] Updated existing future update entry with new info.")
                    
                    # ==== CONFIDENCE INCREASE NOTIFICATION ====
                    # Threshold for re-notification: 15% increase or more
                    MIN_CONFIDENCE_INCREASE = 15
                    
                    if confidence_increased and confidence_difference >= MIN_CONFIDENCE_INCREASE:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[{label}] 📈 Significant confidence increase detected: "
                                f"{old_confidence}% → {confidence}% (+{confidence_difference}%)"
                            )
                        )
                        
                        # Import and send confidence update email
                        from tracker.utils.confidence_email import send_confidence_update_email
                        from tracker.models import Project
                        
                        # Get project and email recipients (we need to pass them)
                        # Since we don't have project context here, we'll return a special flag
                        # and handle it in the calling code
                        return {
                            "library": library,
                            "version": version,
                            "category": "confidence_update",  # Special category for confidence updates
                            "release_date": expected_date or "TBD",
                            "summary": summary or "Upcoming release detected.",
                            "source": source or "",
                            "component_type": component_type,
                            "confidence": confidence,
                            "old_confidence": old_confidence,
                            "confidence_difference": confidence_difference,
                            "change_reason": future_cache.last_change_reason,
                        }
            
            # Mark as notified (only for first-time detection)
            if created:
                future_cache.notification_sent = True
                future_cache.notification_sent_at = datetime.now()
                future_cache.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{label}] ✅ Future update notification prepared: v{version} "
                    f"(confidence: {confidence}%, expected: {expected_date or 'TBD'})"
                )
            )
            
            # Return notification payload (only for new detections)
            if created:
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
