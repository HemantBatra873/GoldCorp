"""Train a next-bar direction classifier with chronological validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

from trading.ml.features import FEATURE_COLUMNS, supervised_matrices
from trading.types import ENGINE_VERSION


@dataclass
class TrainResult:
    model_path: str
    train_rows: int
    test_rows: int
    metrics: dict[str, float]
    feature_importance: dict[str, float]
    feature_columns: tuple[str, ...] = FEATURE_COLUMNS
    model_version: str = "rf_direction_v1"
    engine_version: str = ENGINE_VERSION
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "train_rows": self.train_rows,
            "test_rows": self.test_rows,
            "metrics": self.metrics,
            "feature_importance": self.feature_importance,
            "feature_columns": list(self.feature_columns),
            "model_version": self.model_version,
            "engine_version": self.engine_version,
            "notes": self.notes,
        }


def train_direction_model(
    df: pd.DataFrame,
    output_path: Path,
    *,
    train_ratio: float = 0.7,
    n_estimators: int = 120,
    random_state: int = 42,
) -> TrainResult:
    """
    Fit RandomForest on features through time `i` to predict whether close[i+1] > close[i].

    Split is chronological (no shuffle) to avoid leakage.
    """
    if not 0.5 <= train_ratio < 1.0:
        raise ValueError("train_ratio must be in [0.5, 1)")

    x, y, _index = supervised_matrices(df)
    if len(x) < 80:
        raise ValueError(f"Need at least 80 labeled rows; got {len(x)}")

    split = int(len(x) * train_ratio)
    if split < 40 or len(x) - split < 20:
        raise ValueError("Not enough rows after chronological split")

    x_train, x_test = x.iloc[:split], x.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=6,
        min_samples_leaf=5,
        random_state=random_state,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    model.fit(x_train, y_train)

    proba = model.predict_proba(x_test)[:, 1]
    preds = (proba >= 0.5).astype(int)
    metrics = {
        "accuracy": float(accuracy_score(y_test, preds)),
        "f1": float(f1_score(y_test, preds, zero_division=0)),
    }
    try:
        metrics["roc_auc"] = float(roc_auc_score(y_test, proba))
    except ValueError:
        metrics["roc_auc"] = float("nan")

    importance = {
        col: float(imp)
        for col, imp in zip(FEATURE_COLUMNS, model.feature_importances_, strict=True)
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "feature_columns": list(FEATURE_COLUMNS),
        "model_version": "rf_direction_v1",
        "metrics": metrics,
    }
    joblib.dump(payload, output_path)

    notes = [
        "Chronological train/test split (no shuffle).",
        "Features are causal; label uses next close only during training.",
        "Treat metrics as research diagnostics, not guaranteed edge.",
    ]
    return TrainResult(
        model_path=str(output_path),
        train_rows=len(x_train),
        test_rows=len(x_test),
        metrics=metrics,
        feature_importance=importance,
        notes=notes,
    )


def load_model_bundle(path: Path) -> dict[str, Any]:
    bundle = joblib.load(path)
    if "model" not in bundle or "feature_columns" not in bundle:
        raise ValueError(f"Invalid model bundle at {path}")
    return bundle
