"""ML application services — train via pure trading.ml, persist metadata."""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import Symbol
from apps.mlapp.models import MLModel, MLModelStatus
from trading.marketdata.candles import candles_to_frame
from trading.marketdata.store import csv_path, load_candles
from trading.ml.train import train_direction_model

logger = logging.getLogger("goldcorp.ml")


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


@transaction.atomic
def create_ml_job(
    *,
    symbol: str,
    timeframe: str = "4h",
    name: str = "",
    owner=None,
    train_ratio: float = 0.7,
) -> MLModel:
    symbol_obj = ensure_symbol(symbol)
    return MLModel.objects.create(
        owner=owner,
        name=name or f"rf_{symbol.upper()}_{timeframe}",
        symbol=symbol_obj,
        timeframe=timeframe,
        status=MLModelStatus.QUEUED,
        train_ratio=train_ratio,
        config={"train_ratio": train_ratio, "algorithm": "RandomForestClassifier"},
    )


def enqueue_ml_training(model: MLModel) -> MLModel:
    from apps.mlapp.tasks import train_ml_model_task

    async_result = train_ml_model_task.delay(model.pk)
    model.celery_task_id = async_result.id or ""
    model.save(update_fields=["celery_task_id", "updated_at"])
    return model


def train_ml_model(model_id: int) -> MLModel:
    model = MLModel.objects.select_related("symbol").get(pk=model_id)
    model.status = MLModelStatus.TRAINING
    model.error_message = ""
    model.save(update_fields=["status", "error_message", "updated_at"])

    path = csv_path(
        model.symbol.symbol,
        model.timeframe,
        directory=settings.BASE_DIR / "data" / "ohlcv",
    )
    if not path.exists():
        raise FileNotFoundError(
            f"No OHLCV at {path}. Run download_klines for {model.symbol.symbol}."
        )

    candles = load_candles(path)
    df = candles_to_frame(candles)
    artifact_dir = Path(settings.BASE_DIR) / "data" / "models"
    artifact_path = artifact_dir / f"ml_model_{model.pk}.joblib"

    result = train_direction_model(
        df,
        artifact_path,
        train_ratio=float(model.train_ratio),
    )

    model.status = MLModelStatus.READY
    model.artifact_path = result.model_path
    model.metrics = result.metrics
    model.feature_importance = result.feature_importance
    model.config = {
        **(model.config or {}),
        **result.as_dict(),
        "trained_at": timezone.now().isoformat(),
    }
    model.error_message = ""
    model.save()
    logger.info("ml model %s ready path=%s", model.pk, model.artifact_path)
    return model


def mark_ml_failed(model_id: int, message: str) -> MLModel:
    model = MLModel.objects.get(pk=model_id)
    model.status = MLModelStatus.FAILED
    model.error_message = message[:4000]
    model.save(update_fields=["status", "error_message", "updated_at"])
    return model
