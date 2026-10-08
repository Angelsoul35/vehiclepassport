from __future__ import annotations

from vehiclepassport.events import ODOMETER_EVENTS, EventType


def test_event_values_match_contract_enum():
    # The integer values must match the Solidity enum order exactly.
    assert EventType.SERVICE == 0
    assert EventType.INSPECTION == 1
    assert EventType.PART_REPLACEMENT == 2
    assert EventType.OWNERSHIP_TRANSFER == 3
    assert EventType.ODOMETER_READING == 4
    assert EventType.INCIDENT == 5


def test_odometer_events_exclude_transfers_and_incidents():
    assert EventType.SERVICE in ODOMETER_EVENTS
    assert EventType.ODOMETER_READING in ODOMETER_EVENTS
    assert EventType.OWNERSHIP_TRANSFER not in ODOMETER_EVENTS
    assert EventType.INCIDENT not in ODOMETER_EVENTS


def test_labels():
    assert EventType.PART_REPLACEMENT.label == "part_replacement"
