from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class Signals:
    model_uncertainty: float
    historical_failure_risk: float
    novelty_score: float
    drift_score: float
    missing_information: float
    context_risk: float


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def failure_risk(signals: Signals) -> float:
    weights = {
        "model_uncertainty": 0.24,
        "historical_failure_risk": 0.22,
        "novelty_score": 0.18,
        "drift_score": 0.16,
        "missing_information": 0.10,
        "context_risk": 0.10,
    }
    return clamp(sum(weights[key] * clamp(getattr(signals, key)) for key in weights))


def selective_decision(base_prediction: float, signals: Signals, threshold: float = 0.70) -> dict:
    risk = failure_risk(signals)
    reliability = 1.0 - risk
    accepted = reliability >= threshold
    reasons: list[str] = []
    labels = (
        ("model_uncertainty", 0.60, "Model uncertainty is elevated"),
        ("historical_failure_risk", 0.50, "Similar historical cases showed high failure rates"),
        ("novelty_score", 0.65, "Current context is unusual relative to training data"),
        ("drift_score", 0.55, "Recent behavior indicates distribution drift"),
        ("missing_information", 0.40, "Important external context is unavailable"),
        ("context_risk", 0.55, "Contextual risk is elevated"),
    )
    for field, limit, reason in labels:
        if getattr(signals, field) >= limit:
            reasons.append(reason)
    return {
        "base_prediction": float(base_prediction),
        "prediction": float(base_prediction) if accepted else None,
        "failure_probability": round(risk, 4),
        "reliability": round(reliability, 4),
        "decision": "ACCEPTED" if accepted else "ABSTAINED",
        "reasons": reasons,
        "signals": signals.__dict__,
    }


def novelty_score(vector: Iterable[float], means: Iterable[float], scales: Iterable[float]) -> float:
    values = list(vector)
    standardized = [abs((value - mean) / scale) if scale else 0.0 for value, mean, scale in zip(values, means, scales)]
    if not standardized:
        return 0.0
    # A bounded percentile-like distance; this is an interpretable MVP, not a perfect OOD detector.
    return clamp(sum(standardized) / len(standardized) / 3.0)


def rolling_drift_score(recent_errors: Iterable[float], historical_errors: Iterable[float]) -> float:
    recent = list(recent_errors)
    historical = list(historical_errors)
    if not recent or not historical:
        return 0.0
    recent_mean = sum(abs(value) for value in recent) / len(recent)
    historical_mean = sum(abs(value) for value in historical) / len(historical)
    return clamp((recent_mean - historical_mean) / max(historical_mean, 1e-9))