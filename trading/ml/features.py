"""Causal feature engineering for ML strategies (no look-ahead in features)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading.marketdata.indicators import add_strategy_indicators

FEATURE_COLUMNS = (
    "rsi",
    "stoch_k",
    "stoch_d",
    "macd_hist",
    "ret_1",
    "ret_3",
    "hl_range",
    "close_vs_sma20",
)


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build features from OHLCV.

    Labels use the *next* close (training only). Feature columns at row i
    depend only on data through i.
    """
    out = add_strategy_indicators(df.copy())
    out["ret_1"] = out["close"].pct_change(1)
    out["ret_3"] = out["close"].pct_change(3)
    out["hl_range"] = (out["high"] - out["low"]) / out["close"].replace(0, np.nan)
    sma20 = out["close"].rolling(20, min_periods=5).mean()
    out["close_vs_sma20"] = (out["close"] / sma20) - 1.0
    # Label: next-bar up move (shifted from future — never used as a feature)
    out["label_up"] = (out["close"].shift(-1) > out["close"]).astype(float)
    return out


def supervised_matrices(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DatetimeIndex]:
    framed = build_feature_frame(df)
    usable = framed.dropna(subset=[*FEATURE_COLUMNS, "label_up"]).copy()
    # Last row has no next-close label after dropna on label_up — already dropped
    x = usable.loc[:, list(FEATURE_COLUMNS)]
    y = usable["label_up"].astype(int)
    index = pd.to_datetime(usable["timestamp"], utc=True)
    return x, y, index
