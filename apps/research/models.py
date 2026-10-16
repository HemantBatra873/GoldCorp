"""Research / experiment models. Backtest execution lives in `trading/` (Phase 2)."""

from django.conf import settings
from django.db import models

from apps.core.models import Symbol, TimeStampedModel


class RunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class BacktestRun(TimeStampedModel):
    """
    A saved experiment: immutable configuration + lifecycle + summary metrics.

    Trades / equity curves are added in Phase 2–3 once the engine exists.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backtest_runs",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120, blank=True, default="")
    strategy_id = models.CharField(
        max_length=64,
        help_text="Stable strategy identifier, e.g. 'rsi_macd_v1'",
    )
    strategy_version = models.CharField(max_length=32, default="0.1.0")
    symbol = models.ForeignKey(
        Symbol,
        on_delete=models.PROTECT,
        related_name="backtest_runs",
        null=True,
        blank=True,
    )
    timeframe = models.CharField(max_length=16, default="4h")
    status = models.CharField(
        max_length=16,
        choices=RunStatus.choices,
        default=RunStatus.QUEUED,
        db_index=True,
    )

    # Immutable experiment snapshot (params, fees, slippage, data range, engine version)
    config = models.JSONField(default=dict, blank=True)
    config_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)

    data_start = models.DateTimeField(null=True, blank=True)
    data_end = models.DateTimeField(null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=255, blank=True, default="")

    # Summary metrics (populated when status=completed)
    total_trades = models.PositiveIntegerField(default=0)
    total_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    max_drawdown = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    profit_factor = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    win_rate = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["strategy_id", "-created_at"]),
        ]

    def __str__(self) -> str:
        label = self.name or f"{self.strategy_id}"
        return f"Run#{self.pk} {label} [{self.status}]"


class Trade(TimeStampedModel):
    """Persisted closed trade belonging to a BacktestRun."""

    run = models.ForeignKey(
        BacktestRun,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    side = models.CharField(max_length=4)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    exit_price = models.DecimalField(max_digits=20, decimal_places=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    entry_time = models.DateTimeField()
    exit_time = models.DateTimeField()
    fee = models.DecimalField(max_digits=20, decimal_places=8)
    profit = models.DecimalField(max_digits=20, decimal_places=8)
    close_method = models.CharField(max_length=8)
    sl_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    tp_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["exit_time", "id"]

    def __str__(self) -> str:
        return f"{self.side} {self.profit} ({self.close_method})"


class EquityPoint(models.Model):
    run = models.ForeignKey(
        BacktestRun,
        on_delete=models.CASCADE,
        related_name="equity_points",
    )
    timestamp = models.DateTimeField(null=True, blank=True)
    equity = models.DecimalField(max_digits=20, decimal_places=8)
    sequence = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sequence", "id"]
