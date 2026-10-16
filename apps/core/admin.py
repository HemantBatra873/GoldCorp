from django.contrib import admin

from .models import Symbol


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ("symbol", "exchange", "is_active", "updated_at")
    list_filter = ("exchange", "is_active")
    search_fields = ("symbol", "base_asset", "quote_asset")
