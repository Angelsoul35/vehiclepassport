# ADR 0001: An append-only, faithful ledger

## Status

Accepted.

## Context

The point of putting a vehicle's history on a chain is to make it
tamper-evident: no one can quietly rewrite the past after a sale. But there is a
design trap. The most tempting "safety" feature — making the contract reject a
reading lower than the previous one — would defeat the whole purpose.

An odometer that drops is exactly the fraud we want to catch. If the contract
refused to record it, the rollback would just happen off-chain (or never be
recorded), and the on-chain history would look perfectly clean while the car was
misrepresented.

## Decision

Make the contract **append-only and faithful**:

- events are only ever added, never edited or removed;
- the contract records whatever an authorised recorder submits, including a
  decreasing odometer;
- judgement about what is suspicious lives **off-chain**, in the detector.

The chain's responsibility is the **integrity of the record** (it is complete,
ordered, and unaltered), not the **plausibility of the values**.

## Consequences

- **Fraud is preserved, not hidden.** A rollback stays in the record for the
  detector to find and for anyone to audit.
- **Clear separation of concerns.** The contract guarantees integrity; the model
  and rules provide judgement. Each can evolve without the other.
- **Simple, cheap contract.** No branching logic to validate values, so the
  contract is small and its gas cost is predictable.
- **Trade-off.** The ledger can contain "wrong" values. That is intentional: the
  value of the system is that those wrong values are now permanent evidence
  rather than a forgery in a paper service book.
