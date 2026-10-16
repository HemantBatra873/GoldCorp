"""Strategy interface — pure decision logic, no I/O."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.types import OpenPosition, Signal


@dataclass(frozen=True)
class StrategyInfo:
    strategy_id: str
    version: str
    description: str = ""


class BaseStrategy(ABC):
    """
    Strategies see an indicator-enriched frame and the current bar index.

    Contract: when called with `index=i`, implementations must only read
    rows `<= i` (no look-ahead). The backtester fills signals on a later bar.
    """

    @property
    @abstractmethod
    def info(self) -> StrategyInfo:
        raise NotImplementedError

    def default_params(self) -> dict[str, Any]:
        return {}

    def reset(self) -> None:
        """Clear any cross-bar state before a new run."""

    @abstractmethod
    def on_bar(
        self,
        df: pd.DataFrame,
        index: int,
        position: OpenPosition | None,
    ) -> Signal | None:
        raise NotImplementedError
