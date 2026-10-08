# ADR 0002: A model and rules, with rules that override

## Status

Accepted.

## Context

We need to decide whether a vehicle's history looks tampered with. Two kinds of
signal exist:

- **Obvious, certain signals.** An odometer that drops is a rollback. A gain of
  120,000 km in five days is physically impossible for a private car. These are
  not probabilities; they are facts in the data.
- **Subtle, combined signals.** Servicing slightly too irregular, mileage
  variance a little high, an owner count out of step with the age. No single one
  is damning, but together they raise suspicion.

A pure rules engine misses the subtle cases. A pure machine-learning model can,
in principle, assign a low probability to a history that contains a blatant
rollback — which would be indefensible to a user ("the car's odometer visibly
dropped, but the model said 0.3, so we passed it").

## Decision

Use **both**, and let the rules win when they fire:

- A **RandomForest**, trained on labelled honest and tampered histories, produces
  a risk score from engineered features. It provides sensitivity to the subtle,
  combined cases.
- **Deterministic red flags** detect rollbacks and implausible jumps directly.
- A **hard red flag marks the vehicle suspicious regardless of the model score.**
  The model can raise suspicion; it can never lower it below an obvious fact.

## Consequences

- **No obvious fraud slips through.** A rollback is always caught, whatever the
  model thinks.
- **Subtle fraud is still caught.** The model adds coverage the rules alone would
  miss.
- **Explainable.** The report carries both the score and the plain-language flags,
  so a verdict can always be justified.
- **Testable separately.** The rules are tested on hand-built histories; the model
  is tested on held-out labelled data. Each stands on its own.
- **Trade-off.** Two mechanisms are more code than one. The combination is what
  gives both guaranteed coverage of the obvious and sensitivity to the subtle.
