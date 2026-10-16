"""Strategy registry for CLI / services."""

from __future__ import annotations

from typing import Any, Callable

from trading.strategies.base import BaseStrategy
from trading.strategies.ml_classifier import MLClassifierStrategy
from trading.strategies.rsi_macd_stoch import RsiMacdStochStrategy

StrategyFactory = Callable[..., BaseStrategy]

_REGISTRY: dict[str, StrategyFactory] = {
    RsiMacdStochStrategy.STRATEGY_ID: RsiMacdStochStrategy,
    MLClassifierStrategy.STRATEGY_ID: MLClassifierStrategy,
}


def register(strategy_id: str, factory: StrategyFactory) -> None:
    _REGISTRY[strategy_id] = factory


def available_strategies() -> list[str]:
    return sorted(_REGISTRY)


def create_strategy(strategy_id: str, **params: Any) -> BaseStrategy:
    try:
        factory = _REGISTRY[strategy_id]
    except KeyError as exc:
        known = ", ".join(available_strategies()) or "(none)"
        raise KeyError(f"unknown strategy {strategy_id!r}; known: {known}") from exc
    return factory(**params)
