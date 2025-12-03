from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    # path("register/", views.register_project, name="register_project"),
    path("update-history/", views.updateHistory, name="updateHistory"),
    path("future-updates/", views.future_updates, name="future_updates"),
]
