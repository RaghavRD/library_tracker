"""
clean_summaries: shorten release and future-update summaries already in the database.

New rows are cleaned as they are saved. This command is for rows written before
that, which can hold a whole README, HTML tables or raw markdown. Summaries are
rewritten in place; the text they were built from is not kept, so run with
--dry-run first to see what would change.

Security findings are deliberately left alone: their stored text feeds the
change signature that decides whether a finding is re-notified, so rewriting it
would email every user about findings they have already seen. Those are cleaned
when the email is built instead.

Usage:
  python manage.py clean_summaries --dry-run
  python manage.py clean_summaries
  python manage.py clean_summaries --no-ai      # rule-based cleaning only
"""

import logging

from django.core.management.base import BaseCommand

from tracker.models import FutureUpdateCache, LibraryRelease
from tracker.utils.text_summary import looks_unsummarized, summarize

logger = logging.getLogger("libtrack")


class Command(BaseCommand):
    help = "Clean and shorten stored release and future-update summaries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            "--no-ai",
            action="store_true",
            help="Trim long text instead of asking Groq to summarize it.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many rows per model (0 means no limit).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        allow_ai = not options["no_ai"]
        limit = options["limit"] or None

        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry run: nothing will be written."))

        releases = self._clean(
            LibraryRelease.objects.exclude(summary="").order_by("pk"),
            field="summary",
            label="release",
            dry_run=dry_run,
            allow_ai=allow_ai,
            limit=limit,
            describe=lambda row: f"{row.library.name} {row.version}",
        )
        futures = self._clean(
            FutureUpdateCache.objects.exclude(features="").order_by("pk"),
            field="features",
            label="future update",
            dry_run=dry_run,
            allow_ai=allow_ai,
            limit=limit,
            describe=lambda row: f"{row.library} {row.version}",
        )

        verb = "would be cleaned" if dry_run else "cleaned"
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ {releases} release summary(ies) and {futures} future-update "
                f"summary(ies) {verb}."
            )
        )

    def _clean(self, queryset, *, field, label, dry_run, allow_ai, limit, describe):
        changed = 0
        for row in queryset.iterator():
            if limit is not None and changed >= limit:
                break
            original = getattr(row, field) or ""
            if not looks_unsummarized(original):
                continue

            name = describe(row)
            cleaned = summarize(
                original,
                library=getattr(row.library, "name", str(row.library)),
                version=row.version,
                allow_ai=allow_ai,
            )
            if cleaned == original.strip():
                continue

            changed += 1
            self.stdout.write(
                f"  {label} {name}: {len(original)} → {len(cleaned)} chars"
            )
            if not cleaned:
                self.stdout.write(
                    self.style.WARNING(f"    nothing left after cleaning; leaving as is")
                )
                continue
            if not dry_run:
                setattr(row, field, cleaned)
                row.save(update_fields=[field, "updated_at"])
        return changed
