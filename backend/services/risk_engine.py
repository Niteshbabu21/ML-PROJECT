#!/usr/bin/env python3
"""risk_engine.py — property-level risk assessment (academic prototype).

    from risk_engine import assess_risk
    result = assess_risk(property_features, predicted_price_lacs=85.0)

Input: the same model-ready feature mapping used by the valuation
model (any subset — missing fields are handled explicitly), plus the
predicted price if the uncertainty factor is to be scored. An optional
raw READY_TO_MOVE field is read ONLY for a consistency check against
UNDER_CONSTRUCTION; it is never scored itself.

Method (backend/config/risk_config.json, methodology 1.0.0-prototype):
seven weighted factors in three independent domains, summed to 0–100.
Bands: LOW 0–29, MEDIUM 30–59, HIGH 60–100.

Independence: this module does not import the ML model or SHAP. SHAP
explains the price; this module scores documented risk indicators.
The uncertainty factor is the only place the two meet, and it uses a
precomputed calibration table (held-out errors), never the model.

Scope: listing-data indicators only. Nothing here confirms ownership,
title, encumbrances or regulatory compliance.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping

_HERE = Path(__file__).resolve().parent
_CONFIG = json.loads((_HERE.parent / "config" / "risk_config.json").read_text())

import risk_explanation as _text  # noqa: E402  (same services package)

# The 20 model input fields (kept in sync with backend/ml/feature_schema.json).
MODEL_FEATURES = ["POSTED_BY", "UNDER_CONSTRUCTION", "RERA", "BHK_NO.",
                  "BHK_OR_RK", "SQUARE_FT", "RESALE", "CITY", "LOCALITY",
                  "LATITUDE", "LONGITUDE", "SQUARE_FT_PER_BHK",
                  "LOG_SQUARE_FT", "DIST_TO_CITY_CENTROID", "CITY_FREQ",
                  "LOCALITY_FREQ", "SQFT_BAND", "BHK_CONFIG", "GEO_CLUSTER",
                  "LAT_LON_INTERACTION"]


def _missing(features: Mapping, name: str) -> bool:
    if name not in features:
        return True
    v = features[name]
    return v is None or (isinstance(v, float) and math.isnan(v))


def _num(features: Mapping, name: str) -> float | None:
    if _missing(features, name):
        return None
    try:
        return float(features[name])
    except (TypeError, ValueError):
        return None


def _factor(fid: str, name: str, domain: str, score: float, max_score: float,
            status: str, detail: str) -> dict:
    t = _text.factor_text(fid, status)
    return {"id": fid, "name": name, "domain": domain,
            "score": round(float(score), 1), "max_score": float(max_score),
            "status": status, "detail": detail,
            "explanation": t["explanation"],
            "recommended_action": t["action"]}


def assess_risk(property_features: Mapping,
                predicted_price_lacs: float | None = None) -> dict:
    cfg = _CONFIG
    f = property_features
    warnings: list[str] = []
    factors: list[dict] = []

    # ---- Domain A: regulatory & construction ------------------------------
    rera_cfg = cfg["rera_status"]
    rera = _num(f, "RERA")
    if rera is None:
        s, status = rera_cfg["scores"]["unknown"], "unknown"
        warnings.append("RERA status unknown — scored at the neutral "
                        "midpoint, not as non-compliance.")
        detail = "RERA field missing."
    elif rera == 1:
        s, status = rera_cfg["scores"]["recorded"], "recorded"
        detail = "RERA recorded as registered in the listing data."
    else:
        s, status = rera_cfg["scores"]["not_recorded"], "not_recorded"
        detail = "RERA recorded as not registered in the listing data."
    factors.append(_factor("rera_status", "RERA status",
                           "regulatory_construction", s,
                           rera_cfg["weight"], status, detail))

    uc_cfg = cfg["construction_status"]
    uc = _num(f, "UNDER_CONSTRUCTION")
    if uc is None:
        s, status = uc_cfg["scores"]["unknown"], "unknown"
        warnings.append("Construction status unknown — scored at the "
                        "neutral midpoint.")
        detail = "UNDER_CONSTRUCTION field missing."
    elif uc == 1:
        s, status = uc_cfg["scores"]["under_construction"], "under_construction"
        detail = "Property is under construction."
    else:
        s, status = uc_cfg["scores"]["ready"], "ready"
        detail = "Property is complete (not under construction)."
    factors.append(_factor("construction_status", "Construction status",
                           "regulatory_construction", s,
                           uc_cfg["weight"], status, detail))

    rs_cfg = cfg["resale_status"]
    rs = _num(f, "RESALE")
    if rs is None:
        s, status = rs_cfg["scores"]["unknown"], "unknown"
        warnings.append("Resale status unknown — scored at half weight.")
        detail = "RESALE field missing."
    elif rs == 1:
        s, status = rs_cfg["scores"]["resale"], "resale"
        detail = "Listing is a resale."
    else:
        s, status = rs_cfg["scores"]["first_sale"], "first_sale"
        detail = "Listing is a first sale."
    factors.append(_factor("resale_status", "Resale status",
                           "regulatory_construction", s,
                           rs_cfg["weight"], status, detail))

    # ---- Domain B: data quality --------------------------------------------
    loc_cfg = cfg["location_evidence"]
    tiers = loc_cfg["tiers"]
    freq = _num(f, "LOCALITY_FREQ")
    city = f.get("CITY")
    if _missing(f, "LOCALITY") or city == "Other":
        s, status = tiers["city_other_or_locality_missing"], "unseen"
        detail = "City unidentified ('Other') or locality missing."
    elif freq is None:
        s, status = tiers["locality_freq_zero_unseen"], "unseen"
        warnings.append("LOCALITY_FREQ missing — locality treated as "
                        "unseen (conservative).")
        detail = "No locality frequency available."
    elif freq >= 100:
        s, status = tiers["locality_freq_at_least_100"], "established"
        detail = f"Locality appears {freq:.0f} times in the training data."
    elif freq >= 25:
        s, status = tiers["locality_freq_25_to_99"], "moderate"
        detail = f"Locality appears {freq:.0f} times in the training data."
    elif freq >= 1:
        s, status = tiers["locality_freq_1_to_24"], "thin"
        detail = f"Locality appears only {freq:.0f} time(s) in the training data."
    else:
        s, status = tiers["locality_freq_zero_unseen"], "unseen"
        detail = "Locality does not appear in the training data."
    factors.append(_factor("location_evidence", "Location evidence",
                           "data_quality", s, loc_cfg["weight"], status,
                           detail))

    comp_cfg = cfg["information_completeness"]
    excluded = set(comp_cfg["excluded_fields"])
    missing_fields = [name for name in MODEL_FEATURES
                      if name not in excluded and _missing(f, name)]
    s = min(comp_cfg["max_score"],
            comp_cfg["points_per_missing_field"] * len(missing_fields))
    status = ("complete" if not missing_fields else
              "partial" if len(missing_fields) <= 3 else "sparse")
    if missing_fields:
        warnings.append(f"Missing model input fields (imputed by the "
                        f"pipeline): {missing_fields}.")
    factors.append(_factor(
        "information_completeness", "Information completeness",
        "data_quality", s, comp_cfg["weight"], status,
        f"{len(missing_fields)} of {len(MODEL_FEATURES) - len(excluded)} "
        f"scored fields missing: {missing_fields or 'none'}."))

    con_cfg = cfg["attribute_consistency"]
    checks = con_cfg["checks"]
    flags: list[str] = []
    s = 0.0
    sqft, bhk = _num(f, "SQUARE_FT"), _num(f, "BHK_NO.")
    if sqft is not None and bhk:
        per_bhk = sqft / bhk
        lo, hi = con_cfg["sqft_per_bhk_plausible_range"]
        if per_bhk < lo or per_bhk > hi:
            s += checks["sqft_per_bhk_outside_range_points"]
            flags.append(f"area per BHK {per_bhk:.0f} sq ft outside "
                         f"[{lo}, {hi}]")
    if bhk is not None and bhk >= 8:
        s += checks["bhk_at_least_8_points"]
        flags.append(f"unusually large configuration ({bhk:.0f} BHK)")
    if sqft is not None and sqft > 20000:
        s += checks["sqft_over_20000_points"]
        flags.append(f"very large area ({sqft:.0f} sq ft)")
    dist = _num(f, "DIST_TO_CITY_CENTROID")
    if dist is not None and dist > 50:
        s += checks["dist_to_centroid_km_over_50_points"]
        flags.append(f"coordinates {dist:.0f} km from the city centroid")
    rtm = _num(f, "READY_TO_MOVE")
    if rtm is not None and uc is not None and rtm != 1 - uc:
        s += checks["ready_to_move_contradiction_points"]
        flags.append("READY_TO_MOVE contradicts UNDER_CONSTRUCTION")
    s = min(con_cfg["max_score"], s)
    factors.append(_factor(
        "attribute_consistency", "Attribute consistency", "data_quality",
        s, con_cfg["weight"], "flagged" if flags else "consistent",
        "Flags: " + ("; ".join(flags) if flags else "none.")))

    # ---- Domain C: model uncertainty ---------------------------------------
    unc_cfg = cfg["prediction_uncertainty"]
    cal = unc_cfg["calibration"]
    evaluated_max = 100.0
    if predicted_price_lacs is None:
        evaluated_max -= unc_cfg["weight"]
        warnings.append("Predicted price not supplied — prediction "
                        "uncertainty not evaluated; the overall score is "
                        "rescaled from the remaining factors.")
        factors.append(_factor("prediction_uncertainty",
                               "Prediction uncertainty", "model_uncertainty",
                               0.0, unc_cfg["weight"], "not_evaluated",
                               "No predicted price supplied."))
        unc_block = None
    else:
        band = next(b for b in cal["bands_predicted_price_lacs"]
                    if predicted_price_lacs >= b["predicted_price_min_lacs"]
                    and (b["predicted_price_max_lacs"] is None
                         or predicted_price_lacs < b["predicted_price_max_lacs"]))
        ape80 = band["ape_p80_pct"]
        frac = min(1.0, max(0.0, (ape80 - cal["ape_floor_pct_for_zero_score"])
                            / (cal["ape_ceiling_pct_for_full_score"]
                               - cal["ape_floor_pct_for_zero_score"])))
        s = unc_cfg["weight"] * frac
        status = "low" if frac < 0.34 else "moderate" if frac < 0.67 else "high"
        factors.append(_factor(
            "prediction_uncertainty", "Prediction uncertainty",
            "model_uncertainty", s, unc_cfg["weight"], status,
            f"Predicted price ₹{predicted_price_lacs:,.1f}L falls in the "
            f"₹{band['predicted_price_min_lacs']}–"
            f"{band['predicted_price_max_lacs'] or '∞'}L band; held-out "
            f"APE p80 for that band is {ape80}% (n={band['n']})."))
        unc_block = {"predicted_price_band_lacs":
                     [band["predicted_price_min_lacs"],
                      band["predicted_price_max_lacs"]],
                     "calibrated_ape_p80_pct": ape80,
                     "calibration_n": band["n"]}

    # ---- Aggregate ----------------------------------------------------------
    raw_total = sum(fac["score"] for fac in factors)
    overall = round(raw_total / evaluated_max * 100.0, 1) if evaluated_max else 0.0
    category = ("LOW" if overall < 30 else
                "MEDIUM" if overall < 60 else "HIGH")
    domains: dict[str, dict] = {}
    for dname, members in cfg["domains"].items():
        ds = sum(fac["score"] for fac in factors if fac["id"] in members)
        dm = sum(fac["max_score"] for fac in factors if fac["id"] in members)
        domains[dname] = {"score": round(ds, 1), "max_score": float(dm)}

    result = {
        "overall_score": overall,
        "category": category,
        "domains": domains,
        "factors": factors,
        "warnings": warnings,
        "recommended_actions": sorted(
            {fac["recommended_action"] for fac in factors
             if fac["score"] > 0}),
        "uncertainty": unc_block,
        "score_basis": (f"sum of factor scores = {raw_total:.1f} of "
                        f"{evaluated_max:.0f} evaluated points"
                        + (" (rescaled to 100)" if evaluated_max < 100 else "")),
        "methodology": {"version": cfg["methodology_version"],
                        "bands": cfg["bands"],
                        "disclaimer": cfg["scope_disclaimer"]},
    }
    result["narrative"] = _text.build_narrative(result)
    return result
