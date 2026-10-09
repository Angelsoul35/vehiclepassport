"""Functional tests for the real-used-car benchmark pipeline.

These exercise the real behaviour end to end: loading the vendored real records,
building legitimate and rolled-back histories from them, the deterministic
rollback rule, and the benchmark's generalisation claims (detector beats baseline,
shuffle control collapses to chance). The network fetch is covered with a
monkeypatched transport, so no request leaves the machine.
"""

from __future__ import annotations

import json
import urllib.error

import numpy as np
import pytest

from vehiclepassport import real_benchmark, real_data
from vehiclepassport.events import ODOMETER_EVENTS, EventType
from vehiclepassport.features import red_flags
from vehiclepassport.real_benchmark import _print, _verdict, benchmark, main
from vehiclepassport.real_data import (
    KEPT_FIELDS,
    build_dataset,
    build_history,
    fetch_used_cars,
    load_real_cars,
)

ROLLBACK = "odometer rollback"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def real_cars() -> list[dict]:
    # A subset keeps the benchmark fast while staying real.
    return load_real_cars()[:600]


@pytest.fixture(scope="module")
def report(real_cars):
    return benchmark(cars=real_cars, seed=7)


def _timeline_odos(history) -> list[int]:
    pts = sorted(
        (e.timestamp, e.odometer_km) for e in history if e.event_type in ODOMETER_EVENTS
    )
    return [o for _, o in pts]


def _history_of_kind(car: dict, kind: str) -> list:
    want_fraud = kind != "legit"
    for seed in range(1000):
        events, got = build_history(car, np.random.default_rng(seed), fraud=want_fraud)
        if got == kind:
            return events
    raise AssertionError(f"no {kind!r} history generated for {car}")


# --------------------------------------------------------------------------- #
# Loader returns REAL records
# --------------------------------------------------------------------------- #
def test_loader_returns_real_car_records():
    cars = load_real_cars()
    assert len(cars) >= 1_000  # a substantial real subset is vendored
    for car in cars:
        assert set(KEPT_FIELDS) <= set(car)  # slimmed to the kept columns
        # Real, plausible ranges — a synthetic placeholder would not satisfy these.
        assert 1990 <= car["year"] <= 2023
        assert 1_000 <= car["mileage"] <= 1_000_000
        assert 1 <= car["owners"] <= 6
    # The population is genuinely varied (not one repeated record).
    assert len({c["mark"] for c in cars}) >= 10
    assert len({c["mileage"] for c in cars}) >= 100


def test_loader_distribution_is_realistic():
    cars = load_real_cars()
    years = np.array([c["year"] for c in cars])
    mileage = np.array([c["mileage"] for c in cars])
    # A real used-car population centres on mid-life cars, not brand-new ones.
    assert 2005 <= np.median(years) <= 2020
    assert 50_000 <= np.median(mileage) <= 300_000


# --------------------------------------------------------------------------- #
# The deterministic rollback rule
# --------------------------------------------------------------------------- #
def test_rollback_rule_catches_hand_pinned_rollback():
    # Pin an explicit rollback by hand: 80,000 km drops to 40,000 km.
    from vehiclepassport.chain.registry import EventRecord, record_hash

    day = 86_400
    base = 1_700_000_000

    def ev(odo, d):
        return EventRecord(EventType.SERVICE, odo, base + d * day, record_hash(str(odo)))

    history = [ev(50_000, 0), ev(80_000, 365), ev(40_000, 730)]
    flags = red_flags(history, max_km_per_day=1500.0)
    assert any(f.startswith(ROLLBACK) for f in flags)


def test_injected_rollback_is_a_real_decrease_and_is_caught():
    car = {"year": 2012, "mileage": 150_000, "owners": 2}
    history = _history_of_kind(car, "rollback")
    odos = _timeline_odos(history)
    # The injection actually lowers a later reading below an earlier one.
    assert any(b < a for a, b in zip(odos, odos[1:], strict=False))
    assert any(f.startswith(ROLLBACK) for f in red_flags(history, max_km_per_day=1500.0))


def test_legitimate_history_is_non_decreasing_and_unflagged():
    car = {"year": 2012, "mileage": 150_000, "owners": 2}
    history = _history_of_kind(car, "legit")
    odos = _timeline_odos(history)
    assert odos == sorted(odos)  # monotonically non-decreasing
    flags = red_flags(history, max_km_per_day=1500.0)
    assert not any(f.startswith(ROLLBACK) for f in flags)


# --------------------------------------------------------------------------- #
# Dataset construction
# --------------------------------------------------------------------------- #
def test_build_dataset_is_balanced_and_labels_match_kinds(real_cars):
    histories, labels, kinds = build_dataset(real_cars, seed=3)
    assert len(histories) == len(labels) == len(kinds) == len(real_cars)
    # Balanced legitimate/fraud split.
    assert abs(sum(labels) - len(labels) / 2) <= 1
    # Labels and kinds are consistent: label 1 iff an injected fraud kind.
    for label, kind in zip(labels, kinds, strict=True):
        assert (label == 1) == (kind in {"rollback", "jump"})
        assert (label == 0) == (kind == "legit")


# --------------------------------------------------------------------------- #
# Benchmark: generalisation, baseline, and controls
# --------------------------------------------------------------------------- #
def test_detector_beats_baseline_on_held_out(report):
    # The learned detector is far above the majority-class floor.
    assert report.test_auc >= 0.85
    assert report.detector_test_f1 >= report.baseline_test_f1 + 0.3
    assert report.detector_test_accuracy >= report.baseline_test_accuracy + 0.2
    assert report.baseline_test_auc == pytest.approx(0.5, abs=0.02)


