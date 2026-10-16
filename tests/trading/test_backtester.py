"""Backtester contracts: fill timing, reproducibility, no look-ahead fills."""

from datetime import datetime, timedelta, timezone

import pandas as pd

from trading.backtest.engine import Backtester
from trading.execution.simulator import ExecutionConfig
from trading.risk.fees import FeeModel
from trading.strategies.base import BaseStrategy, StrategyInfo
from trading.types import Candle, OpenPosition, Side, Signal


def _candles(n: int = 80, start_price: float = 100.0) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    price = start_price
    for i in range(n):
        o = price
        c = price * (1.001 if i % 2 == 0 else 0.999)
        h = max(o, c) * 1.01
        low = min(o, c) * 0.99
        out.append(
            Candle(
                timestamp=start + timedelta(hours=4 * i),
                open=o,
                high=h,
                low=low,
                close=c,
                volume=1000,
            )
        )
        price = c
    return out


class _ForceBuyOnce(BaseStrategy):
    """Emits a single BUY at a chosen index using only that bar's low as stop."""

    def __init__(self, signal_index: int = 10):
        self.signal_index = signal_index
        self._fired = False

    @property
    def info(self) -> StrategyInfo:
        return StrategyInfo(strategy_id="force_buy_once", version="0.0.1")

    def reset(self) -> None:
        self._fired = False

    def on_bar(self, df: pd.DataFrame, index: int, position: OpenPosition | None):
        if self._fired or position is not None or index != self.signal_index:
            return None
        self._fired = True
        row = df.iloc[index]
        return Signal(
            side=Side.BUY,
            reason="forced",
            sl_raw=float(row["low"]) * 0.99,
            meta={"signal_index": index},
        )


def test_signal_fills_at_next_open_not_signal_close():
    candles = _candles(40)
    signal_i = 10
    bt = Backtester(
        _ForceBuyOnce(signal_i),
        ExecutionConfig(fee=FeeModel(0.0), enable_trailing=False),
        flat_at_end=True,
    )
    result = bt.run(candles, symbol="TESTUSDT", timeframe="4h")
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_index == signal_i + 1
    assert abs(trade.entry_price - candles[signal_i + 1].open) < 1e-9


def test_config_hash_stable_for_same_inputs():
    candles = _candles(50)
    bt = Backtester(_ForceBuyOnce(12), ExecutionConfig(enable_trailing=False))
    a = bt.run(candles, symbol="BTCUSDT", timeframe="4h")
    b = bt.run(candles, symbol="BTCUSDT", timeframe="4h")
    assert a.config_hash == b.config_hash
    assert a.engine_version == b.engine_version


def test_duplicate_timestamps_rejected():
    candles = _candles(10)
    bad = list(candles) + [candles[3]]
    bt = Backtester(_ForceBuyOnce(5), ExecutionConfig(enable_trailing=False))
    try:
        bt.run(bad, symbol="BTCUSDT", timeframe="4h")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "duplicate" in str(exc).lower()


def test_rsi_macd_strategy_runs_on_synthetic_series():
    from trading.strategies.rsi_macd_stoch import RsiMacdStochStrategy

    candles = _candles(120)
    result = Backtester(
        RsiMacdStochStrategy(warm_up=60),
        ExecutionConfig(enable_trailing=False),
    ).run(candles, symbol="BTCUSDT", timeframe="4h")
    assert result.metrics is not None
    assert result.config["fill_model"] == "signal_on_bar_close__fill_next_open"
    assert result.strategy_id == "rsi_macd_stoch"
