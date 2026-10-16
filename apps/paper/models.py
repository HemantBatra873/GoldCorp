from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class PaperMode(models.TextChoices):
    SIMULATED = "simulated", "Simulated (local fills)"
    TESTNET = "testnet", "Binance Futures Testnet"


class PaperSession(TimeStampedModel):
    """Active paper-trading bot configuration for a user."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="paper_sessions",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120, default="default")
    is_active = models.BooleanField(default=False)
    mode = models.CharField(
        max_length=16,
        choices=PaperMode.choices,
        default=PaperMode.SIMULATED,
    )
    strategy_id = models.CharField(max_length=64, default="rsi_macd_stoch")
    symbols = models.JSONField(default=list)  # e.g. ["BTCUSDT"]
    timeframe = models.CharField(max_length=16, default="4h")
    notional = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    leverage = models.PositiveIntegerField(default=5)
    strategy_params = models.JSONField(default=dict, blank=True)
    execution_config = models.JSONField(default=dict, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"PaperSession#{self.pk} {self.name} [{self.mode}] active={self.is_active}"


class PaperPosition(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    session = models.ForeignKey(
        PaperSession,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=4)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    notional = models.DecimalField(max_digits=20, decimal_places=8)
    sl_price = models.DecimalField(max_digits=20, decimal_places=8)
    tp_price = models.DecimalField(max_digits=20, decimal_places=8)
    factor_ajuste = models.FloatField(default=0.0)
    alt_tp_sl = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    entry_order_id = models.CharField(max_length=64, blank=True, default="")
    sl_order_id = models.CharField(max_length=64, blank=True, default="")
    tp_order_id = models.CharField(max_length=64, blank=True, default="")
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [models.Index(fields=["status", "symbol"])]

    def __str__(self) -> str:
        return f"{self.side} {self.symbol} @ {self.entry_price} [{self.status}]"


class PaperFill(TimeStampedModel):
    session = models.ForeignKey(
        PaperSession,
        on_delete=models.CASCADE,
        related_name="fills",
    )
    position = models.ForeignKey(
        PaperPosition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fills",
    )
    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=4)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    exit_price = models.DecimalField(max_digits=20, decimal_places=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    fee = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    profit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    close_method = models.CharField(max_length=16)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField()
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-closed_at"]


class PaperEvent(TimeStampedModel):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    class Kind(models.TextChoices):
        HEARTBEAT = "heartbeat", "Heartbeat"
        SIGNAL = "signal", "Signal"
        ORDER = "order", "Order"
        FILL = "fill", "Fill"
        REJECT = "reject", "Reject"
        ERROR = "error", "Error"
        RECONCILE = "reconcile", "Reconcile"
        TRAIL = "trail", "Trail"

    session = models.ForeignKey(
        PaperSession,
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
    )
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.INFO)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    message = models.CharField(max_length=500)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
