#!/usr/bin/env python3
"""test_predict.py — fresh-process verification of the packaged model.

Run with a clean interpreter (no prior imports of the training code in
the model path): the packaged artifact is loaded ONLY through
backend/ml/predict.py, exactly as a Flask service would load it.

Checks:
  1. Artifact loads; metadata/schema are readable.
  2. Representative real records (from the held-out test partition):
     predict_property output equals a direct prep+model prediction on
     the same rows — the validation layer must not alter values.
  3. A 1,000-row test subset through predict_property matches direct
     artifact predictions to <1e-6 ₹ lakh per row.
  4. Unseen categorical values are accepted and return finite prices.
  5. Invalid inputs raise ValueError (zero/negative area, BHK 0/25/2.5,
     missing feature, out-of-India coordinates, bad binary flag,
     non-numeric area); DIST_TO_CITY_CENTROID=None is accepted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "ml"))
sys.path.insert(0, str(HERE.parent / "training_stage" / "ml"))

import joblib  # noqa: E402
import pandas as pd  # noqa: E402
from predict import model_info, predict_properties, predict_property  # noqa: E402
from train import FEATURES, TARGET, load_data, make_splits  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        FAILURES.append(name)


def direct_predict(frame: pd.DataFrame) -> np.ndarray:
    art = joblib.load(HERE / "ml" / "model.pkl")
    raw = np.asarray(art["model"].predict(art["prep"].transform(frame)),
                     dtype=float)
    return np.expm1(np.clip(raw, 0, art["log_clip_hi"]))


def main() -> None:
    info = model_info()
    check("metadata loads", info["model"]["name"].startswith("XGBoost"),
          info["model"]["name"])

    df = load_data()
    _tr, _va, test, _ = make_splits(df)
    sample = test.head(6)
    records = [{f: (row[f].item() if hasattr(row[f], "item") else row[f])
                for f in FEATURES} for _, row in sample.iterrows()]
    # 2. representative records: packaged function vs direct artifact
    packaged = predict_properties(records)
    direct = direct_predict(sample[FEATURES])
    diffs = [abs(p - round(float(d), 2)) for p, d in zip(packaged, direct)]
    check("representative records match direct model",
          max(diffs) < 1e-9, f"max diff {max(diffs):.2e} ₹L; "
          f"preds {[round(p, 1) for p in packaged]} vs actual "
          f"{[round(float(a), 1) for a in sample[TARGET]]}")

    # 3. 1,000-row subset equality through the full validation path
    sub = test.head(1000)
    recs = [{f: (row[f].item() if hasattr(row[f], "item") else row[f])
             for f in FEATURES} for _, row in sub.iterrows()]
    pk = np.array(predict_properties(recs))
    di = direct_predict(sub[FEATURES])
    md = float(np.max(np.abs(pk - np.round(di, 2))))
    check("1,000-row packaged-vs-direct equality", md < 1e-6,
          f"max abs diff {md:.2e} ₹L")

    base = dict(records[0])
    # 4. unseen categories
    unseen = dict(base, CITY="Atlantis City", LOCALITY="Nowhere Nagar",
                  POSTED_BY="Agent")
    try:
        p = predict_property(unseen)
        check("unseen categorical values accepted",
              np.isfinite(p) and p > 0, f"prediction ₹{p:.2f}L")
    except Exception as exc:
        check("unseen categorical values accepted", False, str(exc))

    # 5. invalid inputs
    invalid_cases = {
        "SQUARE_FT = 0": dict(base, SQUARE_FT=0),
        "SQUARE_FT = -50": dict(base, SQUARE_FT=-50),
        "SQUARE_FT = 'abc'": dict(base, SQUARE_FT="abc"),
        "BHK_NO. = 0": dict(base, **{"BHK_NO.": 0}),
        "BHK_NO. = 25": dict(base, **{"BHK_NO.": 25}),
        "BHK_NO. = 2.5": dict(base, **{"BHK_NO.": 2.5}),
        "LATITUDE = 95": dict(base, LATITUDE=95.0),
        "LONGITUDE = 10": dict(base, LONGITUDE=10.0),
        "RESALE = 2": dict(base, RESALE=2),
    }
    missing = dict(base); missing.pop("LOCALITY")
    invalid_cases["missing LOCALITY"] = missing
    for name, rec in invalid_cases.items():
        try:
            predict_property(rec)
            check(f"invalid rejected: {name}", False, "no error raised")
        except ValueError as exc:
            check(f"invalid rejected: {name}", True, str(exc)[:60])
        except Exception as exc:
            check(f"invalid rejected: {name}", False,
                  f"wrong exception {type(exc).__name__}: {exc}")
    try:
        p = predict_property(dict(base, DIST_TO_CITY_CENTROID=None))
        check("DIST_TO_CITY_CENTROID=None accepted", np.isfinite(p),
              f"prediction ₹{p:.2f}L")
    except Exception as exc:
        check("DIST_TO_CITY_CENTROID=None accepted", False, str(exc))

    print("\n" + ("ALL TESTS PASSED" if not FAILURES
                  else f"FAILURES: {FAILURES}"))
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
