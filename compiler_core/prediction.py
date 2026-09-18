"""Probability prediction: real trained checkpoints or named absence.

03 card §4b (P01—P13/E01 intake, DEC18): the prediction surface produces
probabilities ONLY from a trained checkpoint registered under the models
root; without one the named ``model_not_available`` state is the honest
answer and a fixed probability is never returned. Training actually
updates parameters (pure-Python logistic regression with L2, deterministic
seeding), saves checkpoint+evaluation together, and reports metrics
against the held-out split. Leakage discipline lives with the data split
(training.py group/time modes); the checkpoint only stores parameters,
the feature order, and calibration facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from compiler_core.pricing import canonical_decimal_text

CHECKPOINT_SCHEMA_VERSION = "jc-prediction-checkpoint/1"
MODEL_NOT_AVAILABLE = "model_not_available"
INTERVAL_LEVEL = "0.95"
Z_95 = 1.959963984540054  # two-sided 95% normal quantile, fixed constant


def canonical_probability(value: float) -> str:
    """Canonical decimal text for a probability clamped into [0, 1]."""

    d = Decimal(str(value))
    if d < 0:
        d = Decimal(0)
    if d > 1:
        d = Decimal(1)
    return canonical_decimal_text(d)


@dataclass(frozen=True)
class TrainingRow:
    features: dict[str, float]
    label: int


def featurize_rows(rows: list[dict[str, Any]], feature_order: list[str]) -> list[TrainingRow]:
    parsed: list[TrainingRow] = []
    for index, row in enumerate(rows):
        features = row.get("features")
        if not isinstance(features, Mapping):
            raise ValueError(f"prediction_row_features_missing:{index}")
        try:
            vector = {name: float(features[name]) for name in feature_order}
        except KeyError as exc:
            raise ValueError(f"prediction_feature_missing:{exc.args[0]}") from exc
        label = int(row["label"])
        if label not in (0, 1):
            raise ValueError(f"prediction_label_invalid:{index}")
        parsed.append(TrainingRow(vector, label))
    return parsed


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


class LogisticModel:
    """Deterministic L2 logistic regression trained by full-batch gradient descent."""

    def __init__(self, weights: dict[str, float], bias: float,
                 feature_order: list[str], l2: float, epochs: int, learning_rate: float):
        self.weights = weights
        self.bias = bias
        self.feature_order = feature_order
        self.l2 = l2
        self.epochs = epochs
        self.learning_rate = learning_rate

    @classmethod
    def train(cls, rows: list[TrainingRow], *, epochs: int = 400, learning_rate: float = 0.35,
              l2: float = 1e-3) -> "LogisticModel":
        if not rows:
            raise ValueError("training_requires_rows")
        feature_order = sorted(rows[0].features)
        if any(sorted(row.features) != feature_order for row in rows):
            raise ValueError("training_feature_sets_differ")
        weights = {name: 0.0 for name in feature_order}
        bias = 0.0
        total = len(rows)
        for _epoch in range(epochs):
            grad_w = {name: 0.0 for name in feature_order}
            grad_b = 0.0
            for row in rows:
                z = bias + sum(weights[name] * row.features[name] for name in feature_order)
                error = _sigmoid(z) - row.label
                for name in feature_order:
                    grad_w[name] += error * row.features[name]
                grad_b += error
            for name in feature_order:
                weights[name] -= learning_rate * (grad_w[name] / total + l2 * weights[name])
            bias -= learning_rate * (grad_b / total)
        return cls(weights, bias, feature_order, l2, epochs, learning_rate)

    def probability(self, features: Mapping[str, float]) -> float:
        missing = [name for name in self.feature_order if name not in features]
        if missing:
            raise ValueError(f"prediction_feature_missing:{','.join(sorted(missing))}")
        z = self.bias + sum(self.weights[name] * float(features[name]) for name in self.feature_order)
        return _sigmoid(z)

    def positive_mass(self) -> float:
        return sum(abs(value) for value in self.weights.values())

    def key_influences(self, limit: int = 5) -> list[str]:
        ranked = sorted(self.weights, key=lambda name: (-abs(self.weights[name]), name))
        return ranked[:limit]


def _metrics(model: LogisticModel, rows: list[TrainingRow]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "brier": None, "logloss": None, "accuracy": None,
                "interval_half_width": None}
    probabilities = [model.probability(row.features) for row in rows]
    n = len(rows)
    brier = sum((p - row.label) ** 2 for p, row in zip(probabilities, rows)) / n
    logloss = -sum(
        math.log(p if row.label == 1 else max(1e-12, 1.0 - p))
        for p, row in zip(probabilities, rows)
    ) / n
    accuracy = sum(
        1 for p, row in zip(probabilities, rows) if (p >= 0.5) == (row.label == 1)
    ) / n
    mean_p = sum(probabilities) / n
    variance = sum((p - mean_p) ** 2 for p in probabilities) / max(1, n - 1)
    half_width = Z_95 * math.sqrt(max(0.0, variance) / n)
    return {
        "n": n,
        "brier": round(brier, 6),
        "logloss": round(logloss, 6),
        "accuracy": round(accuracy, 6),
        "interval_half_width": round(half_width, 6),
    }


def train_and_save(
    output_root: Path,
    *,
    event_definition: str,
    rows: list[dict[str, Any]],
    feature_order: list[str],
    split_rows: dict[str, list[dict[str, Any]]],
    model_config: Mapping[str, Any],
    data_version: str | None,
    rule_version: str | None,
) -> dict[str, Any]:
    """Train on the train split, calibrate the interval on dev, evaluate on test.

    The checkpoint stores parameters plus calibration/evaluation identity;
    the test split is never used for training or interval fitting.
    """

    train = featurize_rows(split_rows["train"], feature_order)
    dev = featurize_rows(split_rows["dev"], feature_order)
    test = featurize_rows(split_rows["test"], feature_order)
    model = LogisticModel.train(
        train,
        epochs=int(model_config.get("epochs", 400)),
        learning_rate=float(model_config.get("learningRate", 0.35)),
        l2=float(model_config.get("l2", 1e-3)),
    )
    dev_metrics = _metrics(model, dev)
    test_metrics = _metrics(model, test)
    half_width = dev_metrics.get("interval_half_width") or 0.0
    payload_digest = hashlib.sha256(
        json.dumps(
            {"weights": model.weights, "bias": model.bias,
             "featureOrder": feature_order, "eventDefinition": event_definition},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "checkpoint_id": f"pred-{payload_digest[:24]}",
        "eventDefinition": event_definition,
        "modelType": "logreg-l2",
        "modelVersion": f"logreg-l2/{payload_digest[:12]}",
        "calibrationVersion": f"dev-interval-95/{payload_digest[:12]}",
        "evaluationVersion": f"held-out-test/{payload_digest[:12]}",
        "dataVersion": data_version,
        "ruleVersion": rule_version,
        "featureOrder": feature_order,
        "parameters": {"weights": model.weights, "bias": model.bias},
        "training": {"epochs": model.epochs, "learningRate": model.learning_rate, "l2": model.l2,
                     "nTrain": len(train)},
        "intervalHalfWidth": half_width,
        "intendedScope": "conditional model on the registered feature definitions; "
                         "never a formal legal conclusion",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_root / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8",
    )
    evaluation = {
        "schema_version": "jc-prediction-eval/1",
        "checkpointId": checkpoint["checkpoint_id"],
        "dev": dev_metrics,
        "test": test_metrics,
        "leakage": {
            "testUsedForTraining": False,
            "testUsedForIntervalFit": False,
        },
    }
    (output_root / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8",
    )
    return {"checkpoint": checkpoint, "evaluation": evaluation,
            "checkpointPath": str(checkpoint_path)}


def load_checkpoint(model_root: Path, *, event_definition: str,
                    model_version: str | None = None) -> dict[str, Any]:
    """Load the registered checkpoint for one event definition, or raise."""

    root = Path(model_root)
    candidates = sorted(root.glob("**/checkpoint.json"))
    for path in candidates:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if document.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            continue
        if document.get("eventDefinition") != event_definition:
            continue
        if model_version and document.get("modelVersion") != model_version:
            continue
        return document
    raise LookupError(MODEL_NOT_AVAILABLE)


def predict_from_checkpoint(checkpoint: Mapping[str, Any],
                            features: Mapping[str, float],
                            *, observation_point: str) -> dict[str, Any]:
    """One calibrated probability from real parameters; no fixed fallbacks."""

    if checkpoint.get("modelType") != "logreg-l2":
        raise ValueError("prediction_model_type_unknown")
    parameters = checkpoint["parameters"]
    weights = {str(name): float(value) for name, value in parameters["weights"].items()}
    bias = float(parameters["bias"])
    model = LogisticModel(weights, bias, list(checkpoint["featureOrder"]), 0.0, 0, 0.0)
    probability = model.probability(dict(features))
    half_width = float(checkpoint.get("intervalHalfWidth") or 0.0)
    low = max(0.0, probability - half_width)
    high = min(1.0, probability + half_width)
    influences = model.key_influences()
    return {
        "eventId": str(checkpoint["checkpoint_id"]),
        "eventDefinition": str(checkpoint["eventDefinition"]),
        "probability": canonical_probability(probability),
        "interval": {
            "low": canonical_probability(low),
            "high": canonical_probability(high),
            "level": INTERVAL_LEVEL,
        },
        "observationPoint": observation_point,
        "applicableScope": str(checkpoint.get("intendedScope", "")),
        "keyInfluences": influences,
        "modelVersion": str(checkpoint["modelVersion"]),
        "calibrationVersion": str(checkpoint["calibrationVersion"]),
        "evaluationVersion": str(checkpoint["evaluationVersion"]),
        "dataRange": str(checkpoint.get("dataVersion") or "unregistered"),
        "guaranteeLevel": None,
    }