def test_detector_generalises_without_overfitting(report):
    assert report.cv_auc_mean >= 0.85  # not underfit
    assert report.test_auc >= 0.85  # generalises to unseen cars
    assert report.auc_gap <= 0.10  # not overfit


def test_shuffle_control_collapses_auc(report):
    # A real signal must vanish when the labels are permuted.
    assert report.cv_auc_mean >= 0.85
    assert report.shuffle_cv_auc_mean <= 0.6


def test_rollback_rule_recall_is_total(report):
    # Every explicit rollback in the held-out set is caught by the rule.
    assert report.n_explicit_rollbacks > 0
    assert report.rollback_rule_recall >= 0.99


def test_fraud_relevant_features_dominate_importance(report):
    top_three = {name for name, _ in report.feature_importances[:3]}
    # The rollback magnitude/count and mileage pace carry the signal.
    assert "max_rollback_km" in top_three or "n_rollbacks" in top_three


# --------------------------------------------------------------------------- #
# Network fetch (monkeypatched transport — no real request)
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *_):
        return self._body


_PLAUSIBLE = {
    "year": 2016,
    "mileage": 90_000,
    "owners": 1,
    "price": 1_000_000,
    "mark": "Toyota",
    "model": "Corolla",
    "region": "Moscow",
    "engine": "GASOLINE",
    "transmission": "AUTOMATIC",
}
_TOO_OLD = {**_PLAUSIBLE, "year": 1980}
_ZERO_MILEAGE = {**_PLAUSIBLE, "mileage": 0}
_TOO_MANY_OWNERS = {**_PLAUSIBLE, "owners": 99}


def test_fetch_used_cars_parses_and_filters(monkeypatch):
    page = {
        "rows": [
            {"row": _PLAUSIBLE},
            {"row": _TOO_OLD},
            {"row": _ZERO_MILEAGE},
            {"row": _TOO_MANY_OWNERS},
        ]
    }
    pages = iter([page, {"rows": []}])  # second page empty -> stop paging

    def fake_urlopen(req, timeout=None):
        return _FakeResponse(next(pages))

    monkeypatch.setattr(real_data.urllib.request, "urlopen", fake_urlopen)
    cars = fetch_used_cars(n=50)

    # Only the plausible record survives the filter; it is slimmed to KEPT_FIELDS.
    assert len(cars) == 1
    assert cars[0]["mark"] == "Toyota"
    assert set(cars[0]) == set(KEPT_FIELDS)


def test_fetch_used_cars_retries_transient_failure(monkeypatch):
    calls = {"n": 0}
    pages = iter([{"rows": [{"row": _PLAUSIBLE}]}, {"rows": []}])

    def flaky_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("transient")
        return _FakeResponse(next(pages))

    monkeypatch.setattr(real_data.time, "sleep", lambda *_: None)  # no real backoff
    monkeypatch.setattr(real_data.urllib.request, "urlopen", flaky_urlopen)

    cars = fetch_used_cars(n=5)
    assert calls["n"] >= 2  # it retried after the first failure
    assert len(cars) == 1


def test_fetch_used_cars_gives_up_after_retries(monkeypatch):
    def always_fails(req, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(real_data.time, "sleep", lambda *_: None)
    monkeypatch.setattr(real_data.urllib.request, "urlopen", always_fails)

    with pytest.raises(RuntimeError, match="failed to fetch"):
        fetch_used_cars(n=5)


# --------------------------------------------------------------------------- #
# Reporting and verdict logic
# --------------------------------------------------------------------------- #
def test_print_report_renders_key_lines(report, capsys):
    _print(report)
    out = capsys.readouterr().out
    assert "ROC-AUC" in out
    assert "rollback rule" in out.lower()
    assert "shuffled-label" in out.lower()
    assert "Verdict" in out


def test_main_runs_on_subset(monkeypatch, real_cars, capsys):
    # Keep it fast and offline by feeding the vendored subset into the entrypoint.
    monkeypatch.setattr(real_benchmark, "load_real_cars", lambda: real_cars)
    main()
    out = capsys.readouterr().out
    assert "benchmark on REAL used-car data" in out
    assert "Verdict" in out


def test_verdict_classifies_each_fit_state():
    well = {
        "cv_auc_mean": 0.97, "test_auc": 0.98, "train_auc": 0.985,
        "auc_gap": 0.005, "shuffle_cv_auc_mean": 0.5,
    }
    verdict, saturates = _verdict(well)
    assert verdict.startswith("well-fit")
    assert saturates is False

    saturated = {**well, "train_auc": 1.0, "auc_gap": 0.03}
    verdict, saturates = _verdict(saturated)
    assert verdict.startswith("well-fit")
    assert saturates is True
    assert "saturates" in verdict

    underfit = {
        "cv_auc_mean": 0.6, "test_auc": 0.6, "train_auc": 0.65,
        "auc_gap": 0.05, "shuffle_cv_auc_mean": 0.5,
    }
    assert _verdict(underfit)[0].startswith("underfit")

    overfit = {
        "cv_auc_mean": 0.9, "test_auc": 0.7, "train_auc": 0.99,
        "auc_gap": 0.29, "shuffle_cv_auc_mean": 0.5,
    }
    assert _verdict(overfit)[0].startswith("overfit")

    leaky = {
        "cv_auc_mean": 0.9, "test_auc": 0.9, "train_auc": 0.92,
        "auc_gap": 0.02, "shuffle_cv_auc_mean": 0.75,
    }
    assert _verdict(leaky)[0].startswith("inconclusive")
