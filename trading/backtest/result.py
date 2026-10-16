"""Reproducible backtest result payload."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from trading.backtest.metrics import PerformanceMetrics
from trading.types import ENGINE_VERSION, ClosedTrade


def stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class BacktestResult:
    strategy_id: str
    strategy_version: str
    symbol: str
    timeframe: str
    config: dict[str, Any]
    config_hash: str
    engine_version: str
    data_start: datetime | None
    data_end: datetime | None
    trades: list[ClosedTrade] = field(default_factory=list)
    metrics: PerformanceMetrics | None = None
    equity_curve: list[tuple] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "config_hash": self.config_hash,
            "engine_version": self.engine_version,
            "data_start": self.data_start,
            "data_end": self.data_end,
            "metrics": self.metrics.as_dict() if self.metrics else None,
            "trade_count": len(self.trades),
        }

    def trades_as_dicts(self) -> list[dict[str, Any]]:
        rows = []
        for t in self.trades:
            row = asdict(t)
            row["side"] = t.side.value
            row["close_method"] = t.close_method.value
            rows.append(row)
        return rows


def build_config_snapshot(
    *,
    strategy_id: str,
    strategy_version: str,
    strategy_params: dict[str, Any],
    execution: dict[str, Any],
    symbol: str,
    timeframe: str,
    data_start: datetime | None,
    data_end: datetime | None,
) -> tuple[dict[str, Any], str]:
    config = {
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "strategy_params": strategy_params,
        "execution": execution,
        "symbol": symbol,
        "timeframe": timeframe,
        "data_start": data_start.isoformat() if data_start else None,
        "data_end": data_end.isoformat() if data_end else None,
        "engine_version": ENGINE_VERSION,
        "fill_model": "signal_on_bar_close__fill_next_open",
    }
    return config, stable_hash(config)
