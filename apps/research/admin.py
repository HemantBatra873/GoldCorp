from django.contrib import admin

from .models import BacktestRun, EquityPoint, Trade


class TradeInline(admin.TabularInline):
    model = Trade
    extra = 0
    readonly_fields = (
        "side",
        "entry_price",
        "exit_price",
        "profit",
        "fee",
        "close_method",
        "entry_time",
        "exit_time",
    )
    can_delete = False


@admin.register(BacktestRun)
class BacktestRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "strategy_id",
        "symbol",
        "status",
        "total_trades",
        "total_pnl",
        "owner",
        "created_at",
    )
    list_filter = ("status", "strategy_id", "timeframe")
    search_fields = ("name", "strategy_id", "config_hash", "celery_task_id")
    readonly_fields = ("created_at", "updated_at", "config_hash")
    raw_id_fields = ("owner", "symbol")
    inlines = [TradeInline]


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "side", "profit", "close_method", "exit_time")
    list_filter = ("side", "close_method")
    raw_id_fields = ("run",)


@admin.register(EquityPoint)
class EquityPointAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "sequence", "equity", "timestamp")
    raw_id_fields = ("run",)
