"""
ML direction strategy — uses a trained sklearn bundle from disk.

Does not import Django. Pass `model_path` (and optional threshold) as params.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from trading.ml.features import FEATURE_COLUMNS, build_feature_frame
from trading.ml.train import load_model_bundle
from trading.strategies.base import BaseStrategy, StrategyInfo
from trading.types import OpenPosition, Side, Signal


class MLClassifierStrategy(BaseStrategy):
    STRATEGY_ID = "ml_classifier"
    VERSION = "1.0.0"

    def __init__(
        self,
        *,
        model_path: str,
        threshold: float = 0.58,
        warm_up: int = 60,
        allow_short: bool = True,
    ):
        if not model_path:
            raise ValueError("model_path is required for ml_classifier")
        self.model_path = str(model_path)
        self.threshold = float(threshold)
        self.warm_up = int(warm_up)
        self.allow_short = bool(allow_short)
        self._bundle = None

    def _model(self):
        if self._bundle is None:
            self._bundle = load_model_bundle(Path(self.model_path))
        return self._bundle

    @property
    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self.STRATEGY_ID,
            version=self.VERSION,
            description="RandomForest next-bar direction classifier",
        )

    def default_params(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "threshold": self.threshold,
            "warm_up": self.warm_up,
            "allow_short": self.allow_short,
        }

    def reset(self) -> None:
        return None

    def on_bar(
        self,
        df: pd.DataFrame,
        index: int,
        position: OpenPosition | None,
    ) -> Signal | None:
        if position is not None or index < self.warm_up:
            return None

        bundle = self._model()
        model = bundle["model"]
        cols = bundle.get("feature_columns") or list(FEATURE_COLUMNS)

        window = build_feature_frame(df.iloc[: index + 1].copy())
        row = window.iloc[-1]
        if any(pd.isna(row.get(c)) for c in cols):
            return None

        features = row[list(cols)].to_frame().T
        proba_up = float(model.predict_proba(features)[0][1])
        proba_down = 1.0 - proba_up

        if proba_up >= self.threshold:
            side = Side.BUY
            sl_raw = float(row["min_low_20"])
            reason = f"ml_long p_up={proba_up:.3f}"
        elif self.allow_short and proba_down >= self.threshold:
            side = Side.SELL
            sl_raw = float(row["max_high_20"])
            reason = f"ml_short p_down={proba_down:.3f}"
        else:
            return None

        return Signal(
            side=side,
            reason=reason,
            sl_raw=sl_raw,
            meta={"proba_up": proba_up, "threshold": self.threshold},
        )
