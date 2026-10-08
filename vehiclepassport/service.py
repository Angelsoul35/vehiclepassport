"""Tie the pieces together: record lifecycle events and assess tampering risk."""

from __future__ import annotations

from dataclasses import asdict

from .chain.registry import (
    EventRecord,
    InMemoryRegistryClient,
    RegistryClient,
    record_hash,
    vehicle_id,
)
from .config import Settings, get_settings
from .detector import TamperDetector, VehicleRiskReport
from .events import EventType


class VehiclePassportService:
    def __init__(
        self,
        settings: Settings | None = None,
        registry: RegistryClient | None = None,
        detector: TamperDetector | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry if registry is not None else self._build_registry()
        self.detector = detector or TamperDetector(
            max_km_per_day=self.settings.max_km_per_day,
            risk_threshold=self.settings.risk_threshold,
        ).fit()

    def _build_registry(self) -> RegistryClient:
        if (
            self.settings.chain_enabled
            and self.settings.contract_address
            and self.settings.chain_private_key
        ):
            from web3 import Web3

            from .chain.registry import Web3RegistryClient

            w3 = Web3(Web3.HTTPProvider(self.settings.chain_rpc_url))
            account = w3.eth.account.from_key(self.settings.chain_private_key).address
            return Web3RegistryClient(
                w3, self.settings.contract_address, account, self.settings.chain_private_key
            )
        return InMemoryRegistryClient()

    def record_event(
        self,
        vin: str,
        event_type: EventType,
        odometer_km: int,
        timestamp: int,
        detail: str = "",
    ) -> dict:
        index = self.registry.record_event(
            vehicle_id(vin),
            event_type,
            odometer_km,
            timestamp,
            record_hash(detail or f"{event_type.label}:{odometer_km}:{timestamp}"),
        )
        return {
            "vin": vin,
            "index": index,
            "event_type": event_type.label,
            "odometer_km": odometer_km,
            "timestamp": timestamp,
            "contract_address": self.registry.address,
        }

    def get_history(self, vin: str) -> list[EventRecord]:
        return self.registry.history(vehicle_id(vin))

    def history_as_dicts(self, vin: str) -> list[dict]:
        out = []
        for e in self.get_history(vin):
            out.append(
                {
                    "event_type": e.event_type.label,
                    "odometer_km": e.odometer_km,
                    "timestamp": e.timestamp,
                    "data_hash": "0x" + e.data_hash.hex(),
                }
            )
        return out

    def assess(self, vin: str) -> dict:
        history = self.get_history(vin)
        report: VehicleRiskReport = self.detector.assess(history)
        result = asdict(report)
        result["vin"] = vin
        result["n_events"] = len(history)
        result["contract_address"] = self.registry.address
        return result
