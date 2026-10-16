"""Hand-calculated risk / exit fixtures — correctness before UI."""

from datetime import datetime, timezone

from trading.execution.simulator import ExecutionConfig, ExecutionSimulator
from trading.risk.exits import resolve_exit
from trading.risk.fees import FeeModel
from trading.risk.levels import LevelConfig, build_tp_sl, pnl_fraction
from trading.types import Candle, CloseMethod, OpenPosition, Side, Signal


def test_fee_round_trip_hand_calculated():
    fee = FeeModel(rate=0.00045)
    entry = 100.0
    exit_notional = 101.0
    assert abs(fee.round_trip(entry, exit_notional) - 0.09045) < 1e-12


def test_pnl_fraction_long_short():
    assert abs(pnl_fraction(Side.BUY, 100, 110) - 0.10) < 1e-12
    assert abs(pnl_fraction(Side.SELL, 100, 90) - 0.10) < 1e-12
    assert abs(pnl_fraction(Side.SELL, 100, 110) - (-0.10)) < 1e-12


def test_build_tp_sl_long_matches_denarios_formula():
    # entry 100, swing low 95 → sl_factor = -0.05
    # sl = 100 * (1 + -0.05 * 1.05) = 94.75
    # tp = 100 * (1 + -0.05 * -1.05 * 1.5) = 107.875
    sl, tp, factor = build_tp_sl(
        Side.BUY,
        100.0,
        95.0,
        LevelConfig(tp_sl_ratio=1.5, sl_limit=0.10, buffer=1.05),
    )
    assert abs(sl - 94.75) < 1e-9
    assert abs(tp - 107.875) < 1e-9
    assert factor > 0


def test_sl_limit_caps_long_stop():
    sl, tp, _ = build_tp_sl(
        Side.BUY,
        100.0,
        50.0,  # 50% away — must cap at 10%
        LevelConfig(tp_sl_ratio=1.5, sl_limit=0.10, buffer=1.05),
    )
    # capped raw stop at 90, then buffer: 100 * (1 + -0.10 * 1.05) = 89.5
    assert abs(sl - 89.5) < 1e-9


def test_same_candle_tp_sl_prefers_larger_excursion_long():
    pos = OpenPosition(
        side=Side.BUY,
        entry_price=100,
        quantity=100,
        entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        entry_index=0,
        sl_price=95,
        tp_price=110,
    )
    candle = Candle(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        open=100,
        high=112,
        low=90,
        close=105,
    )
    hit = resolve_exit(pos, candle)
    assert hit is not None
    # tp_extent=2, sl_extent=5 → SL
    assert hit.method is CloseMethod.SL
    assert hit.price == 95


def test_simulator_profit_matches_fee_math():
    sim = ExecutionSimulator(ExecutionConfig(fee=FeeModel(0.00045)))
    signal = Signal(side=Side.BUY, reason="test", sl_raw=95.0)
    fill = Candle(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=100,
        high=101,
        low=99,
        close=100,
    )
    pos = sim.open_from_signal(signal, fill, 1)
    trade = sim.close_position(
        pos,
        exit_price=pos.tp_price,
        exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
        exit_index=2,
        method=CloseMethod.TP,
    )
    delta = pnl_fraction(Side.BUY, pos.entry_price, trade.exit_price)
    exit_notional = pos.quantity * (1 + delta)
    expected_fee = FeeModel(0.00045).round_trip(pos.quantity, exit_notional)
    expected_profit = pos.quantity * delta - expected_fee
    assert abs(trade.fee - expected_fee) < 1e-9
    assert abs(trade.profit - expected_profit) < 1e-9
