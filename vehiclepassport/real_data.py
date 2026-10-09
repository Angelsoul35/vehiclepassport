"""Load real used-car records and build legitimate / rolled-back odometer histories.

The **legitimate** class is built from REAL cars: the ``imbalet/used_cars`` dataset
on Hugging Face (432,227 real listings). Each car's real ``year``, ``mileage`` and
``owners`` fix a plausible, monotonically rising odometer history, so the feature
distributions the detector sees — mileage, age, km/year, owner count — are those
of real vehicles, not a hand-tuned generator.

The **fraud** class takes a *disjoint* set of real cars and injects an odometer
rollback (a later reading set strictly BELOW an earlier one) or an implausible
mileage jump — the exact signatures of odometer fraud. There is no public dataset
of labelled real rollback *histories*, so this follows the standard
fraud-detection methodology used whenever labelled fraud is scarce: a **real
legitimate population plus injected fraud**. The real distributions make the
validation faithful to real-world vehicle statistics; the injection makes the
fraud label unambiguous (a decrease in a mileage timeline is, by definition,
odometer fraud).

Leakage is avoided by construction: the cars used for the legitimate class and the
cars used for the fraud class are disjoint, so no vehicle appears on both sides,
and each history is derived from a single distinct real listing (no templates are
reused). The split into train/test is then over whole histories.

Fetching uses the Hugging Face datasets-server rows API (no auth). The vendored
subset under ``datasets/`` lets the benchmark and tests run offline; see
``datasets/README.md`` for the source, licence note, and how to regenerate.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import numpy as np

from .chain.registry import EventRecord, record_hash
from .events import EventType
from .generate import DAY, NOW

# Hugging Face datasets-server rows API (public, no authentication).
DATASET = "imbalet/used_cars"
_ROWS_URL = "https://datasets-server.huggingface.co/rows"
_PAGE = 100  # the rows API returns at most 100 rows per request

# The reference "today" against which a car's age (and therefore its real km/year)
# is computed. The listings predate 2024, so this keeps every age at least 1 year.
REF_YEAR = 2024

# Columns kept from each real record. They carry the real distributions the
# detector is validated against, plus provenance (mark/model/region/engine).
KEPT_FIELDS = (
    "owners",
    "year",
    "price",
    "mileage",
    "mark",
    "model",
    "region",
    "engine",
    "transmission",
)

# Plausibility bounds used to drop corrupt or non-car rows (e.g. a missing year,
# a zero odometer, an absurd lifetime pace). They are wide on purpose: the point
# is to keep the real spread, not to hand-pick an easy population.
_MIN_YEAR = 1990
_MAX_YEAR = REF_YEAR - 1
_MIN_MILEAGE = 1_000
_MAX_MILEAGE = 1_000_000
_MIN_OWNERS = 1
_MAX_OWNERS = 6
_MAX_KM_PER_YEAR = 80_000

_DEFAULT_VENDORED = Path(__file__).resolve().parent.parent / "datasets" / "used_cars.jsonl"


# --------------------------------------------------------------------------- #
# Fetching real records
# --------------------------------------------------------------------------- #
def _http_get_json(url: str, *, timeout: float = 60.0, retries: int = 4) -> dict:
    """GET a URL and parse JSON, retrying transient failures with backoff.

    This is the single network seam; tests monkeypatch ``urllib.request.urlopen``
    (or this function) so no real request is made.
    """
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vehiclepassport-benchmark"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only)
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(2.0 * (2**attempt))  # 2s, 4s, 8s, ...
    raise RuntimeError(f"failed to fetch {url} after {retries} attempts") from last_err


def _slim(row: dict) -> dict:
    return {k: row.get(k) for k in KEPT_FIELDS}


def _is_plausible(car: dict) -> bool:
    year, mileage, owners = car.get("year"), car.get("mileage"), car.get("owners")
    if not all(isinstance(v, int) for v in (year, mileage, owners)):
        return False
    if not (_MIN_YEAR <= year <= _MAX_YEAR):
        return False
    if not (_MIN_MILEAGE <= mileage <= _MAX_MILEAGE):
        return False
    if not (_MIN_OWNERS <= owners <= _MAX_OWNERS):
        return False
    age = REF_YEAR - year
    return age >= 1 and (mileage / age) <= _MAX_KM_PER_YEAR


def fetch_used_cars(n: int = 8_000, *, offset: int = 0, timeout: float = 60.0) -> list[dict]:
    """Fetch up to ``n`` plausible real car records from the datasets-server API.

    Pages through the public rows API, slims each row to :data:`KEPT_FIELDS`, and
    keeps only plausible records (see the module-level bounds). Returns real
    records only — nothing is synthesised here.
    """
    cars: list[dict] = []
    cursor = offset
    while len(cars) < n:
        url = (
            f"{_ROWS_URL}?dataset={quote(DATASET, safe='')}"
            f"&config=default&split=train&offset={cursor}&length={_PAGE}"
        )
        payload = _http_get_json(url, timeout=timeout)
        rows = payload.get("rows", [])
        if not rows:
            break  # exhausted the split
        for entry in rows:
            car = _slim(entry.get("row", {}))
            if _is_plausible(car):
                cars.append(car)
                if len(cars) >= n:
                    break
        cursor += _PAGE
    return cars


# --------------------------------------------------------------------------- #
# Vendored subset
# --------------------------------------------------------------------------- #
def load_real_cars(path: str | Path | None = None) -> list[dict]:
    """Load the vendored real-car subset (JSONL). Each line is one real record."""
    p = Path(path) if path is not None else _DEFAULT_VENDORED
    cars: list[dict] = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cars.append(json.loads(line))
    return cars


def save_real_cars(cars: list[dict], path: str | Path) -> None:
    """Write real-car records to JSONL (one record per line)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        for car in cars:
            fh.write(json.dumps(car, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Building odometer histories from real records
# --------------------------------------------------------------------------- #
def _event(event_type: EventType, odo: int, ts: int) -> EventRecord:
    return EventRecord(
        event_type=event_type,
        odometer_km=int(odo),
        timestamp=int(ts),
        data_hash=record_hash(f"{event_type.label}:{int(odo)}:{int(ts)}"),
    )


def build_history(
    car: dict, rng: np.random.Generator, *, fraud: bool
) -> tuple[list[EventRecord], str]:
    """Build one odometer history from a real car record.

    The measurement timeline rises monotonically from ~0 to the car's **real**
    mileage over its **real** age, with the number of readings scaled by age. A
    legitimate car keeps that legitimate-by-construction path. A fraudulent car has a
    rollback (a later reading dropped strictly below an earlier one) or an
    implausible jump injected into it. Ownership-transfer events are added to
    match the real ``owners`` count; they carry a last-known value and so do not
    anchor the mileage timeline.

    Returns ``(events, kind)`` where ``kind`` is ``"legit"``, ``"rollback"`` or
    ``"jump"``.
    """
    year, mileage, owners = int(car["year"]), int(car["mileage"]), int(car["owners"])
    age_years = max(1, REF_YEAR - year)
    age_days = age_years * 365
    start_ts = NOW - age_days * DAY

    n_read = int(np.clip(age_years + 2, 4, 18))
    read_days = np.sort(
        rng.choice(np.arange(10, max(age_days, n_read + 11)), size=n_read, replace=False)
    ).astype(float)

    # Odometer tracks elapsed time (a roughly constant pace to the real mileage)
    # with mild measurement noise, floored to stay positive. Tying distance to
    # time keeps the km/day between any two readings physically plausible and
    # keeps km/year faithful to the real listing; a path decoupled from time could
    # put two nearby readings far apart in km and trip the implausible-jump rule
    # on a perfectly legitimate car. The positive floor keeps every reading a real
    # value, so an injected rollback is always a genuine decrease.
    frac = read_days / age_days
    base = frac * mileage
    noise = rng.normal(0.0, mileage * 0.01, size=n_read)
    odo = np.maximum.accumulate(np.clip(base + noise, 1.0, None))

    kind = "legit"
    if fraud:
        kind = "rollback" if rng.random() < 0.72 else "jump"
        j = int(rng.integers(1, n_read - 1))
        if kind == "rollback":
            # Drop every reading from j on so reading j sits strictly below reading
            # j-1 by a 10-50% margin (at least 1,000 km, so integer rounding can
            # never erase it) — a textbook odometer rollback, guaranteed to be a
            # real decrease rather than one swallowed by the gap between readings.
            cut = max(1_000.0, float(odo[j - 1]) * float(rng.uniform(0.1, 0.5)))
            target = max(0.0, float(odo[j - 1]) - cut)
            drop = float(odo[j]) - target
            odo[j:] = np.maximum(0.0, odo[j:] - drop)
        else:
            # A large distance over the window ending at reading j: the signature
            # of a cloned cluster. Magnitudes span obvious to borderline, so the
            # model — not only the hard km/day rule — has to earn its score.
            bump = float(rng.uniform(0.3, 0.9) * mileage)
            odo[j:] = odo[j:] + bump

    events: list[EventRecord] = []
    for i, (d, km) in enumerate(zip(read_days, odo, strict=True)):
        ts = start_ts + int(d) * DAY
        if i % 5 == 0:
            etype = EventType.INSPECTION
        elif i % 7 == 0:
            etype = EventType.PART_REPLACEMENT
        else:
            etype = EventType.SERVICE
        events.append(_event(etype, round(max(0.0, km)), ts))

    # Ownership transfers, one per real owner, carrying the last-known reading at
    # their time (not a measurement, so excluded from the mileage timeline).
    for k in range(owners):
        frac = (k + 0.5) / owners
        d = 10 + frac * (age_days - 10)
        ts = start_ts + int(d) * DAY
        km = float(np.interp(d, read_days, odo))
        events.append(_event(EventType.OWNERSHIP_TRANSFER, round(max(0.0, km)), ts))

    events.sort(key=lambda e: e.timestamp)
    return events, kind


def build_dataset(
    cars: list[dict], *, seed: int = 11
) -> tuple[list[list[EventRecord]], list[int], list[str]]:
    """Build a balanced legitimate/fraud set of histories from real car records.

    The cars are split into two **disjoint** halves — one becomes legitimate
    histories, the other has fraud injected — so no vehicle appears in both
    classes. Returns ``(histories, labels, kinds)`` with ``label`` 1 for fraud.
    """
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(cars))
    half = len(idx) // 2
    legit_idx, fraud_idx = idx[:half], idx[half:]

    histories: list[list[EventRecord]] = []
    labels: list[int] = []
    kinds: list[str] = []
    for i in legit_idx:
        events, kind = build_history(cars[int(i)], rng, fraud=False)
        histories.append(events)
        labels.append(0)
        kinds.append(kind)
    for i in fraud_idx:
        events, kind = build_history(cars[int(i)], rng, fraud=True)
        histories.append(events)
        labels.append(1)
        kinds.append(kind)

    order = rng.permutation(len(histories))
    return (
        [histories[int(i)] for i in order],
        [labels[int(i)] for i in order],
        [kinds[int(i)] for i in order],
    )
