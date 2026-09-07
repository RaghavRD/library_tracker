from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/run-check/", views.run_daily_check_now, name="run_daily_check_now"),
    path("dashboard/run-check/status/", views.run_daily_check_status, name="run_daily_check_status"),
    path("internal/cron/daily-check/", views.run_scheduled_daily_check, name="run_scheduled_daily_check"),
    path("projects/", views.projects_view, name="projects"),
    path("projects/import-github/", views.import_github_repo, name="import_github_repo"),
    path("projects/github-repositories/", views.github_repositories, name="github_repositories"),
    path("update-history/", views.updateHistory, name="updateHistory"),
    path("future-updates/", views.future_updates, name="future_updates"),
    path("security-alerts/", views.security_alerts, name="security_alerts"),
    path("profile/", views.profile_view, name="profile"),
    path("settings/", views.settings_view, name="settings"),
]
