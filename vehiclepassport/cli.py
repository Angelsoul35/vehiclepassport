"""VehiclePassport command-line demo."""

from __future__ import annotations

import argparse

from web3 import EthereumTesterProvider, Web3

from .chain.registry import Web3RegistryClient, deploy_registry, vehicle_id
from .config import get_settings
from .events import EventType
from .generate import DAY, NOW
from .service import VehiclePassportService

# (event type, odometer km, days before NOW)
HONEST = [
    (EventType.OWNERSHIP_TRANSFER, 0, 2200),
    (EventType.SERVICE, 12_000, 1900),
    (EventType.INSPECTION, 28_000, 1550),
    (EventType.SERVICE, 44_000, 1200),
    (EventType.SERVICE, 61_000, 850),
    (EventType.INSPECTION, 78_000, 500),
    (EventType.SERVICE, 95_000, 150),
]

# Same vehicle, but the odometer is rolled back before the last service.
TAMPERED = [
    (EventType.OWNERSHIP_TRANSFER, 0, 2200),
    (EventType.SERVICE, 12_000, 1900),
    (EventType.INSPECTION, 28_000, 1550),
    (EventType.SERVICE, 44_000, 1200),
    (EventType.SERVICE, 61_000, 850),
    (EventType.OWNERSHIP_TRANSFER, 61_500, 520),
    (EventType.SERVICE, 35_000, 500),  # rollback: 61,500 -> 35,000
    (EventType.SERVICE, 48_000, 150),
]


def _record(service: VehiclePassportService, vin: str, rows) -> None:
    for etype, odo, days_before in rows:
        service.record_event(vin, etype, odo, NOW - days_before * DAY)


def demo() -> None:
    settings = get_settings()

    print("1) Deploying VehicleRegistry to an in-memory EVM ...")
    w3 = Web3(EthereumTesterProvider())
    operator = w3.eth.accounts[0]
    address = deploy_registry(w3, operator)
    registry = Web3RegistryClient(w3, address, operator)
    print(f"   registry at {address}")

    service = VehiclePassportService(settings=settings, registry=registry)

    print("2) Recording lifecycle events for two vehicles ...")
    _record(service, "VIN-HONEST-0001", HONEST)
    _record(service, "VIN-ROLLBACK-002", TAMPERED)
    honest_count = registry.event_count(vehicle_id("VIN-HONEST-0001"))
    bad_count = registry.event_count(vehicle_id("VIN-ROLLBACK-002"))
    print(f"   recorded {honest_count} + {bad_count} events on-chain")

    print("3) Assessing the honest vehicle:")
    honest = service.assess("VIN-HONEST-0001")
    print(f"   risk score {honest['risk_score']:.2f} -> suspicious: {honest['is_suspicious']}")
    print(f"   red flags: {honest['red_flags'] or 'none'}")

    print("4) Assessing the vehicle with a rolled-back odometer:")
    bad = service.assess("VIN-ROLLBACK-002")
    print(f"   risk score {bad['risk_score']:.2f} -> suspicious: {bad['is_suspicious']}")
    for flag in bad["red_flags"]:
        print(f"      - {flag}")

    print("5) Why the model finds this vehicle unlike an honest car")
    print("   (per-vehicle signals, in standard deviations from the honest average):")
    for name, z in bad["model_factors"]:
        print(f"      {name}: {z:+.1f} SD")


def main() -> None:
    parser = argparse.ArgumentParser(description="VehiclePassport CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="deploy, record events, and assess tampering risk")
    args = parser.parse_args()
    if args.command == "demo":
        demo()


if __name__ == "__main__":
    main()
