from django.conf import settings
from django.db import models

from apps.core.models import Symbol, TimeStampedModel


class MLModelStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    TRAINING = "training", "Training"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class MLModel(TimeStampedModel):
    """Trained sklearn bundle metadata (artifact stored on disk)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ml_models",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name="ml_models")
    timeframe = models.CharField(max_length=16, default="4h")
    status = models.CharField(
        max_length=16,
        choices=MLModelStatus.choices,
        default=MLModelStatus.QUEUED,
        db_index=True,
    )
    artifact_path = models.CharField(max_length=500, blank=True, default="")
    train_ratio = models.FloatField(default=0.7)
    metrics = models.JSONField(default=dict, blank=True)
    feature_importance = models.JSONField(default=dict, blank=True)
    config = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"MLModel#{self.pk} {self.name} [{self.status}]"
