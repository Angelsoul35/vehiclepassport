from __future__ import annotations

from vehiclepassport.chain.registry import EventRecord, record_hash
from vehiclepassport.events import EventType
from vehiclepassport.features import (
    FEATURE_NAMES,
    extract_features,
    feature_vector,
    red_flags,
)

DAY = 86_400
BASE = 1_700_000_000


def _ev(etype, odo, day):
    return EventRecord(
        event_type=etype,
        odometer_km=odo,
        timestamp=BASE + day * DAY,
        data_hash=record_hash(f"{etype.label}:{odo}"),
    )


def _legit():
    return [
        _ev(EventType.OWNERSHIP_TRANSFER, 0, 0),
        _ev(EventType.SERVICE, 15_000, 365),
        _ev(EventType.INSPECTION, 31_000, 730),
        _ev(EventType.SERVICE, 48_000, 1095),
    ]


def test_feature_vector_length_and_order():
    vec = feature_vector(_legit())
    assert len(vec) == len(FEATURE_NAMES)


def test_legit_history_has_no_rollback():
    feats = extract_features(_legit())
    assert feats["n_rollbacks"] == 0
    assert feats["max_rollback_km"] == 0
    # The ownership transfer (odometer 0) is not a mileage reading, so the
    # timeline runs from the first service (15,000) to the last (48,000).
    assert feats["total_km"] == 33_000
    assert red_flags(_legit(), max_km_per_day=1500) == []


def test_rollback_is_detected():
    history = [
        _ev(EventType.SERVICE, 60_000, 0),
        _ev(EventType.SERVICE, 35_000, 365),  # rollback
    ]
    feats = extract_features(history)
    assert feats["n_rollbacks"] == 1
    assert feats["max_rollback_km"] == 25_000
    flags = red_flags(history, max_km_per_day=1500)
    assert any(f.startswith("odometer rollback") for f in flags)


def test_implausible_jump_is_detected():
    history = [
        _ev(EventType.SERVICE, 10_000, 0),
        _ev(EventType.SERVICE, 130_000, 5),  # +120k km in 5 days
    ]
    flags = red_flags(history, max_km_per_day=1500)
    assert any(f.startswith("implausible mileage jump") for f in flags)


def test_short_history_is_safe():
    feats = extract_features([_ev(EventType.SERVICE, 10_000, 0)])
    assert feats["n_events"] == 1
    assert feats["total_km"] == 0
