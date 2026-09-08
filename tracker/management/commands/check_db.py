"""
check_db: Show which database this process would actually talk to.

Run this before any command that writes - migrate above all - so you find out
what you are pointed at before you change it, not afterwards.

The check exists because settings.py falls back to SQLite when DATABASE_URL is
set but dj-database-url is not installed. That failure is silent: `migrate`
reports "No migrations to apply" against the local SQLite file and looks like it
succeeded, while the real database was never touched.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "Show which database is configured, and warn if it is not the one you meant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--connect",
            action="store_true",
            help="Also open a connection and report the server version.",
        )

    def handle(self, *args, **options):
        config = settings.DATABASES["default"]
        engine = config["ENGINE"].rsplit(".", 1)[-1]
        database_url_set = bool(os.getenv("DATABASE_URL", "").strip())

        self.stdout.write(self.style.MIGRATE_HEADING("Database target"))
        self.stdout.write(f"  ENGINE : {config['ENGINE']}")
        self.stdout.write(f"  NAME   : {config.get('NAME')}")
        self.stdout.write(f"  HOST   : {config.get('HOST') or '(local file)'}")
        self.stdout.write(f"  PORT   : {config.get('PORT') or '-'}")
        self.stdout.write(f"  USER   : {config.get('USER') or '-'}")
        self.stdout.write(f"  DATABASE_URL set: {'yes' if database_url_set else 'no'}")

        if engine == "sqlite3" and database_url_set:
            self.stdout.write("")
            # Flush first: stderr is unbuffered, so without this the warning
            # can appear above the details it refers to when output is piped.
            self.stdout.flush()
            self.stderr.write(self.style.ERROR(
                "STOP. DATABASE_URL is set but SQLite is configured.\n"
                "  dj-database-url is probably not installed, so settings.py fell back\n"
                "  to the local file. Any migration you run now would hit SQLite, not\n"
                "  your server, and would report success.\n"
                "  Fix: pip install -r requirements.txt"
            ))
            raise SystemExit(1)

        if engine == "sqlite3":
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Local SQLite. Safe to experiment."))
        else:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "REMOTE DATABASE. Anything you run now affects this server."
            ))
            port = str(config.get("PORT") or "")
            if port == "6543":
                self.stdout.write(self.style.WARNING(
                    "  Port 6543 is Supabase's transaction pooler; DDL is unreliable there.\n"
                    "  Use port 5432 for migrations."
                ))

        if options["connect"]:
            self.stdout.write("")
            self.stdout.write("Connecting...")
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT version();" if engine != "sqlite3" else "SELECT sqlite_version();")
                self.stdout.write(self.style.SUCCESS(f"  Connected: {cursor.fetchone()[0]}"))
