"""Phase 5 — paper trading brokers, lifecycle, UI."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.paper.models import PaperEvent, PaperMode, PaperPosition, PaperSession
from apps.paper.services import (
    activate_session,
    manage_exits_for_session,
    scan_entries_for_session,
)
from trading.exchange.base import OrderResult, PositionSnapshot
from trading.exchange.simulated import SimulatedBroker
from trading.types import Candle, Side


User = get_user_model()


class FakeBroker:
    def __init__(self):
        self.positions = {}
        self.orders = 0

    def get_mark_price(self, symbol: str) -> float:
        return 100.0

    def open_market(self, symbol, side, notional_usdt, *, leverage=5):
        self.orders += 1
        qty = notional_usdt / 100.0
        self.positions[symbol] = PositionSnapshot(symbol, side, qty, 100.0)
        return OrderResult(str(self.orders), symbol, side, qty, 100.0, "FILLED")

    def close_market(self, symbol, side, quantity):
        self.orders += 1
        self.positions.pop(symbol, None)
        return OrderResult(str(self.orders), symbol, Side.SELL, quantity, 105.0, "FILLED")

    def place_protective_stop(self, symbol, position_side, *, stop_price, kind):
        self.orders += 1
        return OrderResult(str(self.orders), symbol, Side.SELL, 0.0, stop_price, "NEW")

    def cancel_order(self, symbol, order_id):
        return {"status": "CANCELED"}

    def get_position(self, symbol):
        return self.positions.get(symbol)


def _candles(n=100):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    price = 100.0
    for i in range(n):
        c = price * (1.002 if i % 3 else 0.998)
        out.append(
            Candle(
                start + timedelta(hours=4 * i),
                price,
                max(price, c) * 1.01,
                min(price, c) * 0.99,
                c,
                1.0,
            )
        )
        price = c
    return out


@pytest.mark.django_db
def test_scan_entries_opens_position_with_fake_broker():
    session = PaperSession.objects.create(
        name="t",
        is_active=True,
        mode=PaperMode.SIMULATED,
        symbols=["BTCUSDT"],
        strategy_id="rsi_macd_stoch",
        timeframe="4h",
        notional=Decimal("100"),
        strategy_params={"warm_up": 40, "open_rsi": 0.0},
        execution_config={"enable_trailing": False},
    )
    broker = FakeBroker()

    # Force a signal by patching strategy walk result
    from trading.types import Signal

    fake_signal = Signal(side=Side.BUY, reason="forced", sl_raw=95.0)

    with (
        patch("apps.paper.services.get_broker_for_session", return_value=broker),
        patch("apps.paper.services.fetch_klines", return_value=_candles(120)),
        patch("apps.paper.services.create_strategy") as mock_strat,
    ):
        strategy = MagicMock()
        strategy.reset = MagicMock()
        strategy.on_bar = MagicMock(side_effect=lambda df, i, pos: fake_signal if i == len(df) - 1 else None)
        mock_strat.return_value = strategy
        result = scan_entries_for_session(session)

    assert result["opened"]
    assert PaperPosition.objects.filter(session=session, status=PaperPosition.Status.OPEN).count() == 1
    assert PaperEvent.objects.filter(session=session, kind=PaperEvent.Kind.SIGNAL).exists()


@pytest.mark.django_db
def test_manage_exits_closes_on_tp():
    session = PaperSession.objects.create(
        name="t",
        is_active=True,
        mode=PaperMode.SIMULATED,
        symbols=["BTCUSDT"],
        notional=Decimal("100"),
        execution_config={"enable_trailing": False, "fee_rate": 0.0},
    )
    pos = PaperPosition.objects.create(
        session=session,
        symbol="BTCUSDT",
        side="BUY",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        notional=Decimal("100"),
        sl_price=Decimal("90"),
        tp_price=Decimal("105"),
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    broker = FakeBroker()
    broker.positions["BTCUSDT"] = PositionSnapshot("BTCUSDT", Side.BUY, 1.0, 100.0)
    tp_candle = [
        Candle(
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            104,
            110,
            103,
            108,
            1.0,
        )
    ]
    with (
        patch("apps.paper.services.get_broker_for_session", return_value=broker),
        patch("apps.paper.services.fetch_klines", return_value=tp_candle),
    ):
        result = manage_exits_for_session(session)

    assert pos.pk in result["closed"]
    pos.refresh_from_db()
    assert pos.status == PaperPosition.Status.CLOSED
    assert session.fills.count() == 1


@pytest.mark.django_db
def test_paper_dashboard_requires_login(client):
    response = client.get(reverse("paper:dashboard"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_paper_dashboard_ok(client):
    user = User.objects.create_user("paperuser", password="StrongPass123!")
    client.login(username="paperuser", password="StrongPass123!")
    response = client.get(reverse("paper:dashboard"))
    assert response.status_code == 200
    assert b"Paper trading" in response.content


@pytest.mark.django_db
def test_activate_session_logs_event():
    session = PaperSession.objects.create(name="x", is_active=False, symbols=["BTCUSDT"])
    activate_session(session, active=True)
    session.refresh_from_db()
    assert session.is_active is True
    assert PaperEvent.objects.filter(session=session).exists()


def test_simulated_broker_tracks_position():
    broker = SimulatedBroker()
    with patch.object(broker, "get_mark_price", return_value=50.0):
        order = broker.open_market("ETHUSDT", Side.BUY, 100.0)
        snap = broker.get_position("ETHUSDT")
    assert order.avg_price == 50.0
    assert snap is not None
    assert snap.quantity == 2.0
