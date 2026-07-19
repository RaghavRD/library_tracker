from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/run-check/", views.run_daily_check_now, name="run_daily_check_now"),
    path("dashboard/run-check/status/", views.run_daily_check_status, name="run_daily_check_status"),
    path("projects/", views.projects_view, name="projects"),
    path("projects/parse-manifest/", views.parse_manifest, name="parse_manifest"),
    path("projects/import-github/", views.import_github_repo, name="import_github_repo"),
    path("update-history/", views.updateHistory, name="updateHistory"),
    path("future-updates/", views.future_updates, name="future_updates"),
    path("security-alerts/", views.security_alerts, name="security_alerts"),
    path("profile/", views.profile_view, name="profile"),
    path("settings/", views.settings_view, name="settings"),
]
