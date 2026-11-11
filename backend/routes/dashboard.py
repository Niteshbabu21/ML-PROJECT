#!/usr/bin/env python3
"""routes/dashboard.py — GET /api/dashboard/summary, /history."""
from __future__ import annotations

from flask import Blueprint, current_app

from errors import success_response, utcnow_iso
from schemas.property import parse_pagination

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@bp.get("/summary")
def summary():
    ext = current_app.extensions
    stats = ext["history"].summary()
    return success_response({
        **stats,
        "model_id": "xgboost-e01",
        "model_name": ext["ml"].model_name,
        "model_loaded": ext["ml"].loaded,
        "generated_at": utcnow_iso()})


@bp.get("/history")
def history():
    page, page_size = parse_pagination()
    return success_response(
        current_app.extensions["history"].list_history(page, page_size))
