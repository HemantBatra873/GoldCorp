"""Historical data quality checks — fail fast before a backtest runs."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DataQualityReport:
    ok: bool
    rows: int
    duplicate_timestamps: int
    unordered: bool
    invalid_ohlc: int
    gap_count: int
    messages: tuple[str, ...]

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ValueError("; ".join(self.messages) or "invalid market data")


def validate_ohlcv(
    df: pd.DataFrame,
    *,
    expected_freq: str | None = None,
    max_gap_multiple: float = 1.5,
) -> DataQualityReport:
    messages: list[str] = []
    if df.empty:
        return DataQualityReport(
            ok=False,
            rows=0,
            duplicate_timestamps=0,
            unordered=False,
            invalid_ohlc=0,
            gap_count=0,
            messages=("empty dataset",),
        )

    work = df.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    rows = len(work)
    dupes = int(work["timestamp"].duplicated().sum())
    if dupes:
        messages.append(f"{dupes} duplicate timestamp(s)")

    unordered = not work["timestamp"].is_monotonic_increasing
    if unordered and dupes == 0:
        # Still allow if sorting would fix it; flag for awareness.
        messages.append("timestamps are not sorted ascending")

    invalid = (
        (work["high"] < work["low"])
        | (work["high"] < work["open"])
        | (work["high"] < work["close"])
        | (work["low"] > work["open"])
        | (work["low"] > work["close"])
        | work[["open", "high", "low", "close"]].isna().any(axis=1)
    )
    invalid_ohlc = int(invalid.sum())
    if invalid_ohlc:
        messages.append(f"{invalid_ohlc} candle(s) with invalid OHLC relationships")

    gap_count = 0
    if expected_freq and rows >= 2:
        ordered = work.sort_values("timestamp")
        deltas = ordered["timestamp"].diff().dropna()
        expected = pd.Timedelta(expected_freq)
        gaps = deltas[deltas > expected * max_gap_multiple]
        gap_count = int(len(gaps))
        if gap_count:
            messages.append(
                f"{gap_count} gap(s) larger than {max_gap_multiple}x {expected_freq}"
            )

    # Duplicates and invalid OHLC are hard failures; unsorted alone is OK if we sort.
    hard_fail = dupes > 0 or invalid_ohlc > 0 or rows == 0
    return DataQualityReport(
        ok=not hard_fail,
        rows=rows,
        duplicate_timestamps=dupes,
        unordered=unordered,
        invalid_ohlc=invalid_ohlc,
        gap_count=gap_count,
        messages=tuple(messages),
    )
