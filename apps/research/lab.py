"""Strategy laboratory — parameter sweeps as multiple queued experiments."""

from __future__ import annotations

import itertools
import logging
from typing import Any

from apps.research.services import create_and_enqueue_backtest

logger = logging.getLogger("goldcorp.research")


def expand_param_grid(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not grid:
        return [{}]
    keys = list(grid.keys())
    values = [grid[k] if grid[k] else [None] for k in keys]
    combos = []
    for combo in itertools.product(*values):
        combos.append({k: v for k, v in zip(keys, combo, strict=True) if v is not None})
    return combos


def enqueue_param_sweep(
    *,
    symbol: str,
    strategy_id: str,
    timeframe: str = "4h",
    owner=None,
    strategy_grid: dict[str, list[Any]] | None = None,
    execution_grid: dict[str, list[Any]] | None = None,
    base_strategy_params: dict[str, Any] | None = None,
    base_execution: dict[str, Any] | None = None,
    name_prefix: str = "lab",
) -> list[int]:
    """
    Create and enqueue one BacktestRun per parameter combination.

    Example strategy_grid: {"open_rsi": [3, 5, 7]}
    Example execution_grid: {"tp_sl_ratio": [1.2, 1.5, 2.0]}
    """
    strategy_combos = expand_param_grid(strategy_grid or {})
    execution_combos = expand_param_grid(execution_grid or {})
    run_ids: list[int] = []

    for s_params, e_params in itertools.product(strategy_combos, execution_combos):
        strategy_params = {**(base_strategy_params or {}), **s_params}
        execution = {
            "fee_rate": 0.00045,
            "slippage_rate": 0.0,
            "tp_sl_ratio": 1.5,
            "sl_limit": 0.10,
            "position_notional": 100.0,
            "enable_trailing": True,
            **(base_execution or {}),
            **e_params,
        }
        label = ",".join(f"{k}={v}" for k, v in {**s_params, **e_params}.items()) or "default"
        run = create_and_enqueue_backtest(
            symbol=symbol,
            strategy_id=strategy_id,
            timeframe=timeframe,
            name=f"{name_prefix}:{label}"[:120],
            owner=owner,
            strategy_params=strategy_params,
            execution=execution,
        )
        run_ids.append(run.pk)
        logger.info("lab enqueued run=%s params=%s", run.pk, label)

    return run_ids
