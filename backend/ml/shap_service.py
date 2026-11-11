#!/usr/bin/env python3
"""shap_service.py — Flask-facing explanation service.

    from shap_service import explain_property
    result = explain_property(property_features)   # JSON-compatible dict

The input contract, validation and price are exactly predict.py's — an
explanation can never disagree with the served prediction. Invalid
input raises ValueError (a Flask layer maps that to HTTP 400).

Returned structure (all values JSON-native):
  predicted_price_lacs   the served prediction (₹ lakh)
  base_value_log         TreeExplainer expected value (log1p space)
  baseline_price_lacs    expm1(base value): the model's average
                         expectation before this property's features
  model_output_log       final raw model output (log1p space)
  contributions          all 20 source features, ranked by |SHAP|:
                         {feature, value, shap_log, price_factor,
                          direction}
  top_positive / top_negative / top_influential   top-k views
  additivity             reconstruction check (must be ~0)
  explanation            human-readable summary built from the actual
                         computed contributions — nothing hardcoded
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import numpy as np

import explain as _explain
import predict as _predict

_HERE = Path(__file__).resolve().parent
_CONFIG = json.loads((_HERE / "shap_config.json").read_text())
TOP_K = int(_CONFIG["top_k"])


def _json_value(v) -> object:
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, float) and np.isnan(v):
        return None
    return v


def _describe(feature: str, value, shap_log: float) -> str:
    factor = float(np.exp(shap_log))
    direction = "raised" if shap_log > 0 else "lowered"
    return (f"{feature} = {value} {direction} the estimate "
            f"(×{factor:.2f})")


def explain_property(property_features: Mapping) -> dict:
    """Explain one property prediction. Raises ValueError on invalid
    input, exactly as predict_property does."""
    frame = _predict._validate(property_features)  # shared validation
    price = _predict.predict_property(property_features)
    info = _explain.explain_frame(frame)[0]

    row = frame.iloc[0]
    contributions = []
    for feature, shap_log in info["shap_source"].items():
        contributions.append({
            "feature": feature,
            "value": _json_value(row[feature]),
            "shap_log": round(float(shap_log), 6),
            "price_factor": round(float(np.exp(shap_log)), 4),
            "direction": ("increases_price" if shap_log > 0
                          else "decreases_price" if shap_log < 0
                          else "neutral"),
        })
    contributions.sort(key=lambda c: -abs(c["shap_log"]))
    top_positive = [c for c in contributions if c["shap_log"] > 0][:TOP_K]
    top_negative = sorted([c for c in contributions if c["shap_log"] < 0],
                          key=lambda c: c["shap_log"])[:TOP_K]

    baseline_price = float(np.expm1(info["base_value_log"]))
    up = "; ".join(_describe(c["feature"], c["value"], c["shap_log"])
                   for c in top_positive[:3])
    down = "; ".join(_describe(c["feature"], c["value"], c["shap_log"])
                     for c in top_negative[:3])
    text = (f"Estimated price ₹{price:,.2f} lakh. The model starts from "
            f"a baseline expectation of ₹{baseline_price:,.2f} lakh (its "
            f"average across the properties it was trained on). ")
    if up:
        text += f"Pushing the estimate up: {up}. "
    if down:
        text += f"Pulling it down: {down}. "
    text += ("Contributions are SHAP values in log-price space; each "
             "×factor is that feature's multiplicative effect on price.")

    return {
        "predicted_price_lacs": price,
        "model_output_log": round(info["model_output_log"], 6),
        "base_value_log": round(info["base_value_log"], 6),
        "baseline_price_lacs": round(baseline_price, 2),
        "contributions": contributions,
        "top_positive": top_positive,
        "top_negative": top_negative,
        "top_influential": contributions[:TOP_K],
        "additivity": {
            "base_plus_contributions_log": round(
                info["base_value_log"]
                + sum(info["shap_source"].values()), 6),
            "model_output_log": round(info["model_output_log"], 6),
            "abs_error": info["additivity_abs_error"],
            "tolerance": _CONFIG["additivity_tolerance_log_units"],
            "verified": bool(info["additivity_abs_error"]
                             <= _CONFIG["additivity_tolerance_log_units"]),
        },
        "explanation": text,
        "model": {"name": "XGBoost Regressor (E01)",
                  "explainer": _CONFIG["explainer"],
                  "explanation_space": _CONFIG["explanation_space"]},
    }


def explain_properties(records: list[Mapping]) -> list[dict]:
    return [explain_property(r) for r in records]
