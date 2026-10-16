from django.urls import path

from apps.paper import views

app_name = "paper"

urlpatterns = [
    path("paper/", views.paper_dashboard, name="dashboard"),
    path("paper/settings/", views.paper_settings, name="settings"),
    path("paper/toggle/", views.paper_toggle, name="toggle"),
    path("paper/run-once/", views.paper_run_once, name="run_once"),
]
