"""Technical indicators used by strategies (causal — no future bars)."""

from __future__ import annotations

import pandas as pd
import ta


def add_strategy_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add StochRSI, MACD histogram, RSI, and swing high/low columns.

    Indicator values at row i use only data up to and including i
    (standard rolling / ewm behavior from `ta`).
    """
    out = df.copy()
    if out.empty:
        return out

    stoch = ta.momentum.StochRSIIndicator(out["close"])
    out["stoch_k"] = stoch.stochrsi_k()
    out["stoch_d"] = stoch.stochrsi_d()

    macd = ta.trend.MACD(out["close"], window_fast=6, window_slow=12, window_sign=4)
    out["macd_hist"] = macd.macd_diff()

    # Denarios Agripina used RSI(56); keep that default for strategy parity.
    out["rsi"] = ta.momentum.RSIIndicator(out["close"], window=56).rsi()

    out["max_high_20"] = out["high"].rolling(window=20, min_periods=1).max()
    out["min_low_20"] = out["low"].rolling(window=20, min_periods=1).min()
    return out
