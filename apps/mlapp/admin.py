from django.contrib import admin

from apps.mlapp.models import MLModel


@admin.register(MLModel)
class MLModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "symbol", "timeframe", "status", "owner", "created_at")
    list_filter = ("status", "timeframe")
    search_fields = ("name", "artifact_path")
