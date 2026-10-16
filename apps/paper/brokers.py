"""Build broker adapters from Django settings / session mode."""

from __future__ import annotations

from django.conf import settings

from apps.paper.models import PaperMode, PaperSession
from trading.exchange.binance_futures import BinanceFuturesClient
from trading.exchange.simulated import SimulatedBroker


def get_broker_for_session(session: PaperSession):
    if session.mode == PaperMode.TESTNET:
        key = getattr(settings, "BINANCE_API_KEY", "") or ""
        secret = getattr(settings, "BINANCE_API_SECRET", "") or ""
        return BinanceFuturesClient(
            key,
            secret,
            testnet=True,
        )
    return SimulatedBroker()
