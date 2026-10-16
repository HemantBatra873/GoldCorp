"""Ensure indicator columns at index i do not depend on future rows."""

import numpy as np
import pandas as pd

from trading.marketdata.indicators import add_strategy_indicators


def test_indicator_at_i_stable_when_future_rows_change():
    n = 100
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    close = np.linspace(100, 120, n) + np.sin(np.arange(n) / 3)
    base = pd.DataFrame(
        {
            "timestamp": idx,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 10.0),
        }
    )
    full = add_strategy_indicators(base)

    truncated = add_strategy_indicators(base.iloc[:80].copy())
    i = 70
    for col in ("rsi", "macd_hist", "stoch_k", "stoch_d"):
        a = full.iloc[i][col]
        b = truncated.iloc[i][col]
        if pd.isna(a) and pd.isna(b):
            continue
        assert abs(float(a) - float(b)) < 1e-9, col
