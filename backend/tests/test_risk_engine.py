#!/usr/bin/env python3
"""test_risk_engine.py — validation of the prototype risk methodology.

The three scenario cases are SYNTHETIC by design (documented below) —
they test the scoring methodology, not real properties:

  LOW case (expected 7.7 -> LOW):
    RERA recorded (0) + complete property (0) + first sale (0) +
    established locality, freq 450 (0) + complete information (0) +
    consistent attributes (0) + uncertainty for the ₹75-150L band
    (calibrated APE p80 30.3% -> 7.7) = 7.7.

  MEDIUM case (expected 42.9 -> MEDIUM):
    under construction (20) + resale (5) + thin locality evidence,
    freq 12 (10) + one missing field (2) + uncertainty ₹40-75L band
    (APE p80 27.8% -> 5.9) = 42.9. RERA recorded, attributes consistent.

  HIGH case (expected 89.5 -> HIGH):
    RERA not recorded in listing data (20) + under construction (20) +
    resale (5) + unseen locality, freq 0 (15) + three missing fields
    (6) + flagged attributes: 30,000 sq ft (4) + 9 BHK (3) + 3,333
    sq ft/BHK (5) = 12 + uncertainty >₹400L band (APE p80 35.3% ->
    11.5) = 89.5.

Guard tests:
  * Missing RERA scores the midpoint (10) with an 'unknown' warning —
    never the not-recorded score (20).
  * READY_TO_MOVE consistent with UNDER_CONSTRUCTION changes nothing
    (no double counting); a contradiction adds exactly the consistency
    points (5).
  * Without a predicted price, uncertainty is 'not_evaluated' and the
    score is rescaled with an explicit note.
  * Config weights sum to 100; output is JSON-serialisable; scores are
    bounded to [0, 100].
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "services"))

from risk_engine import assess_risk  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        FAILURES.append(name)


BASE = {"POSTED_BY": "Owner", "UNDER_CONSTRUCTION": 0, "RERA": 1,
        "BHK_NO.": 3, "BHK_OR_RK": "BHK", "SQUARE_FT": 1200.0, "RESALE": 0,
        "CITY": "Bangalore", "LOCALITY": "Koramangala",
        "LATITUDE": 12.935, "LONGITUDE": 77.624,
        "SQUARE_FT_PER_BHK": 400.0, "LOG_SQUARE_FT": 7.09,
        "DIST_TO_CITY_CENTROID": 3.2, "CITY_FREQ": 3298.0,
        "LOCALITY_FREQ": 450.0, "SQFT_BAND": "M", "BHK_CONFIG": "3BHK",
        "GEO_CLUSTER": "C04", "LAT_LON_INTERACTION": 1003.4}


def factor(result: dict, fid: str) -> dict:
    return next(f for f in result["factors"] if f["id"] == fid)


def main() -> None:
    cfg = json.loads((HERE.parent / "config" / "risk_config.json").read_text())
    total_weight = sum(cfg[k]["weight"] for k in
                       ["rera_status", "construction_status", "resale_status",
                        "location_evidence", "information_completeness",
                        "attribute_consistency", "prediction_uncertainty"])
    check("config weights sum to 100", total_weight == 100,
          f"sum={total_weight}")

    low = assess_risk(BASE, predicted_price_lacs=85.0)
    json.dumps(low)
    check("LOW scenario", low["category"] == "LOW"
          and abs(low["overall_score"] - 7.7) < 0.15,
          f"score {low['overall_score']} ({low['category']})")
    check("LOW domains separated",
          low["domains"]["regulatory_construction"]["score"] == 0
          and low["domains"]["data_quality"]["score"] == 0
          and low["domains"]["model_uncertainty"]["score"] > 0)

    med_features = dict(BASE, UNDER_CONSTRUCTION=1, RESALE=1,
                        LOCALITY_FREQ=12.0, DIST_TO_CITY_CENTROID=None,
                        SQUARE_FT=2600.0, **{"BHK_NO.": 2},
                        SQUARE_FT_PER_BHK=1300.0)
    med = assess_risk(med_features, predicted_price_lacs=45.0)
    check("MEDIUM scenario", med["category"] == "MEDIUM"
          and abs(med["overall_score"] - 42.9) < 0.15,
          f"score {med['overall_score']} ({med['category']})")

    high_features = dict(BASE, RERA=0, UNDER_CONSTRUCTION=1, RESALE=1,
                         LOCALITY_FREQ=0.0, SQUARE_FT=30000.0,
                         **{"BHK_NO.": 9}, SQUARE_FT_PER_BHK=3333.3,
                         CITY="Mumbai", LOCALITY="Unseen Nagar")
    for k in ["CITY_FREQ", "GEO_CLUSTER", "LAT_LON_INTERACTION"]:
        high_features.pop(k)
    high = assess_risk(high_features, predicted_price_lacs=500.0)
    check("HIGH scenario", high["category"] == "HIGH"
          and abs(high["overall_score"] - 89.5) < 0.15,
          f"score {high['overall_score']} ({high['category']})")
    check("HIGH has verification actions",
          len(high["recommended_actions"]) >= 4,
          f"{len(high['recommended_actions'])} actions")
    check("scores bounded", 0 <= high["overall_score"] <= 100)

    unknown = dict(BASE); unknown.pop("RERA")
    r = assess_risk(unknown, predicted_price_lacs=85.0)
    fr = factor(r, "rera_status")
    check("missing RERA = midpoint + warning, not non-compliance",
          fr["score"] == 10 and fr["status"] == "unknown"
          and any("RERA" in w for w in r["warnings"]),
          f"rera score {fr['score']}")

    consistent = assess_risk(dict(BASE, READY_TO_MOVE=1),
                             predicted_price_lacs=85.0)
    check("READY_TO_MOVE consistent: no double counting",
          consistent["overall_score"] == low["overall_score"],
          f"{consistent['overall_score']} vs {low['overall_score']}")
    contra = assess_risk(dict(BASE, READY_TO_MOVE=0),
                         predicted_price_lacs=85.0)
    fc = factor(contra, "attribute_consistency")
    check("READY_TO_MOVE contradiction: +5 consistency only",
          fc["score"] == 5 and contra["overall_score"]
          == round(low["overall_score"] + 5, 1),
          f"consistency {fc['score']}, overall {contra['overall_score']}")

    noprice = assess_risk(BASE)
    fu = factor(noprice, "prediction_uncertainty")
    check("no price: uncertainty not evaluated + rescale noted",
          fu["status"] == "not_evaluated"
          and "rescaled" in noprice["score_basis"]
          and any("uncertainty" in w for w in noprice["warnings"]))

    print("\nSample narrative (MEDIUM case):")
    print(med["narrative"])
    print("\n" + ("ALL RISK TESTS PASSED" if not FAILURES
                  else f"FAILURES: {FAILURES}"))
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
