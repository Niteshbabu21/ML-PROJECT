#!/usr/bin/env python3
"""routes/token.py — POST /api/token/calculate.

Accepts either {"valuation_lacs": <number>} or {"property": {...}} (in
which case the valuation is computed first with the served model).
"""
from __future__ import annotations

from flask import Blueprint, current_app, g

from errors import ApiError, success_response
from schemas.property import json_body, parse_property_features
from services.token_service import calculate_token_supply

bp = Blueprint("token", __name__, url_prefix="/api/token")


@bp.post("/calculate")
def calculate():
    body = json_body()
    denomination = current_app.config["TOKEN_DENOMINATION_INR"]
    valuation_lacs = body.get("valuation_lacs")
    source = "provided"
    if valuation_lacs is None:
        if "property" not in body:
            raise ApiError(400, "VALIDATION_ERROR",
                           "Provide 'valuation_lacs' or 'property' "
                           "features to value first.")
        features = parse_property_features(body)
        valuation_lacs = current_app.extensions["ml"].predict(features)
        source = "computed_by_valuation_model"
    try:
        valuation_lacs = float(valuation_lacs)
    except (TypeError, ValueError):
        raise ApiError(400, "VALIDATION_ERROR",
                       "valuation_lacs must be a number.")
    result = calculate_token_supply(valuation_lacs, denomination)
    result["request_id"] = g.request_id
    result["valuation_source"] = source
    return success_response(result)
