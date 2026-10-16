"""Paper trading application services — strategy + broker, not HTTP."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.paper.brokers import get_broker_for_session
from apps.paper.models import PaperEvent, PaperFill, PaperMode, PaperPosition, PaperSession
from trading.execution.simulator import ExecutionConfig
from trading.marketdata.binance import fetch_klines
from trading.marketdata.candles import candles_to_frame
from trading.marketdata.indicators import add_strategy_indicators
from trading.risk.exits import maybe_trail, resolve_exit
from trading.risk.fees import FeeModel
from trading.risk.levels import LevelConfig, build_tp_sl, pnl_fraction
from trading.strategies.registry import create_strategy
from trading.types import Candle, CloseMethod, OpenPosition, Side

logger = logging.getLogger("goldcorp.paper")


def _dec(value) -> Decimal:
    return Decimal(str(round(float(value), 8)))


def log_event(
    session: PaperSession | None,
    kind: str,
    message: str,
    *,
    level: str = PaperEvent.Level.INFO,
    payload: dict | None = None,
) -> PaperEvent:
    return PaperEvent.objects.create(
        session=session,
        kind=kind,
        level=level,
        message=message[:500],
        payload=payload or {},
    )


def heartbeat(session: PaperSession) -> None:
    session.last_heartbeat_at = timezone.now()
    session.last_error = ""
    session.save(update_fields=["last_heartbeat_at", "last_error", "updated_at"])
    log_event(session, PaperEvent.Kind.HEARTBEAT, "paper worker heartbeat ok")


def execution_from_session(session: PaperSession) -> ExecutionConfig:
    raw = session.execution_config or {}
    return ExecutionConfig(
        fee=FeeModel(rate=float(raw.get("fee_rate", 0.00045))),
        levels=LevelConfig(
            tp_sl_ratio=float(raw.get("tp_sl_ratio", 1.5)),
            sl_limit=float(raw.get("sl_limit", 0.10)),
            buffer=float(raw.get("buffer", 1.05)),
        ),
        position_notional=float(session.notional),
        enable_trailing=bool(raw.get("enable_trailing", True)),
    )


def _to_domain_position(pos: PaperPosition) -> OpenPosition:
    return OpenPosition(
        side=Side(pos.side),
        entry_price=float(pos.entry_price),
        quantity=float(pos.notional),
        entry_time=pos.opened_at,
        entry_index=0,
        sl_price=float(pos.sl_price),
        tp_price=float(pos.tp_price),
        factor_ajuste=float(pos.factor_ajuste),
        alt_tp_sl=int(pos.alt_tp_sl),
        meta=dict(pos.meta or {}),
    )


def get_or_create_default_session(owner=None) -> PaperSession:
    session = (
        PaperSession.objects.filter(owner=owner).order_by("-updated_at").first()
        if owner is not None
        else PaperSession.objects.order_by("-updated_at").first()
    )
    if session:
        return session
    return PaperSession.objects.create(
        owner=owner,
        name="default",
        is_active=False,
        mode=PaperMode.SIMULATED,
        symbols=["BTCUSDT"],
        strategy_id="rsi_macd_stoch",
        timeframe="4h",
        notional=Decimal("100"),
        strategy_params={"open_rsi": 5.0, "warm_up": 60},
        execution_config={
            "fee_rate": 0.00045,
            "tp_sl_ratio": 1.5,
            "sl_limit": 0.10,
            "enable_trailing": True,
        },
    )


@transaction.atomic
def activate_session(session: PaperSession, *, active: bool) -> PaperSession:
    session.is_active = active
    session.save(update_fields=["is_active", "updated_at"])
    log_event(
        session,
        PaperEvent.Kind.HEARTBEAT,
        f"session {'activated' if active else 'paused'}",
        payload={"is_active": active},
    )
    return session


def scan_entries_for_session(session: PaperSession) -> dict[str, Any]:
    """Evaluate strategy on latest closed bars and open paper positions."""
    if not session.is_active:
        return {"skipped": True, "reason": "inactive"}

    broker = get_broker_for_session(session)
    exec_cfg = execution_from_session(session)
    strategy = create_strategy(session.strategy_id, **(session.strategy_params or {}))
    opened = []

    for symbol in session.symbols or []:
        symbol = str(symbol).upper()
        if PaperPosition.objects.filter(
            session=session, symbol=symbol, status=PaperPosition.Status.OPEN
        ).exists():
            continue

        try:
            candles = fetch_klines(symbol, session.timeframe, limit=300)
            if len(candles) < 80:
                log_event(
                    session,
                    PaperEvent.Kind.REJECT,
                    f"{symbol}: not enough candles ({len(candles)})",
                    level=PaperEvent.Level.WARNING,
                )
                continue
            # Drop potentially incomplete last candle
            candles = candles[:-1]
            df = add_strategy_indicators(candles_to_frame(candles))
            strategy.reset()
            latest_signal = None
            for i in range(len(df)):
                sig = strategy.on_bar(df, i, None)
                if i == len(df) - 1:
                    latest_signal = sig

            if latest_signal is None:
                continue

            log_event(
                session,
                PaperEvent.Kind.SIGNAL,
                f"{symbol}: {latest_signal.reason}",
                payload={"side": latest_signal.side.value, "meta": latest_signal.meta},
            )

            order = broker.open_market(
                symbol,
                latest_signal.side,
                float(session.notional),
                leverage=int(session.leverage),
            )
            log_event(
                session,
                PaperEvent.Kind.ORDER,
                f"{symbol}: market {latest_signal.side.value} filled @ {order.avg_price}",
                payload={"order_id": order.order_id, "qty": order.quantity},
            )

            sl, tp, factor = build_tp_sl(
                latest_signal.side,
                order.avg_price,
                latest_signal.sl_raw,
                exec_cfg.levels,
            )
            sl_order = broker.place_protective_stop(
                symbol, latest_signal.side, stop_price=sl, kind="STOP_MARKET"
            )
            tp_order = broker.place_protective_stop(
                symbol, latest_signal.side, stop_price=tp, kind="TAKE_PROFIT_MARKET"
            )

            pos = PaperPosition.objects.create(
                session=session,
                symbol=symbol,
                side=latest_signal.side.value,
                entry_price=_dec(order.avg_price),
                quantity=_dec(order.quantity),
                notional=_dec(session.notional),
                sl_price=_dec(sl),
                tp_price=_dec(tp),
                factor_ajuste=factor,
                entry_order_id=order.order_id,
                sl_order_id=sl_order.order_id,
                tp_order_id=tp_order.order_id,
                opened_at=timezone.now(),
                meta={"signal_reason": latest_signal.reason, **latest_signal.meta},
            )
            opened.append(pos.pk)
            log_event(
                session,
                PaperEvent.Kind.FILL,
                f"{symbol}: position opened id={pos.pk}",
                payload={"position_id": pos.pk, "sl": sl, "tp": tp},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("entry scan failed for %s", symbol)
            session.last_error = str(exc)[:2000]
            session.save(update_fields=["last_error", "updated_at"])
            log_event(
                session,
                PaperEvent.Kind.ERROR,
                f"{symbol}: {exc}",
                level=PaperEvent.Level.ERROR,
                payload={"error": str(exc)},
            )

    heartbeat(session)
    return {"opened": opened}


def manage_exits_for_session(session: PaperSession) -> dict[str, Any]:
    """Check open positions for TP/SL/trailing using recent candles + broker close."""
    if not session.is_active:
        return {"skipped": True, "reason": "inactive"}

    broker = get_broker_for_session(session)
    exec_cfg = execution_from_session(session)
    closed_ids = []

    positions = list(
        PaperPosition.objects.filter(session=session, status=PaperPosition.Status.OPEN)
    )
    for pos in positions:
        try:
            candles = fetch_klines(pos.symbol, "5m", limit=5)
            if not candles:
                continue
            candle: Candle = candles[-1]
            domain = _to_domain_position(pos)

            if exec_cfg.enable_trailing:
                trailed = maybe_trail(domain, candle)
                if trailed is not None:
                    pos.sl_price = _dec(trailed.sl_price)
                    pos.tp_price = _dec(trailed.tp_price)
                    pos.alt_tp_sl = trailed.alt_tp_sl
                    pos.save(update_fields=["sl_price", "tp_price", "alt_tp_sl", "updated_at"])
                    domain = trailed
                    log_event(
                        session,
                        PaperEvent.Kind.TRAIL,
                        f"{pos.symbol}: trailed SL/TP (alt={pos.alt_tp_sl})",
                        payload={
                            "sl": float(pos.sl_price),
                            "tp": float(pos.tp_price),
                        },
                    )
                    # Best-effort replace protective orders on testnet
                    if session.mode == PaperMode.TESTNET:
                        for oid in (pos.sl_order_id, pos.tp_order_id):
                            if oid:
                                try:
                                    broker.cancel_order(pos.symbol, oid)
                                except Exception:  # noqa: BLE001
                                    logger.warning("cancel failed for %s", oid)
                        sl_o = broker.place_protective_stop(
                            pos.symbol, domain.side, stop_price=float(pos.sl_price), kind="STOP_MARKET"
                        )
                        tp_o = broker.place_protective_stop(
                            pos.symbol, domain.side, stop_price=float(pos.tp_price), kind="TAKE_PROFIT_MARKET"
                        )
                        pos.sl_order_id = sl_o.order_id
                        pos.tp_order_id = tp_o.order_id
                        pos.save(update_fields=["sl_order_id", "tp_order_id", "updated_at"])

            hit = resolve_exit(domain, candle)
            if hit is None:
                # Reconcile against broker if position already flat on exchange
                snap = broker.get_position(pos.symbol)
                if snap is None and session.mode == PaperMode.TESTNET:
                    mark = broker.get_mark_price(pos.symbol)
                    _close_local_position(
                        session, pos, exit_price=mark, method=CloseMethod.END, broker_order_id=""
                    )
                    closed_ids.append(pos.pk)
                    log_event(
                        session,
                        PaperEvent.Kind.RECONCILE,
                        f"{pos.symbol}: exchange flat — closed locally @ mark",
                    )
                continue

            order = broker.close_market(pos.symbol, Side(pos.side), float(pos.quantity))
            _close_local_position(
                session,
                pos,
                exit_price=order.avg_price or hit.price,
                method=hit.method,
                broker_order_id=order.order_id,
            )
            closed_ids.append(pos.pk)
            log_event(
                session,
                PaperEvent.Kind.FILL,
                f"{pos.symbol}: closed via {hit.method.value} @ {order.avg_price}",
                payload={"method": hit.method.value, "order_id": order.order_id},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("exit manage failed for position %s", pos.pk)
            session.last_error = str(exc)[:2000]
            session.save(update_fields=["last_error", "updated_at"])
            log_event(
                session,
                PaperEvent.Kind.ERROR,
                f"{pos.symbol}: {exc}",
                level=PaperEvent.Level.ERROR,
            )

    heartbeat(session)
    return {"closed": closed_ids}


def _close_local_position(
    session: PaperSession,
    pos: PaperPosition,
    *,
    exit_price: float,
    method: CloseMethod,
    broker_order_id: str,
) -> PaperFill:
    exec_cfg = execution_from_session(session)
    side = Side(pos.side)
    delta = pnl_fraction(side, float(pos.entry_price), float(exit_price))
    exit_notional = float(pos.notional) * (1.0 + delta)
    fee = exec_cfg.fee.round_trip(float(pos.notional), exit_notional)
    profit = float(pos.notional) * delta - fee
    now = timezone.now()
    pos.status = PaperPosition.Status.CLOSED
    pos.closed_at = now
    pos.meta = {**(pos.meta or {}), "exit_order_id": broker_order_id}
    pos.save(update_fields=["status", "closed_at", "meta", "updated_at"])
    return PaperFill.objects.create(
        session=session,
        position=pos,
        symbol=pos.symbol,
        side=pos.side,
        entry_price=pos.entry_price,
        exit_price=_dec(exit_price),
        quantity=pos.quantity,
        fee=_dec(fee),
        profit=_dec(profit),
        close_method=method.value,
        opened_at=pos.opened_at,
        closed_at=now,
        meta={"broker_order_id": broker_order_id},
    )
