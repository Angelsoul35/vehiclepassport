"""VehiclePassport HTTP API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .events import EventType
from .service import VehiclePassportService

app = FastAPI(
    title="VehiclePassport",
    version="1.0.0",
    summary="On-chain vehicle lifecycle log with tampering-risk detection.",
)

_service: VehiclePassportService | None = None


def get_service() -> VehiclePassportService:
    global _service
    if _service is None:
        _service = VehiclePassportService()
    return _service


def _parse_event_type(name: str) -> EventType:
    try:
        return EventType[name.strip().upper()]
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"unknown event type: {name}") from exc


class EventRequest(BaseModel):
    event_type: str
    odometer_km: int = Field(ge=0)
    timestamp: int = Field(ge=0)
    detail: str = ""


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok"}


@app.post("/vehicles/{vin}/events", tags=["passport"])
def record_event(vin: str, request: EventRequest) -> dict:
    return get_service().record_event(
        vin,
        _parse_event_type(request.event_type),
        request.odometer_km,
        request.timestamp,
        request.detail,
    )


@app.get("/vehicles/{vin}/history", tags=["passport"])
def get_history(vin: str) -> dict:
    return {"vin": vin, "events": get_service().history_as_dicts(vin)}


@app.get("/vehicles/{vin}/assessment", tags=["risk"])
def assess(vin: str) -> dict:
    return get_service().assess(vin)
