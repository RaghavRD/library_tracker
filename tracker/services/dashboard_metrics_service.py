from __future__ import annotations

from datetime import timedelta

from django.db.models import Case, CharField, Count, Value, When
from django.utils import timezone

from tracker.models import (
    DashboardSnapshot,
    FutureUpdateCache,
    Project,
    SecurityVulnerability,
    StackComponent,
    UpdateCache,
)


class DashboardMetricsService:
    """Build dashboard metrics and daily snapshots for a single owner."""

    SEVERITY_ORDER = ("critical", "high", "medium", "low", "unknown")

    @classmethod
    def build_for_owner(cls, owner) -> dict:
        projects_qs = Project.objects.filter(owner=owner)
        total_projects = projects_qs.count()

        components_qs = StackComponent.objects.filter(project__owner=owner)
        dependency_components_qs = components_qs.exclude(key="language")
        total_components = dependency_components_qs.count()

        category_counts = cls._category_counts(components_qs)

        updates_qs = UpdateCache.objects.filter(project__owner=owner)
        total_updates = updates_qs.count()
        major_updates = updates_qs.filter(category="major").count()
        minor_updates = updates_qs.filter(category="minor").count()

        tracked_library_keys = cls._tracked_library_keys(owner)
        future_updates_count = cls._future_updates_count(tracked_library_keys)

        security_qs = SecurityVulnerability.objects.filter(project__owner=owner, status="active")
        security_alerts_count = security_qs.count()
        vulnerabilities_count = security_alerts_count

        up_to_date = max(0, total_components - total_updates - security_alerts_count)
        health_score = cls._health_score(total_components, total_updates, security_alerts_count)

        snapshots = cls._trend_snapshots(owner)
        if not snapshots:
            snapshots = [
                {
                    "date": "Current",
                    "vulnerabilities": vulnerabilities_count,
                    "securityAlerts": security_alerts_count,
                    "updatesAvailable": total_updates,
                    "upToDate": up_to_date,
                    "futurePredicted": future_updates_count,
                    "healthScore": health_score,
                }
            ]
        else:
            latest_snapshot = DashboardSnapshot.objects.filter(owner=owner).order_by("-scan_date").first()
            if latest_snapshot and latest_snapshot.scan_date < timezone.localdate():
                snapshots.append(
                    {
                        "date": "Current",
                        "vulnerabilities": vulnerabilities_count,
                        "securityAlerts": security_alerts_count,
                        "updatesAvailable": total_updates,
                        "upToDate": up_to_date,
                        "futurePredicted": future_updates_count,
                        "healthScore": health_score,
                    }
                )

        return {
            "total_projects": total_projects,
            "total_components": total_components,
            "total_updates": total_updates,
            "major_updates": major_updates,
            "minor_updates": minor_updates,
            "future_updates_count": future_updates_count,
            "security_alerts_count": security_alerts_count,
            "vulnerabilities_count": vulnerabilities_count,
            "up_to_date_count": up_to_date,
            "total_unique_stack_count": components_qs.values("name", "category").distinct().count(),
            "health_score": health_score,
            "languages_count": category_counts["languages"],
            "libraries_count": category_counts["libraries"],
            "tools_count": category_counts["tools"],
            "modules_count": category_counts["modules"],
            "trend_points": snapshots,
            "severity_counts": cls._severity_counts(security_qs),
            "top_risky_projects": cls._top_risky_projects(projects_qs, tracked_library_keys),
            "most_outdated_dependencies": cls._most_outdated_dependencies(updates_qs),
            "recent_security_alerts": cls._recent_security_alerts(security_qs),
            "action_items": cls._action_items(
                security_alerts_count=security_alerts_count,
                major_updates=major_updates,
                minor_updates=minor_updates,
                future_updates_count=future_updates_count,
                health_score=health_score,
            ),
            "scan_health": cls._scan_health(owner, total_components),
        }

    @classmethod
    def record_snapshot_for_owner(cls, owner) -> DashboardSnapshot:
        metrics = cls.build_for_owner(owner)
        today = timezone.localdate()
        snapshot, _ = DashboardSnapshot.objects.update_or_create(
            owner=owner,
            scan_date=today,
            defaults={
                "total_components": metrics["total_components"],
                "up_to_date_count": metrics["up_to_date_count"],
                "updates_available_count": metrics["total_updates"],
                "future_predicted_count": metrics["future_updates_count"],
                "security_alerts_count": metrics["security_alerts_count"],
                "vulnerabilities_count": metrics["vulnerabilities_count"],
                "health_score": metrics["health_score"],
            },
        )
        return snapshot

    @classmethod
    def record_all_owner_snapshots(cls) -> int:
        owner_ids = (
            Project.objects.exclude(owner__isnull=True)
            .values_list("owner_id", flat=True)
            .distinct()
        )
        count = 0
        for owner_id in owner_ids:
            owner = Project._meta.get_field("owner").remote_field.model.objects.get(pk=owner_id)
            cls.record_snapshot_for_owner(owner)
            count += 1
        return count

    @staticmethod
    def _category_counts(components_qs) -> dict[str, int]:
        annotated_components = components_qs.annotate(
            norm_cat=Case(
                When(key__icontains="language", then=Value("languages")),
                When(category__icontains="language", then=Value("languages")),
                When(category__icontains="tool", then=Value("tools")),
                When(category__icontains="module", then=Value("modules")),
                default=Value("libraries"),
                output_field=CharField(),
            )
        )
        counts = {"languages": 0, "libraries": 0, "tools": 0, "modules": 0}
        for entry in annotated_components.values("norm_cat").annotate(unique_count=Count("name", distinct=True)):
            if entry["norm_cat"] in counts:
                counts[entry["norm_cat"]] = entry["unique_count"]
        return counts

    @staticmethod
    def _tracked_library_keys(owner) -> set[str]:
        names = (
            StackComponent.objects.filter(project__owner=owner)
            .exclude(key="language")
            .values_list("name", flat=True)
        )
        return {name.strip().lower() for name in names if name and name.strip()}

    @staticmethod
    def _future_updates_count(tracked_library_keys: set[str]) -> int:
        if not tracked_library_keys:
            return 0
        return sum(
            1
            for update in FutureUpdateCache.objects.filter(status__in=["detected", "confirmed"])
            if (update.library or "").strip().lower() in tracked_library_keys
        )

    @staticmethod
    def _health_score(total_components: int, total_updates: int, security_alerts: int) -> int:
        if total_components <= 0:
            return 100
        weighted_risk = total_updates + (security_alerts * 2)
        ratio = min(weighted_risk / total_components, 1.0)
        return int((1.0 - ratio) * 100)

    @classmethod
    def _trend_snapshots(cls, owner) -> list[dict]:
        since = timezone.localdate() - timedelta(days=13)
        snapshots = DashboardSnapshot.objects.filter(owner=owner, scan_date__gte=since).order_by("scan_date")
        return [
            {
                "date": snapshot.scan_date.strftime("%b %d"),
                "vulnerabilities": snapshot.vulnerabilities_count,
                "securityAlerts": snapshot.security_alerts_count,
                "updatesAvailable": snapshot.updates_available_count,
                "upToDate": snapshot.up_to_date_count,
                "futurePredicted": snapshot.future_predicted_count,
                "healthScore": snapshot.health_score,
            }
            for snapshot in snapshots
        ]

    @classmethod
    def _severity_counts(cls, security_qs) -> dict[str, int]:
        counts = {key: 0 for key in cls.SEVERITY_ORDER}
        for raw in security_qs.values_list("severity", flat=True):
            value = (raw or "").strip().lower()
            bucket = "unknown"
            for candidate in cls.SEVERITY_ORDER[:-1]:
                if candidate in value:
                    bucket = candidate
                    break
            counts[bucket] += 1
        return counts

    @classmethod
    def _top_risky_projects(cls, projects_qs, tracked_library_keys: set[str]) -> list[dict]:
        future_updates = FutureUpdateCache.objects.filter(status__in=["detected", "confirmed"])
        future_by_library = {
            (update.library or "").strip().lower()
            for update in future_updates
            if (update.library or "").strip().lower() in tracked_library_keys
        }

        rows = []
        for project in projects_qs.prefetch_related("components"):
            project_library_keys = {
                component.name.strip().lower()
                for component in project.components.all()
                if component.key != "language" and component.name and component.name.strip()
            }
            updates = UpdateCache.objects.filter(project=project)
            vulnerabilities = SecurityVulnerability.objects.filter(project=project, status="active").count()
            major = updates.filter(category="major").count()
            minor = updates.filter(category="minor").count()
            future = len(project_library_keys & future_by_library)
            score = (vulnerabilities * 5) + (major * 3) + minor + future
            if score:
                rows.append(
                    {
                        "project_name": project.project_name,
                        "risk_score": score,
                        "vulnerabilities": vulnerabilities,
                        "major_updates": major,
                        "minor_updates": minor,
                        "future_predictions": future,
                    }
                )
        return sorted(rows, key=lambda row: row["risk_score"], reverse=True)[:5]

    @staticmethod
    def _most_outdated_dependencies(updates_qs) -> list[dict]:
        rows = []
        for update in updates_qs.select_related("project").order_by("-category", "-updated_at")[:6]:
            rows.append(
                {
                    "project_name": update.project.project_name,
                    "library": update.library,
                    "target_version": update.version,
                    "category": update.category,
                }
            )
        return rows

    @staticmethod
    def _recent_security_alerts(security_qs) -> list[dict]:
        rows = []
        for alert in security_qs.select_related("project").order_by("-updated_at")[:5]:
            rows.append(
                {
                    "project_name": alert.project.project_name,
                    "library": alert.library,
                    "version": alert.version,
                    "severity": alert.severity or "Unknown",
                    "osv_id": alert.osv_id,
                }
            )
        return rows

    @staticmethod
    def _action_items(
        *,
        security_alerts_count: int,
        major_updates: int,
        minor_updates: int,
        future_updates_count: int,
        health_score: int,
    ) -> list[dict]:
        items = []
        if security_alerts_count:
            items.append({"label": f"Fix {security_alerts_count} active security alert(s)", "level": "danger"})
        if major_updates:
            items.append({"label": f"Review {major_updates} major update(s)", "level": "warning"})
        if minor_updates:
            items.append({"label": f"Plan {minor_updates} minor update(s)", "level": "info"})
        if future_updates_count:
            items.append({"label": f"Validate {future_updates_count} future prediction(s)", "level": "primary"})
        if health_score < 70:
            items.append({"label": "Health score is below 70%, prioritize cleanup", "level": "danger"})
        if not items:
            items.append({"label": "No urgent action needed right now", "level": "success"})
        return items[:5]

    @staticmethod
    def _scan_health(owner, total_components: int) -> dict:
        latest_snapshot = DashboardSnapshot.objects.filter(owner=owner).order_by("-scan_date").first()
        return {
            "last_scan_label": latest_snapshot.scan_date.strftime("%b %d, %Y") if latest_snapshot else "No snapshot yet",
            "scanned_components": latest_snapshot.total_components if latest_snapshot else total_components,
            "history_points": DashboardSnapshot.objects.filter(owner=owner).count(),
            "status": "Trend ready" if latest_snapshot else "Current snapshot only",
        }
