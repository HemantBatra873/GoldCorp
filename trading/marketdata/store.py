"""CSV persistence for research OHLCV datasets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading.marketdata.candles import candles_to_frame, frame_to_candles, merge_candles
from trading.types import Candle


def default_data_dir(base: Path | None = None) -> Path:
    root = base or Path.cwd()
    path = root / "data" / "ohlcv"
    path.mkdir(parents=True, exist_ok=True)
    return path


def csv_path(symbol: str, interval: str, directory: Path | None = None) -> Path:
    directory = directory or default_data_dir()
    return directory / f"{symbol.upper()}_{interval}.csv"


def save_candles(candles: list[Candle], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = candles_to_frame(candles)
    df.to_csv(path, index=False)
    return path


def load_candles(path: Path) -> list[Candle]:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return frame_to_candles(df)


def upsert_candles(path: Path, candles: list[Candle]) -> list[Candle]:
    existing: list[Candle] = []
    if path.exists():
        existing = load_candles(path)
    merged = merge_candles(existing, candles)
    save_candles(merged, path)
    return merged
