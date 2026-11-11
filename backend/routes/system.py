#!/usr/bin/env python3
"""routes/system.py — GET /api/health."""
from __future__ import annotations

from flask import Blueprint, current_app

from errors import success_response, utcnow_iso

bp = Blueprint("system", __name__)


@bp.get("/api/health")
def health():
    ext = current_app.extensions
    ml = ext["ml"]
    db_ok = bool(ext["history_repo"].available())
    return success_response({
        "status": "ok" if (ml.loaded and db_ok) else "degraded",
        "model_loaded": ml.loaded,
        "model_id": "xgboost-e01",
        "model_name": ml.model_name,
        "model_load_error": ml.load_error,
        "database_connected": db_ok,
        "timestamp": utcnow_iso(),
        "api_version": "1.0.0"})
