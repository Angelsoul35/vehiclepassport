"""Score a vehicle's history for tampering risk.

The detector combines two signals. A RandomForest, trained on labelled legitimate
and tampered histories, produces a risk score from the engineered features — it
picks up soft, combined patterns (irregular servicing, odd mileage variance). On
top of that sit deterministic red flags (a rollback, an implausible jump): if the
history contains one, the vehicle is suspicious regardless of the model score,
because a dropped odometer is not a matter of probability. The report carries
both, so a decision is always explainable — and when the model flags a vehicle
with *no* hard red flag, the report still names the features of that specific
vehicle that look unlike a legitimate car (``model_factors``), rather than a
generic ranking.
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
        self._legit_mean: np.ndarray | None = None
        self._legit_std: np.ndarray | None = None
        self._fitted = False

    def fit(
        self,
        histories: list[list[EventRecord]] | None = None,
        labels: list[int] | None = None,
    ) -> TamperDetector:
        if histories is None:
            histories, labels = make_dataset()
        x = np.array([feature_vector(h) for h in histories])
        y = np.array(labels)
        self._model.fit(x, y)
        # Keep the legitimate-class feature distribution so a model-only flag can
        # be explained per vehicle: which of *its* features look unlike a
        # legitimate car.
        legit = x[y == 0]
        self._legit_mean = legit.mean(axis=0)
        self._legit_std = legit.std(axis=0) + 1e-9
        self._fitted = True
        return self

    @property
    def feature_importances(self) -> list[tuple[str, float]]:
        importances = self._model.feature_importances_
        pairs = sorted(
            zip(FEATURE_NAMES, importances, strict=True), key=lambda p: p[1], reverse=True
        )
        return [(name, round(float(w), 4)) for name, w in pairs]

    def _instance_factors(self, vector: list[float], k: int = 3) -> list[tuple[str, float]]:
        """Per-vehicle explanation of a model score: the features where *this*
        vehicle deviates most from a legitimate car, as a signed z-score weighted
        by the model's importance. Positive means "more than a typical legitimate
        car".
        """
        assert self._legit_mean is not None and self._legit_std is not None
        # Clip the z-score: a feature that is identically zero in legitimate cars
        # (e.g. rollback count) has ~zero variance, which would otherwise yield a
        # meaningless astronomical z. Clipped, a value of +/-20 just reads as
        # "far outside anything seen in a legitimate vehicle".
        z = np.clip((np.array(vector) - self._legit_mean) / self._legit_std, -20.0, 20.0)
        weighted = np.abs(z) * self._model.feature_importances_
        order = np.argsort(weighted)[::-1]
        out: list[tuple[str, float]] = []
        for i in order[:k]:
            if weighted[i] <= 0:
                break
            out.append((FEATURE_NAMES[i], round(float(z[i]), 2)))
        return out

    def assess(self, history: list[EventRecord]) -> VehicleRiskReport:
        if not self._fitted:
            raise RuntimeError("Detector is not fitted. Call fit() first.")
        feats = extract_features(history)
        vector = feature_vector(history)
        x = np.array([vector])
        risk = float(self._model.predict_proba(x)[0][1])

        flags = red_flags(history, self.max_km_per_day)
        has_hard_flag = any(f.startswith(HARD_FLAG_PREFIXES) for f in flags)
        is_suspicious = has_hard_flag or risk >= self.risk_threshold

        return VehicleRiskReport(
            risk_score=round(risk, 4),
            is_suspicious=is_suspicious,
            red_flags=flags,
            features={k: round(v, 2) for k, v in feats.items()},
            # Per-vehicle reasons (not global importances), so even a model-only
            # flag — one with no hard red flag — explains itself.
            model_factors=self._instance_factors(vector),
        )
