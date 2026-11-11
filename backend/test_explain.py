#!/usr/bin/env python3
"""test_explain.py — fresh-process validation of the SHAP module.

For five representative held-out records (incl. a Bengaluru property):
  * explain_property returns a JSON-serialisable dict;
  * all 20 source features are present with correct names;
  * SHAP additivity holds: base + Σ contributions == model output
    within the configured tolerance (log space);
  * the explained price equals predict_property's price;
  * the base value is identical across records (same explainer);
  * a waterfall plot is produced for the Bengaluru record;
  * an invalid record raises ValueError.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "ml"))
sys.path.insert(0, str(HERE.parent / "training_stage" / "ml"))

from predict import predict_property  # noqa: E402
from shap_service import explain_property  # noqa: E402
from shap_visualizations import waterfall_for  # noqa: E402
from train import FEATURES, TARGET, load_data, make_splits  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        FAILURES.append(name)


def main() -> None:
    df = load_data()
    _tr, _va, test, _ = make_splits(df)
    picks = []
    blr = test[test["CITY"] == "Bangalore"]
    picks.append(("Bengaluru record", blr.iloc[len(blr) // 2]))
    picks.append(("cheapest test record", test.loc[test[TARGET].idxmin()]))
    picks.append(("most expensive test record", test.loc[test[TARGET].idxmax()]))
    picks.append(("median-price record",
                  test.iloc[(test[TARGET] - test[TARGET].median()).abs().argmin()]))
    mum = test[test["CITY"] == "Mumbai"]
    picks.append(("Mumbai record", mum.iloc[0]))

    base_values = set()
    for label, row in picks:
        rec = {f: (row[f].item() if hasattr(row[f], "item") else row[f])
               for f in FEATURES}
        res = explain_property(rec)
        json.dumps(res)  # must be JSON-serialisable
        names = {c["feature"] for c in res["contributions"]}
        check(f"{label}: 20 features, JSON-serialisable",
              names == set(FEATURES) and len(res["contributions"]) == 20)
        check(f"{label}: additivity verified",
              res["additivity"]["verified"]
              and res["additivity"]["abs_error"] < 1e-4,
              f"error {res['additivity']['abs_error']:.2e}")
        check(f"{label}: price matches predict_property",
              abs(res["predicted_price_lacs"] - predict_property(rec)) < 0.011,
              f"₹{res['predicted_price_lacs']:,.2f}L vs actual "
              f"₹{float(row[TARGET]):,.2f}L")
        check(f"{label}: top-5 influential present",
              len(res["top_influential"]) == 5
              and len(res["top_positive"]) >= 1)
        base_values.add(res["base_value_log"])
        if label == "Bengaluru record":
            print("\n--- Bengaluru example (computed, not hardcoded) ---")
            print(res["explanation"])
            print("top influential:",
                  [(c["feature"], c["shap_log"]) for c in res["top_influential"]])
            wf = waterfall_for(rec, HERE / "ml" / "visualizations"
                               / "shap_waterfall_example.png")
            check("waterfall plot written", wf.exists() and wf.stat().st_size > 5000,
                  str(wf))
    check("base value identical across records", len(base_values) == 1,
          f"base {base_values}")

    bad = dict(picks[0][1].to_dict(), SQUARE_FT=0)
    bad = {f: (bad[f].item() if hasattr(bad[f], "item") else bad[f])
           for f in FEATURES}
    try:
        explain_property(bad)
        check("invalid input rejected", False, "no error")
    except ValueError as exc:
        check("invalid input rejected", True, str(exc)[:50])

    print("\n" + ("ALL EXPLAIN TESTS PASSED" if not FAILURES
                  else f"FAILURES: {FAILURES}"))
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
