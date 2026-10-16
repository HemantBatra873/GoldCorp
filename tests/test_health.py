from datetime import datetime, timedelta, timezone

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_endpoint(client):
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] is True
    assert payload["service"] == "goldcorp"


@pytest.mark.django_db
def test_symbol_and_backtest_run_create():
    from apps.core.models import Symbol
    from apps.research.models import BacktestRun, RunStatus

    symbol = Symbol.objects.create(symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT")
    run = BacktestRun.objects.create(
        name="phase1-smoke",
        strategy_id="placeholder",
        symbol=symbol,
        status=RunStatus.QUEUED,
        config={"fee_rate": 0.0004},
    )
    assert run.pk is not None
    assert run.status == RunStatus.QUEUED
    assert str(run).startswith("Run#")


def test_trading_package_is_django_free():
    """Trading domain must not depend on Django at import time."""
    import trading
    from trading.strategies import create_strategy

    assert trading.__version__ == "0.2.0"
    strategy = create_strategy("rsi_macd_stoch")
    assert strategy.info.strategy_id == "rsi_macd_stoch"


@pytest.mark.django_db
def test_persist_backtest_result_smoke():
    from apps.research.models import Trade
    from apps.research.services import persist_backtest_result
    from trading.backtest.engine import Backtester
    from trading.execution.simulator import ExecutionConfig
    from trading.risk.fees import FeeModel
    from trading.strategies.base import BaseStrategy, StrategyInfo
    from trading.types import Candle, Side, Signal

    class Once(BaseStrategy):
        def __init__(self):
            self.fired = False

        @property
        def info(self):
            return StrategyInfo("once", "0.0.1")

        def reset(self):
            self.fired = False

        def on_bar(self, df, index, position):
            if self.fired or index != 5:
                return None
            self.fired = True
            return Signal(Side.BUY, "x", float(df.iloc[index]["low"]) * 0.99)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(
            start + timedelta(hours=4 * i),
            100 + i * 0.1,
            101 + i * 0.1,
            99,
            100.05 + i * 0.1,
            1,
        )
        for i in range(20)
    ]
    result = Backtester(
        Once(),
        ExecutionConfig(fee=FeeModel(0.0), enable_trailing=False),
    ).run(candles, symbol="BTCUSDT", timeframe="4h")
    run = persist_backtest_result(result, name="phase2-smoke")
    assert run.pk
    assert run.total_trades == result.metrics.total_trades
    assert Trade.objects.filter(run=run).count() == len(result.trades)
