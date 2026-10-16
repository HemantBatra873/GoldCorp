"""Application services that bridge the pure trading domain and Django ORM."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.models import Symbol
from apps.research.exceptions import (
    BacktestDataError,
    InvalidRunState,
    OwnershipError,
)
from apps.research.models import BacktestRun, EquityPoint, RunStatus, Trade
from trading.backtest.engine import Backtester, execution_config_from_dict
from trading.backtest.result import BacktestResult
from trading.marketdata.store import csv_path, load_candles
from trading.strategies.registry import create_strategy

logger = logging.getLogger("goldcorp.research")


def _dec(value) -> Decimal:
    return Decimal(str(round(float(value), 8)))


def assert_can_access(run: BacktestRun, user=None, *, write: bool = False) -> None:
    """Enforce ownership at the service layer (not only in the UI)."""
    if user is None:
        return
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return
    if run.owner_id is None:
        # Legacy / CLI runs are readable by any authenticated user; writes need staff.
        if write:
            raise OwnershipError("You do not have access to modify this backtest run")
        return
    if run.owner_id != getattr(user, "id", None):
        raise OwnershipError("You do not have access to this backtest run")


def runs_for_user(user=None) -> QuerySet[BacktestRun]:
    qs = BacktestRun.objects.select_related("symbol", "owner")
    if user is None or getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return qs
    # Own experiments + unowned CLI/system runs
    return qs.filter(Q(owner=user) | Q(owner__isnull=True))


def get_run(run_id: int, user=None) -> BacktestRun:
    run = BacktestRun.objects.select_related("symbol", "owner").get(pk=run_id)
    assert_can_access(run, user)
    return run


def ensure_symbol(symbol: str) -> Symbol:
    symbol = symbol.upper()
    obj, _ = Symbol.objects.get_or_create(
        symbol=symbol,
        defaults={
            "base_asset": symbol[:-4] if symbol.endswith("USDT") else "",
            "quote_asset": "USDT" if symbol.endswith("USDT") else "",
            "is_active": True,
        },
    )
    return obj


def build_request_config(
    *,
    symbol: str,
    strategy_id: str,
    timeframe: str,
    strategy_params: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    data_start: datetime | None = None,
    data_end: datetime | None = None,
) -> dict[str, Any]:
    """Immutable request snapshot stored on the run before the worker executes."""
    return {
        "request": {
            "symbol": symbol.upper(),
            "strategy_id": strategy_id,
            "timeframe": timeframe,
            "strategy_params": strategy_params or {},
            "execution": execution
            or {
                "fee_rate": 0.00045,
                "slippage_rate": 0.0,
                "tp_sl_ratio": 1.5,
                "sl_limit": 0.10,
                "position_notional": 100.0,
                "enable_trailing": True,
            },
            "data_start": data_start.isoformat() if data_start else None,
            "data_end": data_end.isoformat() if data_end else None,
        }
    }


@transaction.atomic
def create_backtest_run(
    *,
    symbol: str,
    strategy_id: str,
    timeframe: str = "4h",
    name: str = "",
    owner=None,
    strategy_params: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    data_start: datetime | None = None,
    data_end: datetime | None = None,
) -> BacktestRun:
    """Create a QUEUED experiment row with an immutable request config."""
    strategy = create_strategy(strategy_id, **(strategy_params or {}))

    symbol_obj = ensure_symbol(symbol)
    config = build_request_config(
        symbol=symbol,
        strategy_id=strategy_id,
        timeframe=timeframe,
        strategy_params=strategy_params,
        execution=execution,
        data_start=data_start,
        data_end=data_end,
    )
    run = BacktestRun.objects.create(
        owner=owner,
        name=name or f"{strategy_id}:{symbol.upper()}",
        strategy_id=strategy_id,
        strategy_version=strategy.info.version,
        symbol=symbol_obj,
        timeframe=timeframe,
        status=RunStatus.QUEUED,
        config=config,
        data_start=data_start,
        data_end=data_end,
    )
    logger.info("created backtest run id=%s status=%s", run.pk, run.status)
    return run


def enqueue_backtest_run(run: BacktestRun, user=None) -> BacktestRun:
    """Dispatch a Celery task for a queued (or re-queued failed) run."""
    assert_can_access(run, user)
    if run.status not in {RunStatus.QUEUED, RunStatus.FAILED}:
        raise InvalidRunState(
            f"Cannot enqueue run in status={run.status}; expected queued or failed"
        )

    # Late import avoids circular import with tasks
    from apps.research.tasks import execute_backtest_run_task

    if run.status == RunStatus.FAILED:
        run.status = RunStatus.QUEUED
        run.error_message = ""
        run.finished_at = None
        run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])

    async_result = execute_backtest_run_task.delay(run.pk)
    run.celery_task_id = async_result.id or ""
    run.save(update_fields=["celery_task_id", "updated_at"])
    logger.info("enqueued backtest run id=%s task_id=%s", run.pk, run.celery_task_id)
    return run


def create_and_enqueue_backtest(**kwargs) -> BacktestRun:
    run = create_backtest_run(**kwargs)
    return enqueue_backtest_run(run, user=kwargs.get("owner"))


@transaction.atomic
def cancel_backtest_run(run: BacktestRun, user=None) -> BacktestRun:
    """
    Cancel a queued run, or mark a running run cancelled (worker cooperates).

    Also attempts Celery revoke when a task id is present.
    """
    assert_can_access(run, user, write=True)
    if run.status in {RunStatus.COMPLETED, RunStatus.CANCELLED}:
        raise InvalidRunState(f"Cannot cancel run in status={run.status}")

    if run.status == RunStatus.FAILED:
        raise InvalidRunState("Cannot cancel a failed run")

    previous = run.status
    run.status = RunStatus.CANCELLED
    run.finished_at = timezone.now()
    run.error_message = run.error_message or "Cancelled by user"
    run.save(update_fields=["status", "finished_at", "error_message", "updated_at"])

    if run.celery_task_id:
        try:
            from config.celery import app as celery_app

            celery_app.control.revoke(run.celery_task_id, terminate=previous == RunStatus.RUNNING)
        except Exception:  # noqa: BLE001
            logger.exception("failed to revoke celery task %s", run.celery_task_id)

    logger.info("cancelled backtest run id=%s (was %s)", run.pk, previous)
    return run


def mark_run_running(run_id: int) -> BacktestRun | None:
    """
    Transition queued → running if still eligible.

    Returns None when the run was cancelled or is no longer runnable.
    """
    with transaction.atomic():
        run = BacktestRun.objects.select_for_update().get(pk=run_id)
        if run.status == RunStatus.CANCELLED:
            return None
        if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            raise InvalidRunState(f"Cannot start run in status={run.status}")
        if run.status == RunStatus.QUEUED:
            run.status = RunStatus.RUNNING
            run.started_at = timezone.now()
            run.error_message = ""
            run.save(update_fields=["status", "started_at", "error_message", "updated_at"])
        return run


def mark_run_failed(run_id: int, message: str) -> BacktestRun:
    run = BacktestRun.objects.get(pk=run_id)
    if run.status == RunStatus.CANCELLED:
        return run
    run.status = RunStatus.FAILED
    run.error_message = message[:4000]
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
    return run


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ts


def execute_backtest_run(run_id: int) -> BacktestRun:
    """
    Synchronously execute a run using the pure trading engine.

    Used by the Celery worker (and tests). HTTP must not call this directly
    for long jobs — enqueue instead.
    """
    run = mark_run_running(run_id)
    if run is None:
        logger.info("skip execute; run %s cancelled", run_id)
        return BacktestRun.objects.get(pk=run_id)

    request = (run.config or {}).get("request") or {}
    symbol = (request.get("symbol") or (run.symbol.symbol if run.symbol_id else "")).upper()
    timeframe = request.get("timeframe") or run.timeframe
    strategy_id = request.get("strategy_id") or run.strategy_id
    strategy_params = request.get("strategy_params") or {}
    execution_raw = request.get("execution") or {}
    data_start = _parse_iso(request.get("data_start")) or run.data_start
    data_end = _parse_iso(request.get("data_end")) or run.data_end

    path = csv_path(symbol, timeframe, directory=settings.BASE_DIR / "data" / "ohlcv")
    if not path.exists():
        raise BacktestDataError(
            f"No OHLCV data at {path}. Run download_klines for {symbol} {timeframe}."
        )

    # Re-check cancel before heavy work
    run.refresh_from_db(fields=["status"])
    if run.status == RunStatus.CANCELLED:
        return run

    candles = load_candles(path)
    strategy = create_strategy(strategy_id, **strategy_params)
    execution = execution_config_from_dict(execution_raw)
    result = Backtester(strategy, execution).run(
        candles,
        symbol=symbol,
        timeframe=timeframe,
        start=data_start,
        end=data_end,
    )

    run.refresh_from_db(fields=["status"])
    if run.status == RunStatus.CANCELLED:
        logger.info("run %s cancelled after compute; not persisting success", run_id)
        return run

    return persist_backtest_result(result, run=run, owner=run.owner, name=run.name)


@transaction.atomic
def persist_backtest_result(
    result: BacktestResult,
    *,
    name: str = "",
    owner=None,
    run: BacktestRun | None = None,
) -> BacktestRun:
    """
    Save a completed BacktestResult.

    Creates Symbol if needed. Replaces trades/equity when updating an existing run.
    """
    symbol = ensure_symbol(result.symbol)

    metrics = result.metrics
    now = timezone.now()

    if run is None:
        run = BacktestRun(
            owner=owner,
            name=name or f"{result.strategy_id}:{result.symbol}",
            strategy_id=result.strategy_id,
            strategy_version=result.strategy_version,
            symbol=symbol,
            timeframe=result.timeframe,
        )
    else:
        run.trades.all().delete()
        run.equity_points.all().delete()

    # Preserve original request block if present
    prior_request = (run.config or {}).get("request")
    merged_config = dict(result.config)
    if prior_request:
        merged_config["request"] = prior_request

    run.status = RunStatus.COMPLETED
    run.strategy_id = result.strategy_id
    run.strategy_version = result.strategy_version
    run.symbol = symbol
    run.timeframe = result.timeframe
    run.config = merged_config
    run.config_hash = result.config_hash
    run.data_start = result.data_start
    run.data_end = result.data_end
    run.started_at = run.started_at or now
    run.finished_at = now
    run.error_message = ""
    run.total_trades = metrics.total_trades if metrics else 0
    run.total_pnl = _dec(metrics.total_pnl) if metrics else Decimal("0")
    run.max_drawdown = (
        _dec(metrics.max_drawdown) if metrics and metrics.max_drawdown is not None else None
    )
    run.profit_factor = (
        _dec(metrics.profit_factor)
        if metrics and metrics.profit_factor is not None and metrics.profit_factor != float("inf")
        else None
    )
    run.win_rate = _dec(metrics.win_rate) if metrics and metrics.win_rate is not None else None
    run.metrics = metrics.as_dict() if metrics else {}
    if metrics and metrics.profit_factor == float("inf"):
        run.metrics["profit_factor"] = None
        run.metrics["profit_factor_infinite"] = True
    if result.notes:
        run.metrics["notes"] = result.notes
    run.save()

    Trade.objects.bulk_create(
        [
            Trade(
                run=run,
                side=t.side.value,
                entry_price=_dec(t.entry_price),
                exit_price=_dec(t.exit_price),
                quantity=_dec(t.quantity),
                entry_time=t.entry_time,
                exit_time=t.exit_time,
                fee=_dec(t.fee),
                profit=_dec(t.profit),
                close_method=t.close_method.value,
                sl_price=_dec(t.sl_price),
                tp_price=_dec(t.tp_price),
                meta=t.meta,
            )
            for t in result.trades
        ]
    )

    EquityPoint.objects.bulk_create(
        [
            EquityPoint(
                run=run,
                timestamp=ts,
                equity=_dec(equity),
                sequence=i,
            )
            for i, (ts, equity) in enumerate(result.equity_curve)
        ]
    )
    return run


def compare_runs(run_ids: list[int], user=None) -> list[dict[str, Any]]:
    """Return a side-by-side metric summary for completed runs."""
    rows = []
    for run_id in run_ids:
        run = get_run(run_id, user=user)
        rows.append(
            {
                "id": run.pk,
                "name": run.name,
                "status": run.status,
                "strategy_id": run.strategy_id,
                "symbol": run.symbol.symbol if run.symbol_id else None,
                "timeframe": run.timeframe,
                "config_hash": run.config_hash,
                "total_trades": run.total_trades,
                "total_pnl": float(run.total_pnl),
                "max_drawdown": float(run.max_drawdown) if run.max_drawdown is not None else None,
                "profit_factor": float(run.profit_factor) if run.profit_factor is not None else None,
                "win_rate": float(run.win_rate) if run.win_rate is not None else None,
            }
        )
    return rows
