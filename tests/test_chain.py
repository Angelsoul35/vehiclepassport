from __future__ import annotations

import pytest
from eth_tester.exceptions import TransactionFailed
from web3.exceptions import ContractLogicError

from vehiclepassport.chain.registry import (
    InMemoryRegistryClient,
    Web3RegistryClient,
    deploy_registry,
    record_hash,
    vehicle_id,
)
from vehiclepassport.events import EventType

pytestmark = pytest.mark.chain

REVERT_ERRORS = (ContractLogicError, TransactionFailed)
BASE = 1_700_000_000


def test_record_and_read_history(chain_registry):
    vid = vehicle_id("VIN-1")
    chain_registry.record_event(vid, EventType.SERVICE, 10_000, BASE, record_hash("a"))
    chain_registry.record_event(vid, EventType.SERVICE, 25_000, BASE + 1000, record_hash("b"))

    assert chain_registry.event_count(vid) == 2
    assert chain_registry.last_odometer(vid) == 25_000

    history = chain_registry.history(vid)
    assert [e.odometer_km for e in history] == [10_000, 25_000]
    assert history[0].event_type is EventType.SERVICE
    assert history[1].data_hash == record_hash("b")


def test_contract_preserves_a_rollback(chain_registry):
    # The chain must NOT reject a decreasing odometer; that is the fraud we detect.
    vid = vehicle_id("VIN-2")
    chain_registry.record_event(vid, EventType.SERVICE, 80_000, BASE, record_hash("x"))
    chain_registry.record_event(vid, EventType.SERVICE, 20_000, BASE + 1000, record_hash("y"))
    assert [e.odometer_km for e in chain_registry.history(vid)] == [80_000, 20_000]


def test_non_recorder_cannot_record(w3):
    owner, outsider = w3.eth.accounts[0], w3.eth.accounts[1]
    address = deploy_registry(w3, owner)
    rogue = Web3RegistryClient(w3, address, outsider)
    with pytest.raises(REVERT_ERRORS):
        rogue.record_event(vehicle_id("VIN-3"), EventType.SERVICE, 1, BASE, record_hash("z"))


def test_operator_can_authorise_a_recorder(w3):
    owner, garage = w3.eth.accounts[0], w3.eth.accounts[1]
    address = deploy_registry(w3, owner)
    admin = Web3RegistryClient(w3, address, owner)
    admin.set_recorder(garage, True)

    garage_client = Web3RegistryClient(w3, address, garage)
    garage_client.record_event(
        vehicle_id("VIN-4"), EventType.SERVICE, 5_000, BASE, record_hash("w")
    )
    assert garage_client.event_count(vehicle_id("VIN-4")) == 1


def test_zero_vehicle_reverts(chain_registry):
    with pytest.raises(REVERT_ERRORS):
        chain_registry.record_event(bytes(32), EventType.SERVICE, 1, BASE, record_hash("q"))


def test_in_memory_matches_contract(chain_registry):
    vid = vehicle_id("VIN-5")
    mem = InMemoryRegistryClient()
    for odo, ts in [(1000, BASE), (9000, BASE + 500), (9000, BASE + 900)]:
        chain_registry.record_event(vid, EventType.SERVICE, odo, ts, record_hash(str(odo)))
        mem.record_event(vid, EventType.SERVICE, odo, ts, record_hash(str(odo)))

    assert chain_registry.event_count(vid) == mem.event_count(vid)
    assert chain_registry.last_odometer(vid) == mem.last_odometer(vid)
    assert [e.odometer_km for e in chain_registry.history(vid)] == [
        e.odometer_km for e in mem.history(vid)
    ]
