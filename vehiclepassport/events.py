"""The vehicle event vocabulary, mirrored exactly from the Solidity enum."""

from __future__ import annotations

from enum import IntEnum


class EventType(IntEnum):
    """Kinds of lifecycle event. The integer values match VehicleRegistry.sol."""

    SERVICE = 0
    INSPECTION = 1
    PART_REPLACEMENT = 2
    OWNERSHIP_TRANSFER = 3
    ODOMETER_READING = 4
    INCIDENT = 5

    @property
    def label(self) -> str:
        return self.name.lower()


# Events whose odometer value is a trustworthy reading of the vehicle's mileage.
# Ownership transfers and incidents may carry the last known value but are not
# themselves odometer measurements, so they do not anchor the mileage timeline.
ODOMETER_EVENTS = frozenset(
    {
        EventType.SERVICE,
        EventType.INSPECTION,
        EventType.PART_REPLACEMENT,
        EventType.ODOMETER_READING,
    }
)
