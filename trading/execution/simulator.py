"""Execution simulator — fills, fees, and accounting (not an exchange adapter)."""

from __future__ import annotations

from dataclasses import dataclass

from trading.risk.fees import FeeModel, SlippageModel
from trading.risk.levels import LevelConfig, build_tp_sl, pnl_fraction
from trading.types import (
    Candle,
    CloseMethod,
    ClosedTrade,
    OpenPosition,
    Side,
    Signal,
)


@dataclass(frozen=True)
class ExecutionConfig:
    fee: FeeModel = FeeModel()
    slippage: SlippageModel = SlippageModel()
    levels: LevelConfig = LevelConfig()
    position_notional: float = 100.0
    enable_trailing: bool = True


class ExecutionSimulator:
    """Turn signals into positions and resolve exits with consistent accounting."""

    def __init__(self, config: ExecutionConfig | None = None):
        self.config = config or ExecutionConfig()

    def open_from_signal(
        self,
        signal: Signal,
        fill_candle: Candle,
        fill_index: int,
    ) -> OpenPosition:
        side_is_buy = signal.side is Side.BUY
        raw = fill_candle.open
        entry = self.config.slippage.apply(raw, side_is_buy=side_is_buy, is_entry=True)
        sl, tp, factor = build_tp_sl(
            signal.side,
            entry,
            signal.sl_raw,
            self.config.levels,
        )
        return OpenPosition(
            side=signal.side,
            entry_price=entry,
            quantity=self.config.position_notional,
            entry_time=fill_candle.timestamp,
            entry_index=fill_index,
            sl_price=sl,
            tp_price=tp,
            factor_ajuste=factor,
            meta={"signal_reason": signal.reason, **signal.meta},
        )

    def close_position(
        self,
        position: OpenPosition,
        *,
        exit_price: float,
        exit_time,
        exit_index: int,
        method: CloseMethod,
    ) -> ClosedTrade:
        side_is_buy = position.side is Side.BUY
        px = self.config.slippage.apply(
            exit_price,
            side_is_buy=side_is_buy,
            is_entry=False,
        )
        delta = pnl_fraction(position.side, position.entry_price, px)
        exit_notional = position.quantity * (1.0 + delta)
        fee = self.config.fee.round_trip(position.quantity, exit_notional)
        profit = position.quantity * delta - fee
        return ClosedTrade(
            side=position.side,
            entry_price=position.entry_price,
            exit_price=px,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_index=position.entry_index,
            exit_index=exit_index,
            fee=fee,
            profit=profit,
            close_method=method,
            sl_price=position.sl_price,
            tp_price=position.tp_price,
            meta=dict(position.meta),
        )
