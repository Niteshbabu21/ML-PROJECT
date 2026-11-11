#!/usr/bin/env python3
"""audit_risk.py — risk-engine audit: config weights sum to 100, scores
stay within 0–100 and categories match the score bands over a broad
synthetic sweep (including missing/unknown values), and each factor's
reported score never exceeds its configured maximum.
Run: python audit_risk.py   (from backend/)
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND / "services"))
import risk_engine  # noqa: E402

cfg = json.loads((BACKEND / "config" / "risk_config.json").read_text())

# 1. Weights: factor maxima from the live engine's factor definitions.
BASE = {"POSTED_BY": "Owner", "UNDER_CONSTRUCTION": 0, "RERA": 1,
        "BHK_NO.": 3, "BHK_OR_RK": "BHK", "SQUARE_FT": 1200.0, "RESALE": 0,
        "CITY": "Bangalore", "LOCALITY": "Koramangala",
        "LATITUDE": 12.935, "LONGITUDE": 77.624,
        "SQUARE_FT_PER_BHK": 400.0, "LOG_SQUARE_FT": 7.09,
        "DIST_TO_CITY_CENTROID": 3.2, "CITY_FREQ": 3298.0,
        "LOCALITY_FREQ": 450.0, "SQFT_BAND": "M", "BHK_CONFIG": "3BHK",
        "GEO_CLUSTER": "C04", "LAT_LON_INTERACTION": 1003.4}
probe = risk_engine.assess_risk(BASE, 80.0)
total_max = sum(f["max_score"] for f in probe["factors"])
print(f"[{'PASS' if total_max == 100 else 'FAIL'}] factor maxima sum to 100 "
      f"(got {total_max})")
assert total_max == 100

# 2. Sweep: vary the risk-driving fields incl. missing values.
fails = 0
runs = 0
categories_seen = set()
for uc, rera, resale, lf, sqft, bhk in itertools.product(
        [0, 1, None], [0, 1, None], [0, 1, None],
        [0.0, 5.0, 50.0, 500.0], [300.0, 1200.0, 9000.0, 30000.0],
        [1, 3, 9]):
    feats = dict(BASE, **{"UNDER_CONSTRUCTION": uc, "RERA": rera,
                          "RESALE": resale, "LOCALITY_FREQ": lf,
                          "SQUARE_FT": sqft, "BHK_NO.": bhk})
    for price in [None, 25.0, 80.0, 500.0]:
        out = risk_engine.assess_risk(feats, price)
        runs += 1
        categories_seen.add(out["category"])
        score = out["overall_score"]
        band = "LOW" if score < 30 else "MEDIUM" if score < 60 else "HIGH"
        if not (0.0 <= score <= 100.0) or band != out["category"]:
            fails += 1
            print("  FAIL", uc, rera, resale, lf, sqft, bhk, price,
                  score, out["category"])
        for f in out["factors"]:
            if f["score"] > f["max_score"] + 1e-9 or f["score"] < -1e-9:
                fails += 1
                print("  FACTOR OUT OF RANGE", f["id"], f["score"], f["max_score"])
print(f"[{'PASS' if fails == 0 else 'FAIL'}] {runs} synthetic assessments: "
      f"scores within 0-100, categories consistent, factors within maxima")
print(f"       categories exercised: {sorted(categories_seen)}")

# 3. Missing-everything case must not crash and must warn.
empty = risk_engine.assess_risk({}, None)
print(f"[{'PASS' if empty['warnings'] and 0 <= empty['overall_score'] <= 100 else 'FAIL'}] "
      f"empty input handled: score {empty['overall_score']}, "
      f"{len(empty['warnings'])} warnings, category {empty['category']}")
print("AUDIT RISK: done")
