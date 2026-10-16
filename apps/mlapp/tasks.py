from __future__ import annotations

import logging

from celery import shared_task

from apps.mlapp.models import MLModelStatus
from apps.mlapp.services import mark_ml_failed, train_ml_model

logger = logging.getLogger("goldcorp.ml")


@shared_task(bind=True, name="apps.mlapp.tasks.train_ml_model_task", max_retries=1)
def train_ml_model_task(self, model_id: int) -> dict:
    try:
        model = train_ml_model(model_id)
        return {
            "model_id": model.pk,
            "status": model.status,
            "metrics": model.metrics,
            "artifact_path": model.artifact_path,
        }
    except Exception as exc:
        logger.exception("ml train failed model_id=%s", model_id)
        if self.request.retries >= self.max_retries:
            mark_ml_failed(model_id, f"{type(exc).__name__}: {exc}")
            return {"model_id": model_id, "status": MLModelStatus.FAILED, "error": str(exc)}
        raise self.retry(exc=exc)
