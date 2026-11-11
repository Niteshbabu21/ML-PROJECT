#!/usr/bin/env python3
"""schemas/property.py — request parsing and response serialization.

Request bodies accept the canonical shape {"property": { ...features }}
or a flat feature mapping. Feature-level validation itself is delegated
to the packaged prediction module (the single source of truth for the
model's schema), so API validation can never drift from the model.

Response serializers build exactly the documented payload shapes.
"""
from __future__ import annotations

from flask import g, request

from errors import ApiError, utcnow_iso


def json_body() -> dict:
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        raise ApiError(400, "INVALID_JSON",
                       "Request body must be a JSON object.")
    return body


def parse_property_features(body: dict) -> dict:
    prop = body.get("property", body)
    if not isinstance(prop, dict) or not prop:
        raise ApiError(400, "VALIDATION_ERROR",
                       "Provide property features under the 'property' "
                       "key (or as a flat JSON object).")
    return prop


def parse_pagination() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except ValueError:
        raise ApiError(400, "VALIDATION_ERROR",
                       "page and page_size must be integers.")
    if page < 1 or page_size < 1 or page_size > 100:
        raise ApiError(400, "VALIDATION_ERROR",
                       "page must be >= 1 and page_size between 1 and 100.")
    return page, page_size


def valuation_data(*, property_features: dict, predicted_price_lacs: float,
                   model_id: str, model_name: str,
                   history_saved: bool) -> dict:
    return {"request_id": g.request_id,
            "property": property_features,
            "predicted_price_lacs": predicted_price_lacs,
            "currency": "INR",
            "model_id": model_id,
            "model_name": model_name,
            "timestamp": utcnow_iso(),
            "history_saved": history_saved}
