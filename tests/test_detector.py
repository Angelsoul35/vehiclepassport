from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from vehiclepassport.chain.registry import EventRecord, record_hash
from vehiclepassport.detector import TamperDetector
from vehiclepassport.events import EventType
from vehiclepassport.features import feature_vector
from vehiclepassport.generate import make_dataset

DAY = 86_400
BASE = 1_700_000_000


def _ev(etype, odo, day):
    return EventRecord(
        event_type=etype,
        odometer_km=odo,
        timestamp=BASE + day * DAY,
        data_hash=record_hash(f"{etype.label}:{odo}"),
    )


def test_unfitted_detector_raises():
    with pytest.raises(RuntimeError):
        TamperDetector().assess([])


def test_honest_vehicle_is_clean(detector):
    history = [
        _ev(EventType.OWNERSHIP_TRANSFER, 0, 0),
        _ev(EventType.SERVICE, 15_000, 365),
        _ev(EventType.INSPECTION, 31_000, 730),
        _ev(EventType.SERVICE, 47_000, 1095),
        _ev(EventType.SERVICE, 63_000, 1460),
    ]
    report = detector.assess(history)
    assert report.is_suspicious is False
    assert report.red_flags == []
    assert report.risk_score < 0.5


def test_rollback_vehicle_is_flagged(detector):
    history = [
        _ev(EventType.SERVICE, 20_000, 0),
        _ev(EventType.SERVICE, 55_000, 365),
        _ev(EventType.SERVICE, 30_000, 730),  # rollback
    ]
    report = detector.assess(history)
    assert report.is_suspicious is True
    assert any(f.startswith("odometer rollback") for f in report.red_flags)
    assert report.model_factors  # explanation populated


def test_hard_flag_overrides_low_model_score(detector):
    # Even a two-point history with a rollback must be suspicious.
    history = [
        _ev(EventType.SERVICE, 90_000, 0),
        _ev(EventType.SERVICE, 10_000, 400),
    ]
    report = detector.assess(history)
    assert report.is_suspicious is True


def test_held_out_accuracy_is_high():
    histories, labels = make_dataset(n=600, seed=9)
    idx = np.arange(len(histories))
    tr, te = train_test_split(idx, test_size=0.25, random_state=0, stratify=labels)
    det = TamperDetector().fit([histories[i] for i in tr], [labels[i] for i in tr])
    x_te = np.array([feature_vector(histories[i]) for i in te])
    pred = (det._model.predict_proba(x_te)[:, 1] >= 0.5).astype(int)
    assert accuracy_score([labels[i] for i in te], pred) > 0.9


def test_detector_generalises_without_overfitting():
    # Independent test set (different seed) + CV: a high score here is legitimate
    # generalisation, and the tiny train-test gap rules out overfitting.
    from vehiclepassport.evaluation import evaluate

    report = evaluate()
    assert report.cv_f1_mean >= 0.9          # not underfit
    assert report.test_f1 >= 0.9             # generalises to unseen histories
    assert report.train_test_gap <= 0.1      # not overfit
