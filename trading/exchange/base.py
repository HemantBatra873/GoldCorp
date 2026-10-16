"""Exchange / broker contracts — independent of Django and of strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from trading.types import Side


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    symbol: str
    side: Side
    quantity: float
    avg_price: float
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    side: Side | None
    quantity: float
    entry_price: float
    unrealized_pnl: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


class BrokerClient(Protocol):
    """Minimal broker surface used by paper trading."""

    def get_mark_price(self, symbol: str) -> float: ...

    def open_market(
        self,
        symbol: str,
        side: Side,
        notional_usdt: float,
        *,
        leverage: int = 5,
    ) -> OrderResult: ...

    def close_market(self, symbol: str, side: Side, quantity: float) -> OrderResult: ...

    def place_protective_stop(
        self,
        symbol: str,
        position_side: Side,
        *,
        stop_price: float,
        kind: str,
    ) -> OrderResult: ...

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]: ...

    def get_position(self, symbol: str) -> PositionSnapshot | None: ...
