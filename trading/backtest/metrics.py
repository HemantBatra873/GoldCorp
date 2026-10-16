"""Performance metrics from closed trades / equity curve."""

from __future__ import annotations

from dataclasses import dataclass

from trading.types import ClosedTrade


@dataclass(frozen=True)
class PerformanceMetrics:
    total_trades: int
    total_pnl: float
    total_fees: float
    win_rate: float | None
    profit_factor: float | None
    max_drawdown: float | None
    avg_win: float | None
    avg_loss: float | None
    expectancy: float | None

    def as_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "total_fees": self.total_fees,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "expectancy": self.expectancy,
        }


def build_equity_curve(
    trades: list[ClosedTrade],
    *,
    starting_equity: float = 10_000.0,
) -> list[tuple]:
    equity = starting_equity
    curve: list[tuple] = [(None, equity)]
    for trade in trades:
        equity += trade.profit
        curve.append((trade.exit_time, equity))
    return curve


def max_drawdown(equity_curve: list[tuple]) -> float | None:
    if len(equity_curve) < 2:
        return 0.0 if equity_curve else None
    peak = equity_curve[0][1]
    max_dd = 0.0
    for _, equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)
    return max_dd


def compute_metrics(
    trades: list[ClosedTrade],
    *,
    starting_equity: float = 10_000.0,
) -> PerformanceMetrics:
    total_pnl = sum(t.profit for t in trades)
    total_fees = sum(t.fee for t in trades)
    wins = [t.profit for t in trades if t.profit > 0]
    losses = [t.profit for t in trades if t.profit < 0]
    n = len(trades)
    win_rate = (len(wins) / n) if n else None
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = None
    avg_win = (sum(wins) / len(wins)) if wins else None
    avg_loss = (sum(losses) / len(losses)) if losses else None
    expectancy = (total_pnl / n) if n else None
    curve = build_equity_curve(trades, starting_equity=starting_equity)
    return PerformanceMetrics(
        total_trades=n,
        total_pnl=total_pnl,
        total_fees=total_fees,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown(curve),
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
    )
