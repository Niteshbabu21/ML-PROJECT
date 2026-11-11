#!/usr/bin/env python3
"""audit_ml.py — independent ML audit of the packaged model.

Recomputes, from the packaged artifact only:
  1. Held-out test metrics on the training stage's grouped test
     partition and compares them with model_metadata.json.
  2. Geographic generalisation: metrics on rows whose LOCALITY never
     appears in the data the packaged model was fitted on
     (train+validation of the grouped split).
  3. Target-leakage checks on the feature schema (no target-derived
     feature; engineered features' origins are prediction-time /
     train-fitted statistics only).
  4. Feature-order robustness: shuffled dict key order must not change
     predictions; the schema order must match the pipeline's expected
     feature list.
Run: python audit_ml.py   (from backend/)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND / "ml"))
sys.path.insert(0, str(BACKEND.parent / "training_stage" / "ml"))

import predict as packaged  # noqa: E402
from train import FEATURES, TARGET, load_data, make_splits  # noqa: E402

RESULTS = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def metrics(y_true, y_pred) -> dict:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "r2": float(r2_score(y_true, y_pred)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mape_pct": float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100),
        "n": int(len(y_true)),
    }


def main() -> int:
    df = load_data()
    train, valid, test, _groups = make_splits(df)
    fitted_on = train + valid if isinstance(train, list) else None
    import pandas as pd
    fitted_on = pd.concat([train, valid], ignore_index=True)

    meta = json.loads((BACKEND / "ml" / "model_metadata.json").read_text())
    schema = json.loads((BACKEND / "ml" / "feature_schema.json").read_text())

    # --- 1. held-out test metrics vs metadata -----------------------------
    records = test[FEATURES].to_dict("records")
    preds = packaged.predict_properties(records)
    m = metrics(test[TARGET].to_numpy(), preds)
    recorded = meta["metrics"]["test"]
    check("test partition size matches metadata",
          m["n"] == recorded["n"], f"n={m['n']} vs {recorded['n']}")
    check("test R2 reproduces metadata",
          abs(m["r2"] - recorded["r2"]) < 0.002,
          f"recomputed {m['r2']:.4f} vs recorded {recorded['r2']}")
    check("test RMSE reproduces metadata",
          abs(m["rmse"] - recorded["rmse_lacs"]) < 0.05,
          f"recomputed ₹{m['rmse']:.2f}L vs recorded ₹{recorded['rmse_lacs']}L")
    check("test MAE reproduces metadata",
          abs(m["mae"] - recorded["mae_lacs"]) < 0.05,
          f"recomputed ₹{m['mae']:.2f}L vs recorded ₹{recorded['mae_lacs']}L")

    # --- 2. geographic generalisation --------------------------------------
    fitted_localities = set(fitted_on["LOCALITY"].unique())
    geo = df[~df["LOCALITY"].isin(fitted_localities)]
    geo_m = metrics(geo[TARGET].to_numpy(),
                    packaged.predict_properties(geo[FEATURES].to_dict("records")))
    print(f"       fitted-on localities: {len(fitted_localities)}; "
          f"unseen-locality rows in full data: {geo_m['n']}")
    check("geographic holdout exists and is material",
          geo_m["n"] >= 100, f"n={geo_m['n']} unseen-locality rows")
    print(f"       geographic generalisation: R2 {geo_m['r2']:.4f}, "
          f"MAE ₹{geo_m['mae']:.2f}L, RMSE ₹{geo_m['rmse']:.2f}L "
          f"(vs grouped-test R2 {m['r2']:.4f})")

    # --- 3. leakage ----------------------------------------------------------
    names = [f["name"] for f in schema["features"]]
    check("no price_per_sqft / target-derived feature in schema",
          not any("PRICE" in n.upper() and "SQFT" in n.upper() for n in names)
          and "TARGET" not in names)
    origins = {f["name"]: f.get("origin", "") for f in schema["features"]}
    suspicious = [n for n, o in origins.items()
                  if "target" in o.lower() and "log1p" not in o.lower()]
    check("feature origins declare no target usage", not suspicious,
          f"suspicious: {suspicious}")
    check("schema feature order == training FEATURES order",
          schema["feature_order"] == FEATURES)

    # --- 4. order robustness ---------------------------------------------------
    sample = records[:50]
    base = np.asarray(packaged.predict_properties(sample), dtype=float)
    shuffled = [dict(reversed(list(r.items()))) for r in sample]
    alt = np.asarray(packaged.predict_properties(shuffled), dtype=float)
    check("predictions invariant to input dict key order",
          bool(np.allclose(base, alt, atol=1e-9)),
          f"max diff {float(np.max(np.abs(base - alt))):.2e}")

    print()
    failed = [r for r in RESULTS if not r[1]]
    print(f"AUDIT ML: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
