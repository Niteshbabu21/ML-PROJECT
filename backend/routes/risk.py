#!/usr/bin/env python3
"""routes/risk.py — POST /api/risk/assess."""
from __future__ import annotations

from flask import Blueprint, current_app, g

from errors import success_response
from schemas.property import json_body, parse_property_features

bp = Blueprint("risk", __name__, url_prefix="/api/risk")


@bp.post("/assess")
def assess():
    body = json_body()
    features = parse_property_features(body)
    price = body.get("predicted_price_lacs")
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            from errors import ApiError
            raise ApiError(400, "VALIDATION_ERROR",
                           "predicted_price_lacs must be a number.")
    result = current_app.extensions["risk"].assess(features, price)
    return success_response({
        "request_id": g.request_id,
        "property": features,
        "predicted_price_lacs": result["predicted_price_lacs"],
        "predicted_price_source": result["predicted_price_source"],
        "risk_score": result["overall_score"],
        "risk_category": result["category"],
        "domains": result["domains"],
        "factors": result["factors"],
        "warnings": result["warnings"],
        "recommended_actions": result["recommended_actions"],
        "uncertainty": result["uncertainty"],
        "narrative": result["narrative"],
        "methodology": result["methodology"]})
