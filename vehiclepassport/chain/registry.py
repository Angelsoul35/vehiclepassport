"""Registry clients: a Web3-backed client and an in-memory fake.

Both implement :class:`RegistryClient`, so the service can append and read a
vehicle's lifecycle against the real compiled contract (on Anvil or an in-memory
PyEVM node) or against an in-memory fake with the same behaviour. Vehicles are
identified by a bytes32 id (a hash of the VIN), so no VIN reaches the chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from eth_utils import keccak
from web3 import Web3
from web3.contract import Contract

from ..events import EventType
from .artifacts import contract_abi, contract_bytecode


def vehicle_id(vin: str) -> bytes:
    """Return the 32-byte on-chain id for a vehicle VIN."""
    return keccak(text=vin)


def record_hash(detail: str) -> bytes:
    """Digest of an off-chain record detail, anchored on-chain for tamper-evidence."""
    return keccak(text=detail)


@dataclass(frozen=True)
class EventRecord:
    event_type: EventType
    odometer_km: int
    timestamp: int
    data_hash: bytes
    recorder: str | None = None


@runtime_checkable
class RegistryClient(Protocol):
    @property
    def address(self) -> str: ...

    def record_event(
        self,
        vehicle: bytes,
        event_type: EventType,
        odometer_km: int,
        timestamp: int,
        data_hash: bytes,
    ) -> int: ...

    def event_count(self, vehicle: bytes) -> int: ...

    def history(self, vehicle: bytes) -> list[EventRecord]: ...

    def last_odometer(self, vehicle: bytes) -> int: ...


class InMemoryRegistryClient:
    """A dict-backed registry that mirrors the contract's append-only history."""

    def __init__(self) -> None:
        self._history: dict[bytes, list[EventRecord]] = {}
        self.total_events = 0

    @property
    def address(self) -> str:
        return "0x0000000000000000000000000000000000000000"

    def record_event(self, vehicle, event_type, odometer_km, timestamp, data_hash) -> int:
        if vehicle == bytes(32):
            raise ValueError("zero vehicle")
        events = self._history.setdefault(vehicle, [])
        index = len(events)
        events.append(
            EventRecord(
                event_type=EventType(event_type),
                odometer_km=int(odometer_km),
                timestamp=int(timestamp),
                data_hash=data_hash,
                recorder=self.address,
            )
        )
        self.total_events += 1
        return index

    def event_count(self, vehicle) -> int:
        return len(self._history.get(vehicle, []))

    def history(self, vehicle) -> list[EventRecord]:
        return list(self._history.get(vehicle, []))

    def last_odometer(self, vehicle) -> int:
        events = self._history.get(vehicle, [])
        return events[-1].odometer_km if events else 0


def deploy_registry(w3: Web3, deployer: str, private_key: str | None = None) -> str:
    deployer = Web3.to_checksum_address(deployer)
    factory = w3.eth.contract(abi=contract_abi(), bytecode=contract_bytecode())
    if private_key:
        tx = factory.constructor().build_transaction(
            {"from": deployer, "nonce": w3.eth.get_transaction_count(deployer)}
        )
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    else:
        tx_hash = factory.constructor().transact({"from": deployer})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt["contractAddress"]


class Web3RegistryClient:
    def __init__(
        self, w3: Web3, contract_address: str, account: str, private_key: str | None = None
    ) -> None:
        self._w3 = w3
        self._account = Web3.to_checksum_address(account)
        self._private_key = private_key
        self._contract: Contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address), abi=contract_abi()
        )

    @property
    def address(self) -> str:
        return self._contract.address

    def set_recorder(self, recorder: str, allowed: bool = True) -> None:
        self._send(
            self._contract.functions.setRecorder(Web3.to_checksum_address(recorder), allowed)
        )

    def _send(self, fn) -> None:
        if self._private_key:
            tx = fn.build_transaction(
                {"from": self._account, "nonce": self._w3.eth.get_transaction_count(self._account)}
            )
            signed = self._w3.eth.account.sign_transaction(tx, self._private_key)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        else:
            tx_hash = fn.transact({"from": self._account})
        self._w3.eth.wait_for_transaction_receipt(tx_hash)

    def record_event(self, vehicle, event_type, odometer_km, timestamp, data_hash) -> int:
        index = self.event_count(vehicle)
        self._send(
            self._contract.functions.recordEvent(
                vehicle, int(event_type), int(odometer_km), int(timestamp), data_hash
            )
        )
        return index

    def event_count(self, vehicle) -> int:
        return int(self._contract.functions.eventCount(vehicle).call())

    def history(self, vehicle) -> list[EventRecord]:
        count = self.event_count(vehicle)
        out: list[EventRecord] = []
        for i in range(count):
            etype, odo, ts, dhash, recorder = self._contract.functions.getEvent(vehicle, i).call()
            out.append(
                EventRecord(
                    event_type=EventType(int(etype)),
                    odometer_km=int(odo),
                    timestamp=int(ts),
                    data_hash=bytes(dhash),
                    recorder=recorder,
                )
            )
        return out

    def last_odometer(self, vehicle) -> int:
        return int(self._contract.functions.lastOdometer(vehicle).call())
