"""Shared domain models used across GoldCorp apps."""

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Symbol(TimeStampedModel):
    """Tradable instrument (e.g. BTCUSDT on Binance USD-M Futures)."""

    symbol = models.CharField(max_length=32, unique=True)
    base_asset = models.CharField(max_length=16, blank=True, default="")
    quote_asset = models.CharField(max_length=16, blank=True, default="")
    is_active = models.BooleanField(default=True)
    exchange = models.CharField(max_length=32, default="binance_futures")

    class Meta:
        ordering = ["symbol"]

    def __str__(self) -> str:
        return self.symbol
