"""Synthetic vehicle lifecycle histories, honest and tampered.

An honest vehicle has a monotonically rising odometer at a plausible rate and
regular servicing. A tampered vehicle carries one of two classic frauds: an
*odometer rollback* (the reading drops before a sale) or an *implausible jump*
(a large distance appears over a few days, the signature of a cloned or swapped
cluster). Everything is synthetic and deterministic, labelled for evaluation.
"""

from __future__ import annotations

import numpy as np

from .chain.registry import EventRecord, record_hash
from .events import EventType

DAY = 86_400
NOW = 1_760_000_000  # a fixed "today" so histories are reproducible


def _event(event_type: EventType, odo: int, ts: int) -> EventRecord:
    return EventRecord(
        event_type=event_type,
        odometer_km=int(odo),
        timestamp=int(ts),
        data_hash=record_hash(f"{event_type.label}:{int(odo)}:{int(ts)}"),
    )


def make_history(rng: np.random.Generator, tampered: bool) -> tuple[list[EventRecord], int, str]:
    """Return (events, label, kind). label is 1 for tampered, else 0."""
    age_days = int(rng.uniform(3 * 365, 12 * 365))
    start_ts = NOW - age_days * DAY
    # About a quarter of vehicles are high-mileage commercial use (a taxi, a
    # delivery van). An honest one of these still has a monotonically rising
    # odometer — just a much steeper slope. Including them in training stops the
    # model from equating "high mileage" with fraud: high *monotonic* mileage is
    # honest, a *rollback* or an impossible *jump* is not.
    if rng.random() < 0.25:
        daily_km = float(rng.uniform(70.0, 230.0))  # ~26k..84k km/year (commercial)
    else:
        daily_km = float(rng.uniform(22.0, 70.0))  # ~8k..26k km/year (private)

    n_events = int(rng.integers(9, 20))
    day_offsets = np.sort(rng.choice(np.arange(10, age_days), size=n_events, replace=False))
    odo = np.array([max(0, d * daily_km + rng.normal(0, 150)) for d in day_offsets])
    odo = np.maximum.accumulate(odo)  # honest: never decreases

    kind = "honest"
    if tampered:
        kind = str(rng.choice(["rollback", "jump"]))
        j = int(rng.integers(n_events // 3, n_events - 1))
        if kind == "rollback":
            cut = float(rng.uniform(30_000, 90_000))
            odo[j:] = np.maximum(0.0, odo[j:] - cut)
        else:  # implausible jump over a short window
            bump = float(rng.uniform(80_000, 160_000))
            odo[j:] = odo[j:] + bump

    events: list[EventRecord] = []
    for i, (d, km) in enumerate(zip(day_offsets, odo, strict=True)):
        ts = start_ts + int(d) * DAY
        if i == 0:
            etype = EventType.OWNERSHIP_TRANSFER
        elif i % 5 == 0:
            etype = EventType.INSPECTION
        elif i % 7 == 0:
            etype = EventType.PART_REPLACEMENT
        else:
            etype = EventType.SERVICE
        events.append(_event(etype, round(km), ts))

    return events, (1 if tampered else 0), kind


def make_dataset(
    n: int = 600, tamper_ratio: float = 0.4, seed: int = 11
) -> tuple[list[list[EventRecord]], list[int]]:
    rng = np.random.default_rng(seed)
    histories: list[list[EventRecord]] = []
    labels: list[int] = []
    for _ in range(n):
        tampered = rng.random() < tamper_ratio
        events, label, _ = make_history(rng, tampered)
        histories.append(events)
        labels.append(label)
    return histories, labels
