from django.urls import path

from apps.core import auth_views, views

app_name = "core"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("register/", auth_views.RegisterView.as_view(), name="register"),
]
