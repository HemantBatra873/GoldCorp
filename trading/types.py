"""Shared value objects for the trading domain (no Django)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class CloseMethod(str, Enum):
    TP = "TP"
    SL = "SL"
    END = "END"  # forced flat at end of backtest


ENGINE_VERSION = "0.2.0"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class OpenPosition:
    side: Side
    entry_price: float
    quantity: float  # notional in quote currency (USDT)
    entry_time: datetime
    entry_index: int
    sl_price: float
    tp_price: float
    factor_ajuste: float = 0.0
    alt_tp_sl: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClosedTrade:
    side: Side
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    entry_index: int
    exit_index: int
    fee: float
    profit: float
    close_method: CloseMethod
    sl_price: float
    tp_price: float
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Signal:
    """Intent emitted after a closed bar is evaluated (filled on a later bar)."""

    side: Side
    reason: str
    sl_raw: float  # swing-based stop before caps/buffers
    meta: dict[str, Any] = field(default_factory=dict)
