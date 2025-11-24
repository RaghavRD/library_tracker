from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    # path("register/", views.register_project, name="register_project"),
    path("update-history/", views.updateHistory, name="updateHistory"),
]
