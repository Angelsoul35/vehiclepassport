from __future__ import annotations

from fastapi.testclient import TestClient

from vehiclepassport.events import EventType
from vehiclepassport.generate import DAY, NOW

LEGIT = [
    (EventType.OWNERSHIP_TRANSFER, 0, 1800),
    (EventType.SERVICE, 15_000, 1400),
    (EventType.SERVICE, 32_000, 1000),
    (EventType.INSPECTION, 50_000, 600),
    (EventType.SERVICE, 67_000, 200),
]
ROLLBACK = [
    (EventType.SERVICE, 40_000, 1400),
    (EventType.SERVICE, 70_000, 900),
    (EventType.SERVICE, 25_000, 400),  # rollback
]


def _record(service, vin, rows):
    for etype, odo, days in rows:
        service.record_event(vin, etype, odo, NOW - days * DAY)


def test_service_assess_legit_and_rollback(service):
    _record(service, "VIN-OK", LEGIT)
    _record(service, "VIN-BAD", ROLLBACK)

    ok = service.assess("VIN-OK")
    assert ok["is_suspicious"] is False
    assert ok["red_flags"] == []

    bad = service.assess("VIN-BAD")
    assert bad["is_suspicious"] is True
    assert any("rollback" in f for f in bad["red_flags"])


def test_history_round_trips(service):
    _record(service, "VIN-H", LEGIT)
    history = service.history_as_dicts("VIN-H")
    assert len(history) == len(LEGIT)
    assert history[0]["event_type"] == "ownership_transfer"
    assert history[0]["data_hash"].startswith("0x")


def _client(service):
    import vehiclepassport.main as main

    main._service = service
    return TestClient(main.app)


def test_api_flow(service):
    client = _client(service)
    assert client.get("/health").json() == {"status": "ok"}

    for etype, odo, days in ROLLBACK:
        resp = client.post(
            "/vehicles/VIN-API/events",
            json={"event_type": etype.label, "odometer_km": odo, "timestamp": NOW - days * DAY},
        )
        assert resp.status_code == 200

    history = client.get("/vehicles/VIN-API/history")
    assert history.status_code == 200
    assert len(history.json()["events"]) == len(ROLLBACK)

    assessment = client.get("/vehicles/VIN-API/assessment")
    assert assessment.status_code == 200
    assert assessment.json()["is_suspicious"] is True


def test_api_rejects_unknown_event_type(service):
    client = _client(service)
    resp = client.post(
        "/vehicles/VIN-X/events",
        json={"event_type": "teleport", "odometer_km": 1, "timestamp": NOW},
    )
    assert resp.status_code == 422
