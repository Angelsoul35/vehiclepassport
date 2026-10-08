# ADR 0004: Authorised recorders and no VIN on-chain

## Status

Accepted.

## Context

Two questions had to be answered for the contract:

1. **Who may write?** If anyone could append events, the ledger would fill with
   junk and forgeries, and its integrity guarantee would be worthless.
2. **What may be written?** A chain is permanent and public. A VIN is personal
   data and, together with the history, can identify a car and its owner.

## Decision

- **Authorised recorders.** The contract keeps a set of addresses allowed to
  append events. Only the operator can change that set (`setRecorder`). In
  practice the recorders are the passport service, workshops, and inspection
  centres — the parties that legitimately observe a vehicle.
- **No VIN or personal data on-chain.** A vehicle is a `bytes32` id (the keccak
  hash of its VIN). The full record detail stays off-chain; only its keccak
  digest is stored, which proves the detail has not changed without revealing it.

## Consequences

- **Trustworthy writers.** Only known, authorised parties can add to a vehicle's
  history, so the record means something.
- **Privacy preserved.** The chain never reveals which car or whose. The
  id-to-VIN mapping lives off-chain, under the operator's control.
- **Tamper-evidence without disclosure.** Anchoring a digest lets anyone verify
  that an off-chain record is the one that was recorded, without publishing its
  contents.
- **Trade-off.** The operator holds real power: it decides who may record and it
  holds the id-to-VIN mapping. That is an explicit, auditable responsibility, and
  it keeps the sensitive data in a place that can enforce access control and
  deletion — which a public chain cannot.
- A production deployment would likely decentralise the recorder set (for
  example, a registry of accredited inspection bodies) rather than a single
  operator; the contract's `setRecorder` is the hook for that.
