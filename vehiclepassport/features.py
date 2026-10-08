"""Turn a vehicle's event history into features and human-readable red flags.

The feature vector feeds the risk model. The red flags are deterministic, rule-
based findings (a rollback, an implausible jump, a long gap) that stand on their
own: they explain a decision in plain terms and do not depend on the model.
"""

from __future__ import annotations

from datetime import date

from .chain.registry import EventRecord
from .events import ODOMETER_EVENTS

DAY = 86_400

FEATURE_NAMES = [
    "n_events",
    "age_days",
    "total_km",
    "km_per_year",
    "n_rollbacks",
    "max_rollback_km",
    "max_km_per_day",
    "mean_interval_days",
    "max_gap_days",
    "n_owners",
]


def _odometer_timeline(history: list[EventRecord]) -> list[tuple[int, int]]:
    """(timestamp, odometer) for events that carry a real mileage reading, sorted."""
    points = [
        (e.timestamp, e.odometer_km) for e in history if e.event_type in ODOMETER_EVENTS
    ]
    return sorted(points)


def extract_features(history: list[EventRecord]) -> dict[str, float]:
    timeline = _odometer_timeline(history)
    n_owners = sum(1 for e in history if e.event_type.name == "OWNERSHIP_TRANSFER")

    if len(timeline) < 2:
        feats = dict.fromkeys(FEATURE_NAMES, 0.0)
        feats["n_events"] = float(len(history))
        feats["n_owners"] = float(n_owners)
        return feats

    times = [t for t, _ in timeline]
    odos = [o for _, o in timeline]

    age_days = (times[-1] - times[0]) / DAY
    total_km = odos[-1] - odos[0]
    km_per_year = (total_km / age_days * 365) if age_days > 0 else 0.0

    rollbacks = 0
    max_rollback = 0.0
    max_kpd = 0.0
    intervals = []
    for (t0, o0), (t1, o1) in zip(timeline, timeline[1:], strict=False):
        dt_days = max((t1 - t0) / DAY, 1e-9)
        intervals.append((t1 - t0) / DAY)
        delta = o1 - o0
        if delta < 0:
            rollbacks += 1
            max_rollback = max(max_rollback, -delta)
        else:
            max_kpd = max(max_kpd, delta / dt_days)

    return {
        "n_events": float(len(history)),
        "age_days": float(age_days),
        "total_km": float(total_km),
        "km_per_year": float(km_per_year),
        "n_rollbacks": float(rollbacks),
        "max_rollback_km": float(max_rollback),
        "max_km_per_day": float(max_kpd),
        "mean_interval_days": float(sum(intervals) / len(intervals)),
        "max_gap_days": float(max(intervals)),
        "n_owners": float(n_owners),
    }


def feature_vector(history: list[EventRecord]) -> list[float]:
    feats = extract_features(history)
    return [feats[name] for name in FEATURE_NAMES]


def red_flags(history: list[EventRecord], max_km_per_day: float) -> list[str]:
    """Deterministic findings that explain a risk independently of the model."""
    timeline = _odometer_timeline(history)
    flags: list[str] = []
    for (t0, o0), (t1, o1) in zip(timeline, timeline[1:], strict=False):
        if o1 < o0:
            flags.append(
                f"odometer rollback: {o0:,} km on {date.fromtimestamp(t0)} "
                f"dropped to {o1:,} km on {date.fromtimestamp(t1)} "
                f"(-{o0 - o1:,} km)"
            )
            continue
        dt_days = max((t1 - t0) / DAY, 1e-9)
        kpd = (o1 - o0) / dt_days
        if kpd > max_km_per_day:
            flags.append(
                f"implausible mileage jump: +{o1 - o0:,} km in {dt_days:.0f} days "
                f"({kpd:,.0f} km/day) around {date.fromtimestamp(t1)}"
            )
    # A very long gap between recorded readings can hide tampering.
    for (t0, _), (t1, _) in zip(timeline, timeline[1:], strict=False):
        gap_days = (t1 - t0) / DAY
        if gap_days > 3 * 365:
            flags.append(
                f"long gap without a reading: {gap_days / 365:.1f} years "
                f"ending {date.fromtimestamp(t1)}"
            )
    return flags
