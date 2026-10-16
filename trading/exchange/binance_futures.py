"""Binance USD-M Futures REST adapter (testnet or mainnet)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any
from urllib.parse import urlencode

import requests

from trading.exchange.base import OrderResult, PositionSnapshot
from trading.types import Side

logger = logging.getLogger("trading.exchange")

MAINNET = "https://fapi.binance.com"
TESTNET = "https://testnet.binancefuture.com"


class BinanceAPIError(RuntimeError):
    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


class BinanceFuturesClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = True,
        session: requests.Session | None = None,
        recv_window: int = 60_000,
    ):
        if not api_key or not api_secret:
            raise ValueError("Binance API key and secret are required for testnet/live mode")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = TESTNET if testnet else MAINNET
        self.session = session or requests.Session()
        self.recv_window = recv_window
        self._precision_cache: dict[str, tuple[int, int]] = {}

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params, doseq=True)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        signed: bool = False,
    ) -> Any:
        params = dict(params or {})
        url = f"{self.base_url}{path}"
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.recv_window
            params["signature"] = self._sign(params)
        response = self.session.request(
            method,
            url,
            params=params if method.upper() == "GET" else None,
            data=params if method.upper() != "GET" else None,
            headers=self._headers() if signed or path.startswith("/fapi") else None,
            timeout=30,
        )
        payload = response.json()
        if response.status_code >= 400 or (isinstance(payload, dict) and payload.get("code") not in (None, 200, 0) and "msg" in payload and response.status_code >= 400):
            # Binance error bodies include code/msg even on HTTP 400
            if isinstance(payload, dict) and "msg" in payload:
                raise BinanceAPIError(f"Binance error: {payload.get('msg')}", payload)
            response.raise_for_status()
        if isinstance(payload, dict) and "code" in payload and payload["code"] not in (None, 200, 0) and "orderId" not in payload:
            # Some endpoints return code only on failure
            if payload.get("msg"):
                raise BinanceAPIError(f"Binance error: {payload.get('msg')}", payload)
        return payload

    def get_mark_price(self, symbol: str) -> float:
        data = self._request("GET", "/fapi/v1/ticker/price", {"symbol": symbol.upper()})
        return float(data["price"])

    def _symbol_precision(self, symbol: str) -> tuple[int, int]:
        symbol = symbol.upper()
        if symbol in self._precision_cache:
            return self._precision_cache[symbol]
        info = self._request("GET", "/fapi/v1/exchangeInfo")
        qty_p, price_p = 3, 2
        for item in info.get("symbols", []):
            if item.get("symbol") == symbol:
                qty_p = int(item.get("quantityPrecision", 3))
                for f in item.get("filters", []):
                    if f.get("filterType") == "PRICE_FILTER":
                        tick = f.get("tickSize", "0.01")
                        if "." in tick:
                            price_p = len(tick.rstrip("0").split(".")[-1])
                        break
                break
        self._precision_cache[symbol] = (qty_p, price_p)
        return qty_p, price_p

    def set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            self._request(
                "POST",
                "/fapi/v1/leverage",
                {"symbol": symbol.upper(), "leverage": int(leverage)},
                signed=True,
            )
        except BinanceAPIError as exc:
            logger.warning("set_leverage failed for %s: %s", symbol, exc)

    def open_market(
        self,
        symbol: str,
        side: Side,
        notional_usdt: float,
        *,
        leverage: int = 5,
    ) -> OrderResult:
        symbol = symbol.upper()
        self.set_leverage(symbol, leverage)
        price = self.get_mark_price(symbol)
        qty_p, _ = self._symbol_precision(symbol)
        quantity = round(notional_usdt / price, qty_p)
        if quantity <= 0:
            raise BinanceAPIError("Calculated quantity is zero")
        data = self._request(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": side.value,
                "type": "MARKET",
                "quantity": quantity,
            },
            signed=True,
        )
        avg = float(data.get("avgPrice") or price)
        if avg == 0:
            avg = price
        filled_qty = float(data.get("executedQty") or quantity)
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            symbol=symbol,
            side=side,
            quantity=filled_qty,
            avg_price=avg,
            status=str(data.get("status", "FILLED")),
            raw=data if isinstance(data, dict) else {},
        )

    def close_market(self, symbol: str, side: Side, quantity: float) -> OrderResult:
        """Close by trading the opposite side."""
        symbol = symbol.upper()
        close_side = Side.SELL if side is Side.BUY else Side.BUY
        qty_p, _ = self._symbol_precision(symbol)
        quantity = round(quantity, qty_p)
        data = self._request(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": close_side.value,
                "type": "MARKET",
                "quantity": quantity,
                "reduceOnly": "true",
            },
            signed=True,
        )
        price = self.get_mark_price(symbol)
        avg = float(data.get("avgPrice") or price)
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            symbol=symbol,
            side=close_side,
            quantity=float(data.get("executedQty") or quantity),
            avg_price=avg,
            status=str(data.get("status", "FILLED")),
            raw=data if isinstance(data, dict) else {},
        )

    def place_protective_stop(
        self,
        symbol: str,
        position_side: Side,
        *,
        stop_price: float,
        kind: str,
    ) -> OrderResult:
        """
        Place STOP_MARKET or TAKE_PROFIT_MARKET with closePosition.
        kind: 'STOP_MARKET' | 'TAKE_PROFIT_MARKET'
        """
        symbol = symbol.upper()
        opposite = Side.SELL if position_side is Side.BUY else Side.BUY
        _, price_p = self._symbol_precision(symbol)
        stop_price = round(stop_price, price_p)
        data = self._request(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": opposite.value,
                "type": kind,
                "stopPrice": stop_price,
                "closePosition": "true",
                "workingType": "MARK_PRICE",
            },
            signed=True,
        )
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            symbol=symbol,
            side=opposite,
            quantity=0.0,
            avg_price=stop_price,
            status=str(data.get("status", "NEW")),
            raw=data if isinstance(data, dict) else {},
        )

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        data = self._request(
            "DELETE",
            "/fapi/v1/order",
            {"symbol": symbol.upper(), "orderId": order_id},
            signed=True,
        )
        return data if isinstance(data, dict) else {"raw": data}

    def get_position(self, symbol: str) -> PositionSnapshot | None:
        data = self._request(
            "GET",
            "/fapi/v2/positionRisk",
            {"symbol": symbol.upper()},
            signed=True,
        )
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            amt = float(row.get("positionAmt") or 0)
            if abs(amt) < 1e-12:
                continue
            side = Side.BUY if amt > 0 else Side.SELL
            return PositionSnapshot(
                symbol=symbol.upper(),
                side=side,
                quantity=abs(amt),
                entry_price=float(row.get("entryPrice") or 0),
                unrealized_pnl=float(row.get("unRealizedProfit") or 0),
                raw=row,
            )
        return None
