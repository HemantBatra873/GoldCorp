"""Stop-loss / take-profit construction (ported from Denarios Agripina rules)."""

from __future__ import annotations

from dataclasses import dataclass

from trading.types import Side


@dataclass(frozen=True)
class LevelConfig:
    tp_sl_ratio: float = 1.5
    sl_limit: float = 0.10  # max distance from entry as fraction
    buffer: float = 1.05  # Denarios used 1.05 expansion on SL/TP factors


def build_tp_sl(
    side: Side,
    entry_price: float,
    swing_stop: float,
    config: LevelConfig,
) -> tuple[float, float, float]:
    """
    Return (sl_price, tp_price, factor_ajuste).

    Swing stop is the raw structural level (e.g. 20-bar low for longs).
    Distance is capped by sl_limit, then expanded by `buffer` like Denarios.
    """
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")

    if side is Side.BUY:
        sl_raw = swing_stop
        sl_factor = (sl_raw / entry_price) - 1.0  # negative for longs
        if abs(sl_factor) > config.sl_limit:
            sl_raw = entry_price * (1.0 - config.sl_limit)
            sl_factor = (sl_raw / entry_price) - 1.0
        sl_price = entry_price * (1.0 + sl_factor * config.buffer)
        tp_price = entry_price * (1.0 + sl_factor * (-config.buffer) * config.tp_sl_ratio)
    else:
        sl_raw = swing_stop
        sl_factor = (sl_raw / entry_price) - 1.0  # positive for shorts
        if sl_factor > config.sl_limit:
            sl_raw = entry_price * (1.0 + config.sl_limit)
            sl_factor = (sl_raw / entry_price) - 1.0
        sl_price = entry_price * (1.0 + sl_factor * config.buffer)
        tp_price = entry_price * (1.0 + sl_factor * (-config.buffer) * config.tp_sl_ratio)

    factor_ajuste = (abs(1.0 - entry_price / sl_raw) + 0.001) * 1.5
    return sl_price, tp_price, factor_ajuste


def pnl_fraction(side: Side, entry: float, exit_: float) -> float:
    if side is Side.BUY:
        return exit_ / entry - 1.0
    return -((exit_ / entry) - 1.0)
