"""
Backtesting engine.

Fill model (documented & hashed into every result):
  1. Indicators / signals evaluated on closed bar i (rows <= i only).
  2. Market entries fill at open of bar i+1 (no same-bar lookahead fill).
  3. Open positions are checked for TP/SL on each subsequent bar using high/low.
  4. Fees + optional slippage applied by ExecutionSimulator.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

import pandas as pd

from trading.backtest.metrics import build_equity_curve, compute_metrics
from trading.backtest.result import BacktestResult, build_config_snapshot
from trading.execution.simulator import ExecutionConfig, ExecutionSimulator
from trading.marketdata.candles import candles_to_frame, slice_frame
from trading.marketdata.indicators import add_strategy_indicators
from trading.marketdata.quality import validate_ohlcv
from trading.risk.exits import maybe_trail, resolve_exit
from trading.strategies.base import BaseStrategy
from trading.types import ENGINE_VERSION, Candle, CloseMethod, OpenPosition, Signal


class Backtester:
    def __init__(
        self,
        strategy: BaseStrategy,
        execution: ExecutionConfig | None = None,
        *,
        starting_equity: float = 10_000.0,
        expected_freq: str | None = None,
        flat_at_end: bool = True,
    ):
        self.strategy = strategy
        self.execution_config = execution or ExecutionConfig()
        self.simulator = ExecutionSimulator(self.execution_config)
        self.starting_equity = starting_equity
        self.expected_freq = expected_freq
        self.flat_at_end = flat_at_end

    def run(
        self,
        candles: list[Candle],
        *,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> BacktestResult:
        df = candles_to_frame(candles)
        df = slice_frame(df, start=start, end=end)
        report = validate_ohlcv(df, expected_freq=self.expected_freq)
        report.raise_if_invalid()
        if report.unordered:
            df = df.sort_values("timestamp").reset_index(drop=True)

        df = add_strategy_indicators(df)
        self.strategy.reset()

        info = self.strategy.info
        exec_snapshot = {
            "fee_rate": self.execution_config.fee.rate,
            "slippage_rate": self.execution_config.slippage.rate,
            "tp_sl_ratio": self.execution_config.levels.tp_sl_ratio,
            "sl_limit": self.execution_config.levels.sl_limit,
            "buffer": self.execution_config.levels.buffer,
            "position_notional": self.execution_config.position_notional,
            "enable_trailing": self.execution_config.enable_trailing,
            "starting_equity": self.starting_equity,
            "flat_at_end": self.flat_at_end,
        }
        data_start = df["timestamp"].iloc[0].to_pydatetime() if len(df) else None
        data_end = df["timestamp"].iloc[-1].to_pydatetime() if len(df) else None
        config, config_hash = build_config_snapshot(
            strategy_id=info.strategy_id,
            strategy_version=info.version,
            strategy_params=self.strategy.default_params(),
            execution=exec_snapshot,
            symbol=symbol,
            timeframe=timeframe,
            data_start=data_start,
            data_end=data_end,
        )

        trades = []
        position: OpenPosition | None = None
        pending: Signal | None = None
        notes: list[str] = []

        for i in range(len(df)):
            candle = _row_candle(df, i)

            # 1) Resolve exits on current bar for any open position
            if position is not None:
                hit = resolve_exit(position, candle)
                if hit is not None:
                    trades.append(
                        self.simulator.close_position(
                            position,
                            exit_price=hit.price,
                            exit_time=candle.timestamp,
                            exit_index=i,
                            method=hit.method,
                        )
                    )
                    position = None
                elif self.execution_config.enable_trailing:
                    trailed = maybe_trail(position, candle)
                    if trailed is not None:
                        position = trailed

            # 2) Fill pending entry at this bar's open (signal was on previous close)
            if position is None and pending is not None:
                position = self.simulator.open_from_signal(pending, candle, i)
                pending = None

            # 3) Evaluate strategy on this closed bar → maybe queue next-bar entry
            if position is None and pending is None:
                signal = self.strategy.on_bar(df, i, position)
                if signal is not None:
                    if i + 1 >= len(df):
                        notes.append("signal on final bar skipped (no next open to fill)")
                    else:
                        pending = signal

        if position is not None and self.flat_at_end and len(df):
            last_i = len(df) - 1
            last = _row_candle(df, last_i)
            trades.append(
                self.simulator.close_position(
                    position,
                    exit_price=last.close,
                    exit_time=last.timestamp,
                    exit_index=last_i,
                    method=CloseMethod.END,
                )
            )
            notes.append("flattened open position at end of series")

        metrics = compute_metrics(trades, starting_equity=self.starting_equity)
        equity = build_equity_curve(trades, starting_equity=self.starting_equity)

        return BacktestResult(
            strategy_id=info.strategy_id,
            strategy_version=info.version,
            symbol=symbol.upper(),
            timeframe=timeframe,
            config=config,
            config_hash=config_hash,
            engine_version=ENGINE_VERSION,
            data_start=data_start,
            data_end=data_end,
            trades=trades,
            metrics=metrics,
            equity_curve=equity,
            notes=notes,
        )


def _row_candle(df: pd.DataFrame, index: int) -> Candle:
    row = df.iloc[index]
    ts = row["timestamp"]
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    return Candle(
        timestamp=ts,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]) if "volume" in df.columns else 0.0,
    )


def execution_config_from_dict(raw: dict[str, Any] | None) -> ExecutionConfig:
    from trading.risk.fees import FeeModel, SlippageModel
    from trading.risk.levels import LevelConfig

    raw = raw or {}
    return ExecutionConfig(
        fee=FeeModel(rate=float(raw.get("fee_rate", 0.00045))),
        slippage=SlippageModel(rate=float(raw.get("slippage_rate", 0.0))),
        levels=LevelConfig(
            tp_sl_ratio=float(raw.get("tp_sl_ratio", 1.5)),
            sl_limit=float(raw.get("sl_limit", 0.10)),
            buffer=float(raw.get("buffer", 1.05)),
        ),
        position_notional=float(raw.get("position_notional", 100.0)),
        enable_trailing=bool(raw.get("enable_trailing", True)),
    )


def config_dict_for_hash(cfg: ExecutionConfig) -> dict[str, Any]:
    return {
        "fee": asdict(cfg.fee),
        "slippage": asdict(cfg.slippage),
        "levels": asdict(cfg.levels),
        "position_notional": cfg.position_notional,
        "enable_trailing": cfg.enable_trailing,
    }
