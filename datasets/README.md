# Real used-car data

`used_cars.jsonl` is a real sample used to benchmark the tamper detector against
real-world vehicle statistics instead of a hand-built generator. Each line is one
real listing, as JSON.

## Source

- **Dataset:** [`imbalet/used_cars`](https://huggingface.co/datasets/imbalet/used_cars)
  on Hugging Face — 432,227 real used-car listings.
- **Licence:** MIT (per the dataset card), the same licence as this project, so a
  small real sample is vendored here for reproducible, offline benchmarking.
- **This file:** 8,000 real records (of the 432,227), slimmed to the columns the
  benchmark uses — `owners`, `year`, `price`, `mileage` (km), `mark`, `model`,
  `region`, `engine`, `transmission` — and filtered to plausible rows (a valid
  year 1990–2023, mileage 1,000–1,000,000 km, 1–6 owners, and a lifetime pace
  under 80,000 km/year). About 1.6 MB. Nothing here is synthesised; every record
  is a verbatim real listing.

## Methodology: real distributions + injected fraud

There is **no public dataset of labelled real odometer-rollback histories** — when
a car is sold with a rolled-back odometer, the fraud is, by design, not labelled.
So the benchmark follows the standard fraud-detection methodology used whenever
labelled fraud is scarce: a **real legitimate population plus injected fraud**.

- The **legitimate** class is built from these real cars. Each car's real `year`,
  `mileage` and `owners` fix a plausible, monotonically rising odometer history
  (a constant-ish pace to the real mileage over the real age, with mild
  measurement noise). The feature distributions the detector sees — mileage, age,
  km/year, owner count — are therefore those of **real vehicles**.
- The **fraud** class takes a *disjoint* set of the same real cars and injects an
  **odometer rollback** (a later reading set strictly below an earlier one — the
  exact signature of odometer fraud) or an **implausible mileage jump** (a large
  distance over a short window, the signature of a cloned cluster).

Because the legitimate and fraud cars are disjoint and each history comes from a
single distinct real listing, no vehicle appears in both classes, and the
train/test and cross-validation splits are over whole histories. This is stated
plainly in the project README and the study guide; it is the transparent,
standard way to validate a detector when real labelled fraud is unavailable.

The code lives in `vehiclepassport/real_data.py` (fetch, load, build histories)
and `vehiclepassport/real_benchmark.py` (the benchmark itself).

## Regenerating

The vendored subset is produced by the project's own fetch function (urllib with
retries, hitting the public Hugging Face datasets-server rows API — no auth):

```bash
python -c "from vehiclepassport.real_data import fetch_used_cars, save_real_cars, _DEFAULT_VENDORED; \
save_real_cars(fetch_used_cars(8000), _DEFAULT_VENDORED)"
```

Then run the benchmark:

```bash
python -m vehiclepassport.real_benchmark
```
