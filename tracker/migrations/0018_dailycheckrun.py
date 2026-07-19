from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tracker", "0017_securityvulnerability_notification_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyCheckRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scope",
                    models.CharField(
                        choices=[("owner", "Current user"), ("global", "All users")],
                        default="owner",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("partial", "Partial"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.FloatField(blank=True, null=True)),
                ("projects_scanned", models.PositiveIntegerField(default=0)),
                ("libraries_checked", models.PositiveIntegerField(default=0)),
                ("future_updates_found", models.PositiveIntegerField(default=0)),
                ("security_findings_found", models.PositiveIntegerField(default=0)),
                ("emails_attempted", models.PositiveIntegerField(default=0)),
                ("emails_sent", models.PositiveIntegerField(default=0)),
                ("emails_failed", models.PositiveIntegerField(default=0)),
                ("emails_skipped", models.PositiveIntegerField(default=0)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                (
                    "scope_owner",
                    models.ForeignKey(
                        blank=True,
                        help_text="Owner whose projects were checked for owner-scoped runs",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scoped_daily_check_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "triggered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="daily_check_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Daily Check Run",
                "verbose_name_plural": "Daily Check Runs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["scope_owner", "status"], name="tracker_dai_scope_o_a6f35a_idx"),
                    models.Index(fields=["triggered_by", "-created_at"], name="tracker_dai_trigger_b6577e_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="notificationrecord",
            name="daily_check_run",
            field=models.ForeignKey(
                blank=True,
                help_text="Manual or scheduled run that produced this notification attempt",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notification_records",
                to="tracker.dailycheckrun",
            ),
        ),
    ]
