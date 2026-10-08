"""Honest evaluation of the tamper detector.

Unlike a text classifier trained on a few templates, the detector learns from
vehicle histories that are each an *independent* random draw, and its features
(rollback size, maximum km/day, service gaps) are engineered to capture the
fraud directly. So a high score is legitimate rather than memorisation — but we
prove it rather than assert it:

* **5-fold cross-validation** (mean ± std) shows the score is stable, not a lucky
  split;
* an **independently generated test set** (a different seed) measures
  generalisation to histories never seen in training;
* the **train/test gap** is reported — a large gap would signal overfitting, a
  low score on both would signal underfitting.

Run with ``python -m vehiclepassport.evaluation``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import cross_val_score

from .features import feature_vector
from .generate import make_dataset


@dataclass
class EvalReport:
    cv_f1_mean: float
    cv_f1_std: float
    train_f1: float
    test_f1: float
    test_accuracy: float
    train_test_gap: float
    n_train: int
    n_test: int


def _matrix(histories):
    return np.array([feature_vector(h) for h in histories])


def evaluate(train_seed: int = 3, test_seed: int = 999, n: int = 800) -> EvalReport:
    h_tr, y_tr = make_dataset(n=n, seed=train_seed)
    h_te, y_te = make_dataset(n=n // 2, seed=test_seed)  # independent draw
    x_tr, y_tr = _matrix(h_tr), np.array(y_tr)
    x_te, y_te = _matrix(h_te), np.array(y_te)

    model = RandomForestClassifier(
        n_estimators=200, max_depth=8, random_state=0, class_weight="balanced"
    )
    cv = cross_val_score(model, x_tr, y_tr, cv=5, scoring="f1")
    model.fit(x_tr, y_tr)
    train_f1 = f1_score(y_tr, model.predict(x_tr))
    test_pred = model.predict(x_te)
    test_f1 = f1_score(y_te, test_pred)
    return EvalReport(
        cv_f1_mean=round(float(cv.mean()), 3),
        cv_f1_std=round(float(cv.std()), 3),
        train_f1=round(float(train_f1), 3),
        test_f1=round(float(test_f1), 3),
        test_accuracy=round(float(accuracy_score(y_te, test_pred)), 3),
        train_test_gap=round(float(train_f1 - test_f1), 3),
        n_train=len(h_tr),
        n_test=len(h_te),
    )


if __name__ == "__main__":
    r = evaluate()
    print("Tamper-detector evaluation (independent test set, different seed):")
    print(f"  train / test size   : {r.n_train} / {r.n_test}")
    print(f"  5-fold CV F1        : {r.cv_f1_mean} +/- {r.cv_f1_std}")
    print(f"  independent test F1 : {r.test_f1}")
    print(f"  independent test acc: {r.test_accuracy}")
    print(f"  train-test gap      : {r.train_test_gap}  (small = not overfit)")
