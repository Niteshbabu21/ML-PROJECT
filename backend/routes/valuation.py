#!/usr/bin/env python3
"""routes/valuation.py — POST /api/valuation/predict, /explain."""
from __future__ import annotations

from flask import Blueprint, current_app, g

from errors import success_response
from schemas.property import json_body, parse_property_features, valuation_data

bp = Blueprint("valuation", __name__, url_prefix="/api/valuation")


def _services():
    ext = current_app.extensions
    return ext["ml"], ext["valuation"]


@bp.post("/predict")
def predict():
    ml, valuation = _services()
    features = parse_property_features(json_body())
    result = valuation.predict(g.request_id, features)
    return success_response(valuation_data(
        property_features=features,
        predicted_price_lacs=result["predicted_price_lacs"],
        model_id="xgboost-e01", model_name=ml.model_name,
        history_saved=result["history_saved"]))


@bp.post("/explain")
def explain():
    ml, valuation = _services()
    features = parse_property_features(json_body())
    result = valuation.explain(g.request_id, features)
    exp = result["explanation"]
    return success_response({
        "request_id": g.request_id,
        "property": features,
        "prediction": {
            "predicted_price_lacs": exp["predicted_price_lacs"],
            "currency": "INR",
            "model_id": "xgboost-e01",
            "model_name": ml.model_name},
        "base_value_log": exp["base_value_log"],
        "baseline_price_lacs": exp["baseline_price_lacs"],
        "model_output_log": exp["model_output_log"],
        "contributions": exp["contributions"],
        "top_influential": exp["top_influential"],
        "top_positive": exp["top_positive"],
        "top_negative": exp["top_negative"],
        "additivity": exp["additivity"],
        "explanation": exp["explanation"],
        "history_saved": result["history_saved"]})
