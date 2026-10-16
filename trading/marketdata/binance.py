"""Binance USD-M Futures public market data (no API key required)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from trading.marketdata.candles import frame_to_candles
from trading.types import Candle

FAPI_KLINES = "https://fapi.binance.com/fapi/v1/klines"

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def _ms(ts: datetime | None) -> int | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return int(ts.timestamp() * 1000)


def fetch_klines(
    symbol: str,
    interval: str = "4h",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1500,
    session: requests.Session | None = None,
) -> list[Candle]:
    """
    Download historical klines, paginating when a range is provided.

    Uses public REST — suitable for research; not authenticated.
    """
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval {interval!r}; choose from {sorted(INTERVAL_MS)}")

    http = session or requests.Session()
    symbol = symbol.upper()
    start_ms = _ms(start)
    end_ms = _ms(end)
    rows: list[list[Any]] = []

    while True:
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1500),
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        response = http.get(FAPI_KLINES, params=params, timeout=30)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break

        rows.extend(batch)
        last_open = int(batch[-1][0])
        next_start = last_open + INTERVAL_MS[interval]
        if start_ms is None or end_ms is None:
            # Single page when no explicit range windowing needed beyond limit
            if len(batch) < params["limit"]:
                break
            # If only limit was requested, stop after one full page unless start set
            if start is None:
                break
        if end_ms is not None and next_start > end_ms:
            break
        if len(batch) < params["limit"]:
            break
        start_ms = next_start

    if not rows:
        return []

    df = pd.DataFrame(
        rows,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "num_trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    return frame_to_candles(df[["timestamp", "open", "high", "low", "close", "volume"]])
