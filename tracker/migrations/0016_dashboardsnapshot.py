from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tracker", "0015_securityvulnerability"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scan_date", models.DateField(db_index=True)),
                ("total_components", models.PositiveIntegerField(default=0)),
                ("up_to_date_count", models.PositiveIntegerField(default=0)),
                ("updates_available_count", models.PositiveIntegerField(default=0)),
                ("future_predicted_count", models.PositiveIntegerField(default=0)),
                ("security_alerts_count", models.PositiveIntegerField(default=0)),
                ("vulnerabilities_count", models.PositiveIntegerField(default=0)),
                ("health_score", models.PositiveIntegerField(default=100)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dashboard_snapshots",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Dashboard Snapshot",
                "verbose_name_plural": "Dashboard Snapshots",
                "ordering": ["scan_date"],
                "unique_together": {("owner", "scan_date")},
            },
        ),
    ]
