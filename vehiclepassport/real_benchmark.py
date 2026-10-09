"""Benchmark the tamper detector on histories built from REAL used-car data.

This complements the deterministic, seed-controlled check in
:mod:`vehiclepassport.evaluation` with a benchmark whose feature distributions are
drawn from real vehicles. The legitimate histories are built from real cars in
``imbalet/used_cars`` (432,227 real listings); the fraud histories inject odometer
rollbacks and implausible jumps into a *disjoint* set of real cars. See
:mod:`vehiclepassport.real_data` and ``datasets/README.md`` for the methodology
(real legitimate population + injected fraud) and the licence note.

It reuses the project's own detector and feature code — :func:`feature_vector`,
:func:`red_flags`, and :class:`TamperDetector` (its exact RandomForest and its
``feature_importances``) — so the benchmark measures the shipped detector, not a
throwaway model.

What it reports, and why each line earns its place:

* **Stratified 5-fold cross-validation** (ROC-AUC and F1, mean ± std) on the
  training portion — a stable score, not a lucky split.
* **A held-out split** (ROC-AUC, F1, accuracy) plus the train→test AUC gap — the
  direct over/underfitting read.
* **A majority-class baseline** — the floor any useful detector must clear.
* **The deterministic rollback rule's recall** on the explicit rollbacks — the
  guaranteed catch that stands independent of the model.
* **A shuffled-label control** — retraining on permuted labels collapses CV AUC to
  chance (~0.5), proving the score comes from real structure, not leakage.
* **Feature importances** — the explainable signal (km/year, age, owners, ...).

Leakage is avoided by construction: legitimate and fraud histories come from
disjoint real cars, each history is a distinct real listing, and the held-out and
cross-validation splits are over whole histories, so no vehicle is seen in both
training and scoring.

Run with ``python -m vehiclepassport.real_benchmark``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import cross_val_score

from .detector import TamperDetector
from .features import feature_vector, red_flags
from .real_data import REF_YEAR, build_dataset, load_real_cars

ROLLBACK_PREFIX = "odometer rollback"
DAY = 86_400


@dataclass
class BenchmarkReport:
    n_cars: int
    n_histories: int
    n_legit: int
    n_fraud: int
    # Real-distribution sanity (medians over the built histories' source cars).
    mileage_median: float
    km_per_year_median: float
    age_years_median: float
    owners_median: float
    # Stratified 5-fold cross-validation on the training portion.
    cv_auc_mean: float
    cv_auc_std: float
    cv_f1_mean: float
    cv_f1_std: float
    # Held-out split (RandomForest probability).
    train_auc: float
    test_auc: float
    test_f1: float
    test_accuracy: float
    auc_gap: float
    # Full detector (RandomForest + deterministic hard rules) vs baseline.
    detector_test_f1: float
    detector_test_accuracy: float
    baseline_test_f1: float
    baseline_test_accuracy: float
    baseline_test_auc: float
    # Deterministic rollback rule, measured on the explicit rollbacks.
    rollback_rule_recall: float
    n_explicit_rollbacks: int
    # Shuffled-label control.
    shuffle_cv_auc_mean: float
    verdict: str
    rf_saturates_train: bool
    feature_importances: list[tuple[str, float]] = field(default_factory=list)


def _matrix(histories: list) -> np.ndarray:
    return np.array([feature_vector(h) for h in histories])


def _stratified_split(n: int, labels: np.ndarray, test_frac: float, seed: int):
    """Stratified index split over whole histories (no car in both sides)."""
    rng = np.random.default_rng(seed)
    test_idx: list[int] = []
    for cls in (0, 1):
        members = np.where(labels == cls)[0]
        rng.shuffle(members)
        k = int(round(len(members) * test_frac))
        test_idx.extend(members[:k].tolist())
    test_mask = np.zeros(n, dtype=bool)
    test_mask[test_idx] = True
    train_idx = np.where(~test_mask)[0]
    test_idx_arr = np.where(test_mask)[0]
    return train_idx, test_idx_arr


def _rollback_rule_recall(histories, kinds, max_km_per_day) -> tuple[float, int]:
    """Recall of the deterministic rollback rule on the explicit rollbacks.

    An explicit rollback is a fraud history built with a decreasing reading. The
    rule catches it iff :func:`red_flags` emits an ``"odometer rollback"`` finding.
    """
    caught = total = 0
    for history, kind in zip(histories, kinds, strict=True):
        if kind != "rollback":
            continue
        total += 1
        flags = red_flags(history, max_km_per_day)
        if any(f.startswith(ROLLBACK_PREFIX) for f in flags):
            caught += 1
    return (caught / total if total else 0.0), total


def _source_medians(cars: list[dict]) -> tuple[float, float, float, float]:
    mileage = np.array([c["mileage"] for c in cars], dtype=float)
    age = np.array([max(1, REF_YEAR - c["year"]) for c in cars], dtype=float)
    owners = np.array([c["owners"] for c in cars], dtype=float)
    return (
        float(np.median(mileage)),
        float(np.median(mileage / age)),
        float(np.median(age)),
        float(np.median(owners)),
    )


def _verdict(report_fields: dict) -> tuple[str, bool]:
    cv = report_fields["cv_auc_mean"]
    test = report_fields["test_auc"]
    train = report_fields["train_auc"]
    gap = report_fields["auc_gap"]
    shuffle = report_fields["shuffle_cv_auc_mean"]
    saturates = train >= 0.999
    if cv < 0.70 and test < 0.70:
        return "underfit (low on both cross-validation and held-out)", saturates
    if gap > 0.10:
        return f"overfit (train-test AUC gap {gap:.3f} > 0.10)", saturates
    if not (shuffle <= 0.60):
        return "inconclusive (shuffle control did not collapse to chance)", saturates
    base = (
        "well-fit (cross-validation agrees with held-out, small train-test gap, "
        "shuffle control at chance)"
    )
    if saturates:
        base += "; RandomForest saturates on train, so generalisation is judged by "
        base += "the cross-validation / held-out agreement and the shuffle control"
    return base, saturates


def benchmark(
    *,
    cars: list[dict] | None = None,
    seed: int = 11,
    test_frac: float = 0.25,
    max_km_per_day: float = 1500.0,
    risk_threshold: float = 0.5,
) -> BenchmarkReport:
    cars = cars if cars is not None else load_real_cars()
    histories, labels, kinds = build_dataset(cars, seed=seed)
    y = np.array(labels)
    x = _matrix(histories)
    n = len(histories)

    mileage_med, kpy_med, age_med, owners_med = _source_medians(cars)

    train_idx, test_idx = _stratified_split(n, y, test_frac, seed)
    x_tr, y_tr = x[train_idx], y[train_idx]
    x_te, y_te = x[test_idx], y[test_idx]

    # Reuse the project detector's exact classifier (cloned for an unbiased per-run
    # fit; clone copies hyperparameters without copying any learned state).
    rf = clone(TamperDetector(max_km_per_day=max_km_per_day, risk_threshold=risk_threshold)._model)

    cv_auc = cross_val_score(rf, x_tr, y_tr, cv=5, scoring="roc_auc")
    cv_f1 = cross_val_score(rf, x_tr, y_tr, cv=5, scoring="f1")

    rf.fit(x_tr, y_tr)
    train_prob = rf.predict_proba(x_tr)[:, 1]
    test_prob = rf.predict_proba(x_te)[:, 1]
    train_auc = roc_auc_score(y_tr, train_prob)
    test_auc = roc_auc_score(y_te, test_prob)
    test_pred = (test_prob >= risk_threshold).astype(int)
    test_f1 = f1_score(y_te, test_pred)
    test_acc = accuracy_score(y_te, test_pred)

    # Full detector (RandomForest + hard rules) end to end vs a majority baseline.
    detector = TamperDetector(max_km_per_day=max_km_per_day, risk_threshold=risk_threshold).fit(
        [histories[i] for i in train_idx], [labels[i] for i in train_idx]
    )
    det_pred = np.array(
        [1 if detector.assess(histories[i]).is_suspicious else 0 for i in test_idx]
    )
    detector_f1 = f1_score(y_te, det_pred)
    detector_acc = accuracy_score(y_te, det_pred)

    baseline = DummyClassifier(strategy="most_frequent").fit(x_tr, y_tr)
    base_pred = baseline.predict(x_te)
    base_f1 = f1_score(y_te, base_pred, zero_division=0)
    base_acc = accuracy_score(y_te, base_pred)
    try:
        base_auc = roc_auc_score(y_te, baseline.predict_proba(x_te)[:, 1])
    except ValueError:
        base_auc = 0.5

    rule_recall, n_rollbacks = _rollback_rule_recall(
        [histories[i] for i in test_idx],
        [kinds[i] for i in test_idx],
        max_km_per_day,
    )

    # Shuffled-label control: permute the training labels and refit. A detector
    # that learned real structure must collapse to chance here.
    rng = np.random.default_rng(seed + 1)
    y_shuffled = y_tr.copy()
    rng.shuffle(y_shuffled)
    shuffle_auc = cross_val_score(clone(rf), x_tr, y_shuffled, cv=5, scoring="roc_auc")

    importances = detector.feature_importances

    fields = {
        "cv_auc_mean": float(cv_auc.mean()),
        "test_auc": float(test_auc),
        "train_auc": float(train_auc),
        "auc_gap": float(train_auc - test_auc),
        "shuffle_cv_auc_mean": float(shuffle_auc.mean()),
    }
    verdict, saturates = _verdict(fields)

    return BenchmarkReport(
        n_cars=len(cars),
        n_histories=n,
        n_legit=int((y == 0).sum()),
        n_fraud=int((y == 1).sum()),
        mileage_median=round(mileage_med, 1),
        km_per_year_median=round(kpy_med, 1),
        age_years_median=round(age_med, 1),
        owners_median=round(owners_med, 1),
        cv_auc_mean=round(float(cv_auc.mean()), 3),
        cv_auc_std=round(float(cv_auc.std()), 3),
        cv_f1_mean=round(float(cv_f1.mean()), 3),
        cv_f1_std=round(float(cv_f1.std()), 3),
        train_auc=round(float(train_auc), 3),
        test_auc=round(float(test_auc), 3),
        test_f1=round(float(test_f1), 3),
        test_accuracy=round(float(test_acc), 3),
        auc_gap=round(float(train_auc - test_auc), 3),
        detector_test_f1=round(float(detector_f1), 3),
        detector_test_accuracy=round(float(detector_acc), 3),
        baseline_test_f1=round(float(base_f1), 3),
        baseline_test_accuracy=round(float(base_acc), 3),
        baseline_test_auc=round(float(base_auc), 3),
        rollback_rule_recall=round(float(rule_recall), 3),
        n_explicit_rollbacks=n_rollbacks,
        shuffle_cv_auc_mean=round(float(shuffle_auc.mean()), 3),
        verdict=verdict,
        rf_saturates_train=saturates,
        feature_importances=importances,
    )


def _print(report: BenchmarkReport) -> None:
    r = report
    print("Tamper-detector benchmark on REAL used-car data (imbalet/used_cars)")
    print("=" * 68)
    print("Methodology: real legitimate population + injected fraud (rollbacks and")
    print("implausible jumps) on a disjoint set of real cars. Feature distributions")
    print("(mileage, age, km/year, owners) are drawn from real listings.")
    print()
    print(f"  real cars loaded      : {r.n_cars:,}")
    print(
        f"  histories built       : {r.n_histories:,}  "
        f"({r.n_legit:,} legit / {r.n_fraud:,} fraud)"
    )
    print("  real distribution      :")
    print(f"      mileage median    : {r.mileage_median:,.0f} km")
    print(f"      km/year median    : {r.km_per_year_median:,.0f} km/year")
    print(f"      age median        : {r.age_years_median:.0f} years")
    print(f"      owners median     : {r.owners_median:.0f}")
    print()
    print("  Stratified 5-fold cross-validation (train portion):")
    print(f"      ROC-AUC           : {r.cv_auc_mean:.3f} +/- {r.cv_auc_std:.3f}")
    print(f"      F1                : {r.cv_f1_mean:.3f} +/- {r.cv_f1_std:.3f}")
    print()
    print("  Held-out split (RandomForest probability):")
    print(f"      ROC-AUC           : {r.test_auc:.3f}   (train {r.train_auc:.3f})")
    print(f"      F1                : {r.test_f1:.3f}")
    print(f"      accuracy          : {r.test_accuracy:.3f}")
    print(f"      train-test AUC gap: {r.auc_gap:.3f}   (small = not overfit)")
    print()
    print("  Full detector (RandomForest + hard rules) vs majority baseline:")
    print(f"      detector  F1 / acc: {r.detector_test_f1:.3f} / {r.detector_test_accuracy:.3f}")
    print(f"      baseline  F1 / acc: {r.baseline_test_f1:.3f} / {r.baseline_test_accuracy:.3f}")
    print(f"      baseline  ROC-AUC : {r.baseline_test_auc:.3f}  (chance)")
    print()
    print("  Deterministic rollback rule (independent of the model):")
    print(
        f"      recall on explicit rollbacks: {r.rollback_rule_recall:.3f} "
        f"({r.n_explicit_rollbacks} held-out rollbacks)"
    )
    print()
    print("  Shuffled-label control (labels permuted, refit):")
    print(f"      CV ROC-AUC        : {r.shuffle_cv_auc_mean:.3f}  (collapses to chance)")
    print()
    print("  Feature importances (the explainable signal):")
    for name, weight in r.feature_importances:
        print(f"      {name:<20}: {weight:.4f}")
    print()
    print(f"  Verdict: {r.verdict}")


def main() -> None:
    _print(benchmark())


if __name__ == "__main__":
    main()
