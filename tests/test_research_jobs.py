"""Phase 3 — run lifecycle, ownership, Celery enqueue."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model

from apps.research.exceptions import InvalidRunState, OwnershipError
from apps.research.models import RunStatus, Trade
from apps.research.services import (
    cancel_backtest_run,
    compare_runs,
    create_and_enqueue_backtest,
    create_backtest_run,
    enqueue_backtest_run,
    execute_backtest_run,
    get_run,
)
from trading.marketdata.store import csv_path, save_candles
from trading.types import Candle


def _write_tiny_csv(settings, symbol: str = "BTCUSDT", n: int = 80):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(
            start + timedelta(hours=4 * i),
            100 + i * 0.05,
            101 + i * 0.05,
            99,
            100.1 + i * 0.05,
            1.0,
        )
        for i in range(n)
    ]
    path = csv_path(symbol, "4h", directory=settings.BASE_DIR / "data" / "ohlcv")
    save_candles(candles, path)
    return path


@pytest.mark.django_db
def test_create_and_enqueue_completes_eager(settings):
    _write_tiny_csv(settings)
    run = create_and_enqueue_backtest(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        timeframe="4h",
        name="phase3-eager",
        strategy_params={"warm_up": 40},
        execution={"fee_rate": 0.00045, "enable_trailing": False, "position_notional": 100},
    )
    run.refresh_from_db()
    assert run.status == RunStatus.COMPLETED
    assert run.config_hash
    assert "request" in run.config
    assert Trade.objects.filter(run=run).count() == run.total_trades


@pytest.mark.django_db
def test_missing_data_marks_failed(settings):
    run = create_backtest_run(
        symbol="MISSINGUSDT",
        strategy_id="rsi_macd_stoch",
        timeframe="4h",
    )
    from apps.research.tasks import execute_backtest_run_task

    payload = execute_backtest_run_task(run.pk)
    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert payload["status"] == RunStatus.FAILED
    assert "No OHLCV" in run.error_message or "No OHLCV" in payload.get("error", "")


@pytest.mark.django_db
def test_cancel_queued_run(settings):
    run = create_backtest_run(symbol="BTCUSDT", strategy_id="rsi_macd_stoch")
    cancelled = cancel_backtest_run(run)
    assert cancelled.status == RunStatus.CANCELLED
    with pytest.raises(InvalidRunState):
        enqueue_backtest_run(cancelled)


@pytest.mark.django_db
def test_ownership_enforced(settings):
    User = get_user_model()
    owner = User.objects.create_user("owner", password="x")
    other = User.objects.create_user("other", password="x")
    run = create_backtest_run(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        owner=owner,
    )
    assert get_run(run.pk, user=owner).pk == run.pk
    with pytest.raises(OwnershipError):
        get_run(run.pk, user=other)


@pytest.mark.django_db
def test_compare_runs(settings):
    _write_tiny_csv(settings)
    a = create_and_enqueue_backtest(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        strategy_params={"warm_up": 40},
        execution={"enable_trailing": False},
    )
    b = create_and_enqueue_backtest(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        strategy_params={"warm_up": 50},
        execution={"enable_trailing": False},
    )
    rows = compare_runs([a.pk, b.pk])
    assert len(rows) == 2
    assert rows[0]["id"] == a.pk


@pytest.mark.django_db
def test_execute_sync_path(settings):
    _write_tiny_csv(settings)
    run = create_backtest_run(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        strategy_params={"warm_up": 40},
        execution={"enable_trailing": False},
    )
    completed = execute_backtest_run(run.pk)
    assert completed.status == RunStatus.COMPLETED
