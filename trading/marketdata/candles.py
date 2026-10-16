"""Candle series helpers — always chronological ascending (oldest → newest)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

import pandas as pd

from trading.types import Candle

OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def candles_to_frame(candles: Sequence[Candle]) -> pd.DataFrame:
    rows = [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=list(OHLCV_COLUMNS))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def frame_to_candles(df: pd.DataFrame) -> list[Candle]:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing columns: {sorted(missing)}")

    out: list[Candle] = []
    working = df.sort_values("timestamp").reset_index(drop=True)
    for row in working.itertuples(index=False):
        ts = row.timestamp
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        volume = float(getattr(row, "volume", 0.0) or 0.0)
        out.append(
            Candle(
                timestamp=ts,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=volume,
            )
        )
    return out


def ensure_aware_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def slice_frame(
    df: pd.DataFrame,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    work = df.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    if start is not None:
        work = work[work["timestamp"] >= pd.Timestamp(ensure_aware_utc(start))]
    if end is not None:
        work = work[work["timestamp"] <= pd.Timestamp(ensure_aware_utc(end))]
    return work.sort_values("timestamp").reset_index(drop=True)


def merge_candles(existing: Iterable[Candle], new: Iterable[Candle]) -> list[Candle]:
    by_ts = {ensure_aware_utc(c.timestamp): c for c in existing}
    for c in new:
        by_ts[ensure_aware_utc(c.timestamp)] = c
    return [by_ts[k] for k in sorted(by_ts)]
