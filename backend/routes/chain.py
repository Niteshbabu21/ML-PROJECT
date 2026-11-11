#!/usr/bin/env python3
"""routes/chain.py — blockchain bridge endpoints.

POST /api/chain/register  register a valued property on-chain (admin)
POST /api/chain/mint      mint the registered property's token supply
GET  /api/chain/status    chain/contract connectivity
GET  /api/chain/properties            tokenisation records (+ live supply)
GET  /api/chain/properties/<id>       one record

Success is returned only after on-chain confirmation; failures use the
standard error envelope (503 CHAIN_UNAVAILABLE, 409 duplicates, 502
reverted transactions). Nothing is simulated.
"""
from __future__ import annotations

import hmac

from flask import Blueprint, current_app, g, request

from errors import ApiError, success_response
from schemas.property import json_body, parse_property_features

bp = Blueprint("chain", __name__, url_prefix="/api/chain")


def _service():
    return current_app.extensions["chain"]


def _require_admin():
    """Administrative chain operations (register/mint) are restricted
    when ADMIN_API_KEY is configured: callers must present it in the
    X-Admin-Key header (constant-time comparison). When the key is not
    configured the API is in local-development mode (the app factory
    refuses a default SECRET_KEY in production and warns if the admin
    key is missing there)."""
    key = current_app.config.get("ADMIN_API_KEY", "")
    if not key:
        return
    provided = request.headers.get("X-Admin-Key", "")
    if not hmac.compare_digest(provided, key):
        raise ApiError(401, "ADMIN_UNAUTHORIZED",
                       "This operation requires a valid X-Admin-Key header.")


@bp.get("/status")
def status():
    return success_response(_service().status())


@bp.post("/register")
def register():
    _require_admin()
    body = json_body()
    features = parse_property_features(body)
    return success_response(_service().register(g.request_id, features),
                            status=201)


@bp.post("/mint")
def mint():
    _require_admin()
    body = json_body()
    chain_property_id = body.get("chain_property_id")
    if not isinstance(chain_property_id, int) or chain_property_id < 1:
        raise ApiError(400, "VALIDATION_ERROR",
                       "chain_property_id must be a positive integer.")
    return success_response(_service().mint(chain_property_id))


@bp.get("/properties")
def properties():
    return success_response(_service().properties())


@bp.get("/properties/<int:chain_property_id>")
def property_detail(chain_property_id: int):
    return success_response(_service().property_detail(chain_property_id))
