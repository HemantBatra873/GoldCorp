from django.urls import path

from apps.research import views

app_name = "research"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("runs/", views.run_list, name="run_list"),
    path("runs/new/", views.run_create, name="run_create"),
    path("runs/lab/", views.strategy_lab, name="strategy_lab"),
    path("runs/compare/", views.run_compare, name="run_compare"),
    path("runs/<int:run_id>/", views.run_detail, name="run_detail"),
    path("runs/<int:run_id>/cancel/", views.run_cancel, name="run_cancel"),
    path("api/runs/", views.api_runs, name="api_runs"),
]
