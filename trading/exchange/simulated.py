"""In-memory / local simulated broker for paper trading without API keys."""

from __future__ import annotations

import itertools
import logging
from typing import Any

import requests

from trading.exchange.base import OrderResult, PositionSnapshot
from trading.types import Side

logger = logging.getLogger("trading.exchange")


class SimulatedBroker:
    """
    Fills market orders at the public mark price.

    Positions are tracked in-process (and mirrored to Django by the paper service).
    """

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self._orders = itertools.count(1)
        self._positions: dict[str, PositionSnapshot] = {}

    def get_mark_price(self, symbol: str) -> float:
        response = self.session.get(
            "https://fapi.binance.com/fapi/v1/ticker/price",
            params={"symbol": symbol.upper()},
            timeout=20,
        )
        response.raise_for_status()
        return float(response.json()["price"])

    def open_market(
        self,
        symbol: str,
        side: Side,
        notional_usdt: float,
        *,
        leverage: int = 5,
    ) -> OrderResult:
        symbol = symbol.upper()
        price = self.get_mark_price(symbol)
        quantity = notional_usdt / price
        order_id = str(next(self._orders))
        self._positions[symbol] = PositionSnapshot(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=price,
        )
        logger.info("sim open %s %s qty=%s @ %s", side.value, symbol, quantity, price)
        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            avg_price=price,
            status="FILLED",
            raw={"simulated": True, "leverage": leverage},
        )

    def close_market(self, symbol: str, side: Side, quantity: float) -> OrderResult:
        symbol = symbol.upper()
        price = self.get_mark_price(symbol)
        close_side = Side.SELL if side is Side.BUY else Side.BUY
        order_id = str(next(self._orders))
        self._positions.pop(symbol, None)
        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=close_side,
            quantity=quantity,
            avg_price=price,
            status="FILLED",
            raw={"simulated": True},
        )

    def place_protective_stop(
        self,
        symbol: str,
        position_side: Side,
        *,
        stop_price: float,
        kind: str,
    ) -> OrderResult:
        opposite = Side.SELL if position_side is Side.BUY else Side.BUY
        return OrderResult(
            order_id=str(next(self._orders)),
            symbol=symbol.upper(),
            side=opposite,
            quantity=0.0,
            avg_price=stop_price,
            status="NEW",
            raw={"simulated": True, "kind": kind},
        )

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        return {"symbol": symbol.upper(), "orderId": order_id, "status": "CANCELED", "simulated": True}

    def get_position(self, symbol: str) -> PositionSnapshot | None:
        return self._positions.get(symbol.upper())

    def seed_position(self, snapshot: PositionSnapshot) -> None:
        """Restore in-memory state from DB after worker restart."""
        self._positions[snapshot.symbol.upper()] = snapshot
