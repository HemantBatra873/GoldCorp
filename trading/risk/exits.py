"""Intrabar exit resolution — including same-candle TP+SL conflicts."""

from __future__ import annotations

from dataclasses import dataclass

from trading.types import Candle, CloseMethod, OpenPosition, Side


@dataclass(frozen=True)
class ExitHit:
    method: CloseMethod
    price: float


def resolve_exit(position: OpenPosition, candle: Candle) -> ExitHit | None:
    """
    Decide if TP/SL is hit on this candle.

    Same-candle rule (from Denarios Anastasia): if both levels trade,
    choose the side with the larger excursion beyond the level
    (conservative distance heuristic, not path reconstruction).
    """
    side = position.side
    tp = position.tp_price
    sl = position.sl_price
    high = candle.high
    low = candle.low

    if side is Side.BUY:
        tp_hit = high >= tp
        sl_hit = low <= sl
        if tp_hit and not sl_hit:
            return ExitHit(CloseMethod.TP, tp)
        if sl_hit and not tp_hit:
            return ExitHit(CloseMethod.SL, sl)
        if tp_hit and sl_hit:
            tp_extent = high - tp
            sl_extent = sl - low
            if tp_extent > sl_extent:
                return ExitHit(CloseMethod.TP, tp)
            return ExitHit(CloseMethod.SL, sl)
    else:
        tp_hit = low <= tp
        sl_hit = high >= sl
        if tp_hit and not sl_hit:
            return ExitHit(CloseMethod.TP, tp)
        if sl_hit and not tp_hit:
            return ExitHit(CloseMethod.SL, sl)
        if tp_hit and sl_hit:
            tp_extent = tp - low
            sl_extent = high - sl
            if tp_extent > sl_extent:
                return ExitHit(CloseMethod.TP, tp)
            return ExitHit(CloseMethod.SL, sl)
    return None


def maybe_trail(position: OpenPosition, candle: Candle) -> OpenPosition | None:
    """
    Optional trailing adjustment (simplified Anastasia tiers).

    Returns a new position if SL/TP should move; otherwise None.
    """
    factor = position.factor_ajuste
    if factor <= 0:
        return None

    if position.side is Side.BUY:
        move = (candle.close - position.entry_price) / position.entry_price
    else:
        move = -((candle.close - position.entry_price) / position.entry_price)

    alt = position.alt_tp_sl
    threshold = factor if alt == 0 else factor + (alt + 1) * (factor / 2.0)
    if move <= threshold:
        return None

    step = position.entry_price * (factor / 2.0)
    if position.side is Side.BUY:
        if alt == 0:
            new_sl = position.sl_price + step * 3.0
            new_tp = position.tp_price + step
        else:
            new_sl = position.sl_price + step
            new_tp = position.tp_price + step
    else:
        if alt == 0:
            new_sl = position.sl_price - step * 3.0
            new_tp = position.tp_price - step
        else:
            new_sl = position.sl_price - step
            new_tp = position.tp_price - step

    return OpenPosition(
        side=position.side,
        entry_price=position.entry_price,
        quantity=position.quantity,
        entry_time=position.entry_time,
        entry_index=position.entry_index,
        sl_price=new_sl,
        tp_price=new_tp,
        factor_ajuste=position.factor_ajuste,
        alt_tp_sl=alt + 1,
        meta=dict(position.meta),
    )
