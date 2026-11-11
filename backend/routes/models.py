#!/usr/bin/env python3
"""routes/models.py — GET /api/models/metrics, /api/models/compare."""
from __future__ import annotations

from flask import Blueprint, current_app

from errors import success_response

bp = Blueprint("models", __name__, url_prefix="/api/models")


@bp.get("/metrics")
def metrics():
    return success_response(current_app.extensions["models"].metrics())


@bp.get("/compare")
def compare():
    return success_response(current_app.extensions["models"].compare())


@bp.get("/schema")
def schema():
    return success_response(current_app.extensions["models"].schema())


@bp.get("/shap-summary")
def shap_summary():
    return success_response(current_app.extensions["models"].shap_summary())
