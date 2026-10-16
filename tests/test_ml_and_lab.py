"""Phase 6 — ML training/strategy and strategy lab sweeps."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.mlapp.models import MLModel, MLModelStatus
from apps.mlapp.services import create_ml_job, train_ml_model
from apps.research.lab import enqueue_param_sweep, expand_param_grid
from trading.marketdata.store import csv_path, save_candles
from trading.ml.train import train_direction_model
from trading.strategies import create_strategy
from trading.types import Candle


User = get_user_model()


def _candles(n=160):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    out = []
    for i in range(n):
        c = price * (1.003 if i % 4 else 0.997)
        out.append(
            Candle(
                start + timedelta(hours=4 * i),
                price,
                max(price, c) * 1.015,
                min(price, c) * 0.985,
                c,
                10.0,
            )
        )
        price = c
    return out


def test_expand_param_grid():
    combos = expand_param_grid({"open_rsi": [3, 5], "x": [1]})
    assert len(combos) == 2


def test_train_direction_model_and_strategy(tmp_path):
    from trading.marketdata.candles import candles_to_frame

    df = candles_to_frame(_candles(160))
    artifact = tmp_path / "model.joblib"
    result = train_direction_model(df, artifact, train_ratio=0.7)
    assert artifact.exists()
    assert "accuracy" in result.metrics
    strategy = create_strategy(
        "ml_classifier",
        model_path=str(artifact),
        threshold=0.51,
        warm_up=60,
    )
    framed = candles_to_frame(_candles(160))
    from trading.marketdata.indicators import add_strategy_indicators

    enriched = add_strategy_indicators(framed)
    # strategy builds its own features; pass OHLCV-like frame with indicators ok
    sig = strategy.on_bar(enriched, len(enriched) - 1, None)
    # May or may not signal; ensure call does not crash
    assert sig is None or sig.side.value in {"BUY", "SELL"}


@pytest.mark.django_db
def test_train_ml_model_service(settings, tmp_path):
    candles = _candles(180)
    path = csv_path("BTCUSDT", "4h", directory=settings.BASE_DIR / "data" / "ohlcv")
    save_candles(candles, path)
    model = create_ml_job(symbol="BTCUSDT", timeframe="4h", name="unit")
    trained = train_ml_model(model.pk)
    assert trained.status == MLModelStatus.READY
    assert Path(trained.artifact_path).exists()
    assert trained.metrics.get("accuracy") is not None


@pytest.mark.django_db
def test_enqueue_param_sweep_eager(settings):
    candles = _candles(100)
    path = csv_path("BTCUSDT", "4h", directory=settings.BASE_DIR / "data" / "ohlcv")
    save_candles(candles, path)
    user = User.objects.create_user("labuser", password="StrongPass123!")
    ids = enqueue_param_sweep(
        symbol="BTCUSDT",
        strategy_id="rsi_macd_stoch",
        owner=user,
        strategy_grid={"open_rsi": [4.0, 6.0]},
        execution_grid={"tp_sl_ratio": [1.5]},
        base_strategy_params={"warm_up": 40},
        base_execution={"enable_trailing": False},
        name_prefix="labtest",
    )
    assert len(ids) == 2
    assert MLModel.objects.count() >= 0  # noop sanity


@pytest.mark.django_db
def test_ml_list_page(client):
    user = User.objects.create_user("mluser", password="StrongPass123!")
    client.login(username="mluser", password="StrongPass123!")
    response = client.get(reverse("mlapp:list"))
    assert response.status_code == 200
    assert b"ML models" in response.content


@pytest.mark.django_db
def test_strategy_lab_page(client):
    user = User.objects.create_user("labpage", password="StrongPass123!")
    client.login(username="labpage", password="StrongPass123!")
    response = client.get(reverse("research:strategy_lab"))
    assert response.status_code == 200
    assert b"Strategy laboratory" in response.content
