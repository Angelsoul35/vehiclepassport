# ADR 0003: Build the mileage timeline from measurement events only

## Status

Accepted.

## Context

A vehicle's history contains several kinds of event, and not all of them carry a
trustworthy mileage reading:

- A **service**, **inspection**, **part replacement**, or explicit **odometer
  reading** is taken by a party who actually looked at the odometer. The value is
  a genuine measurement.
- An **ownership transfer** or an **incident** may carry a last-known or
  self-reported value. A seller could enter any number at transfer — which is
  exactly where fraud happens.

If the analysis treated every event's odometer as a real reading, a fraudster
could anchor the mileage timeline with a value they simply made up at a transfer.

## Decision

Build the mileage timeline (and the rollback / jump / gap checks) from
**measurement events only** — the set `ODOMETER_EVENTS`. Ownership transfers and
incidents are still recorded and still counted (for example, the owner count is a
feature), but their odometer values do not anchor the mileage analysis.

## Consequences

- **The analysis rests on trustworthy points.** Rollbacks and jumps are measured
  between readings taken by someone who inspected the vehicle.
- **A fraudster cannot seed the timeline at a transfer.** A made-up value at a
  sale does not become a reference point for "normal".
- **Conservative by design.** When a value's provenance is weak, we exclude it
  from the mileage reasoning rather than trust it.
- **Trade-off.** For a genuinely new car bought at 0 km, the purchase's odometer
  is excluded, so the measured distance runs from the first service. This is the
  safe direction to err: the system never over-trusts a transfer value, and the
  first real reading is close behind.
