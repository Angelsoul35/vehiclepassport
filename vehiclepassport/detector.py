"""Score a vehicle's history for tampering risk.

The detector combines two signals. A RandomForest, trained on labelled honest and
tampered histories, produces a risk score from the engineered features — it picks
up soft, combined patterns (irregular servicing, odd mileage variance). On top of
that sit deterministic red flags (a rollback, an implausible jump): if the history
contains one, the vehicle is suspicious regardless of the model score, because a
dropped odometer is not a matter of probability. The report carries both, so a
decision is always explainable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from .chain.registry import EventRecord
from .features import FEATURE_NAMES, extract_features, feature_vector, red_flags
from .generate import make_dataset

# Flags that, on their own, mark a vehicle suspicious no matter the model score.
HARD_FLAG_PREFIXES = ("odometer rollback", "implausible mileage jump")


@dataclass
class VehicleRiskReport:
    risk_score: float
    is_suspicious: bool
    red_flags: list[str]
    features: dict[str, float]
    model_factors: list[tuple[str, float]] = field(default_factory=list)


class TamperDetector:
    def __init__(self, max_km_per_day: float = 1500.0, risk_threshold: float = 0.5) -> None:
        self.max_km_per_day = max_km_per_day
        self.risk_threshold = risk_threshold
        self._model = RandomForestClassifier(
            n_estimators=200, max_depth=8, random_state=0, class_weight="balanced"
        )
        self._fitted = False

    def fit(
        self,
        histories: list[list[EventRecord]] | None = None,
        labels: list[int] | None = None,
    ) -> TamperDetector:
        if histories is None:
            histories, labels = make_dataset()
        x = np.array([feature_vector(h) for h in histories])
        self._model.fit(x, labels)
        self._fitted = True
        return self

    @property
    def feature_importances(self) -> list[tuple[str, float]]:
        importances = self._model.feature_importances_
        pairs = sorted(
            zip(FEATURE_NAMES, importances, strict=True), key=lambda p: p[1], reverse=True
        )
        return [(name, round(float(w), 4)) for name, w in pairs]

    def assess(self, history: list[EventRecord]) -> VehicleRiskReport:
        if not self._fitted:
            raise RuntimeError("Detector is not fitted. Call fit() first.")
        feats = extract_features(history)
        x = np.array([feature_vector(history)])
        risk = float(self._model.predict_proba(x)[0][1])

        flags = red_flags(history, self.max_km_per_day)
        has_hard_flag = any(f.startswith(HARD_FLAG_PREFIXES) for f in flags)
        is_suspicious = has_hard_flag or risk >= self.risk_threshold

        return VehicleRiskReport(
            risk_score=round(risk, 4),
            is_suspicious=is_suspicious,
            red_flags=flags,
            features={k: round(v, 2) for k, v in feats.items()},
            model_factors=self.feature_importances[:3],
        )
