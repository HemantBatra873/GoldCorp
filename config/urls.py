"""URL configuration for GoldCorp."""

from django.contrib import admin
from django.urls import include, path

from apps.core.auth_views import GoldCorpLoginView, GoldCorpLogoutView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", GoldCorpLoginView.as_view(), name="login"),
    path("accounts/logout/", GoldCorpLogoutView.as_view(), name="logout"),
    path("", include("apps.core.urls")),
    path("", include("apps.research.urls")),
    path("", include("apps.paper.urls")),
    path("", include("apps.mlapp.urls")),
]
