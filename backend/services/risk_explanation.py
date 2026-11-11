#!/usr/bin/env python3
"""risk_explanation.py — human-readable texts for the risk engine.

Every explanation and recommended action lives here, keyed by
(factor, status), so the scoring logic in risk_engine.py stays purely
numerical and the dashboard wording can be reviewed independently.

Language discipline (methodology requirement): texts describe what the
LISTING DATA records and what to verify. They never assert legal
ownership, title clearance, encumbrance status or regulatory
compliance — the dataset cannot establish any of those.
"""
from __future__ import annotations

FACTOR_TEXT: dict[str, dict[str, dict[str, str]]] = {
    "rera_status": {
        "recorded": {
            "explanation": "The listing data records RERA registration for "
                           "this project.",
            "action": "Verify the registration number on the state RERA "
                      "portal and confirm it covers this project and phase."},
        "not_recorded": {
            "explanation": "The listing data does not record RERA "
                           "registration for this project. This is a "
                           "verification flag only — listing data alone "
                           "cannot establish a project's compliance status.",
            "action": "Check the project on the state RERA portal; if it "
                      "is registered, record the number, and if it is not, "
                      "treat regulatory verification as outstanding."},
        "unknown": {
            "explanation": "RERA information is missing for this property, "
                           "so this factor is scored at the neutral midpoint "
                           "— unknown is not treated as non-compliance.",
            "action": "Obtain the project's RERA status from the seller or "
                      "the state RERA portal before relying on this score."},
    },
    "construction_status": {
        "ready": {
            "explanation": "The property is recorded as complete "
                           "(not under construction).",
            "action": "Confirm completion/occupancy documentation during "
                      "physical verification."},
        "under_construction": {
            "explanation": "The property is recorded as under construction, "
                           "which carries delivery and completion risk.",
            "action": "Verify the builder's track record, the promised "
                      "possession date, and stage-wise construction progress "
                      "before committing."},
        "unknown": {
            "explanation": "Construction status is missing, so this factor "
                           "is scored at the neutral midpoint.",
            "action": "Confirm whether the property is ready to move or "
                      "under construction."},
    },
    "resale_status": {
        "first_sale": {
            "explanation": "The listing is recorded as a first sale, not a "
                           "resale.",
            "action": "Standard first-sale document checks apply."},
        "resale": {
            "explanation": "The listing is a resale, which adds a "
                           "verification burden around previous transfers.",
            "action": "Review the chain of previous sale documents during "
                      "due diligence."},
        "unknown": {
            "explanation": "Resale status is missing; scored at half the "
                           "factor weight.",
            "action": "Confirm whether this is a first sale or a resale."},
    },
    "location_evidence": {
        "established": {
            "explanation": "The locality is well represented in the "
                           "training data, so the valuation rests on "
                           "substantial comparable-listing evidence.",
            "action": "No location-specific action beyond standard checks."},
        "moderate": {
            "explanation": "The locality has moderate representation in the "
                           "training data; comparable evidence exists but is "
                           "not deep.",
            "action": "Cross-check the estimate against recent listings in "
                      "the same locality."},
        "thin": {
            "explanation": "The locality appears only rarely in the training "
                           "data, so both the model and a human valuer have "
                           "thin comparable evidence here.",
            "action": "Seek independent local comparables before relying on "
                      "the estimate."},
        "unseen": {
            "explanation": "The locality (or city) has no usable "
                           "representation in the training data — the "
                           "valuation is an extrapolation for this location.",
            "action": "Treat the estimate as indicative only; obtain a "
                      "local valuation for this area."},
    },
    "information_completeness": {
        "complete": {
            "explanation": "All model input fields were supplied for this "
                           "property.",
            "action": "No completeness action."},
        "partial": {
            "explanation": "Some model input fields were missing and had to "
                           "be imputed by the pipeline, which lowers "
                           "confidence in both the estimate and this score.",
            "action": "Supply the missing fields listed in the warnings "
                      "and re-run the assessment."},
        "sparse": {
            "explanation": "Many model input fields were missing; a large "
                           "part of this assessment rests on imputed data.",
            "action": "Complete the property record before relying on "
                      "either the estimate or this score."},
    },
    "attribute_consistency": {
        "consistent": {
            "explanation": "No unusual or inconsistent attributes were "
                           "detected in the supplied property data.",
            "action": "No consistency action."},
        "flagged": {
            "explanation": "One or more attributes are unusual or "
                           "inconsistent (see factor details) — each flag "
                           "marks data to verify, not a defect in the "
                           "property.",
            "action": "Verify the flagged attributes against source "
                      "documents or a site visit."},
    },
    "prediction_uncertainty": {
        "low": {
            "explanation": "On held-out properties in this price band, the "
                           "model's typical error was comparatively low.",
            "action": "Use the estimate with the calibrated error band in "
                      "mind."},
        "moderate": {
            "explanation": "On held-out properties in this price band, the "
                           "model's 80th-percentile absolute error was "
                           "material (see factor details).",
            "action": "Treat the point estimate as the centre of a wide "
                      "range, not an exact value."},
        "high": {
            "explanation": "On held-out properties in this price band, the "
                           "model's errors were large at the 80th "
                           "percentile (see factor details).",
            "action": "Obtain an independent valuation before acting on "
                      "this estimate."},
        "not_evaluated": {
            "explanation": "No predicted price was supplied, so prediction "
                           "uncertainty could not be scored; the overall "
                           "score is rescaled from the remaining factors.",
            "action": "Run the valuation first, then re-assess risk with "
                      "the predicted price included."},
    },
}


def factor_text(factor_id: str, status: str) -> dict[str, str]:
    return FACTOR_TEXT[factor_id][status]


def build_narrative(result: dict) -> str:
    """One-paragraph dashboard summary, built only from computed values."""
    cat = result["category"]
    score = result["overall_score"]
    top = sorted(result["factors"], key=lambda f: -f["score"])[:2]
    drivers = "; ".join(
        f"{f['name']} contributes {f['score']:.1f}/{f['max_score']:.0f} "
        f"({f['explanation']})" for f in top if f["score"] > 0)
    base = (f"Overall risk score {score:.1f}/100 — {cat}. "
            f"Regulatory & construction domain: "
            f"{result['domains']['regulatory_construction']['score']:.1f}/"
            f"{result['domains']['regulatory_construction']['max_score']:.0f}; "
            f"data-quality domain: "
            f"{result['domains']['data_quality']['score']:.1f}/"
            f"{result['domains']['data_quality']['max_score']:.0f}; "
            f"model-uncertainty domain: "
            f"{result['domains']['model_uncertainty']['score']:.1f}/"
            f"{result['domains']['model_uncertainty']['max_score']:.0f}.")
    if drivers:
        base += f" Largest contributors: {drivers}."
    if result["warnings"]:
        base += (f" {len(result['warnings'])} warning(s) — "
                 f"missing or unknown information is listed with the "
                 f"factor details.")
    base += (" This is an academic prototype score over documented "
             "indicators, not a due-diligence or investment-risk verdict.")
    return base
