from django.contrib import admin

from apps.paper.models import PaperEvent, PaperFill, PaperPosition, PaperSession


@admin.register(PaperSession)
class PaperSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "mode", "is_active", "strategy_id", "last_heartbeat_at")
    list_filter = ("mode", "is_active", "strategy_id")


@admin.register(PaperPosition)
class PaperPositionAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "symbol", "side", "status", "entry_price", "opened_at")
    list_filter = ("status", "side", "symbol")


@admin.register(PaperFill)
class PaperFillAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "symbol", "side", "profit", "close_method", "closed_at")


@admin.register(PaperEvent)
class PaperEventAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "level", "kind", "message", "created_at")
    list_filter = ("level", "kind")
