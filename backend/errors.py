#!/usr/bin/env python3
"""errors.py — consistent JSON envelopes and centralized error handling.

Success envelope: {"success": true, "request_id": ..., "timestamp": ...,
                   "data": {...}}
Error envelope:   {"success": false, "request_id": ..., "timestamp": ...,
                   "error": {"code": ..., "message": ...}}

Internal exceptions are logged with their traceback and NEVER exposed
to clients; clients receive stable error codes and safe messages.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import g, jsonify

logger = logging.getLogger("backend.errors")


class ApiError(Exception):
    """An error with an HTTP status and a stable client-facing code."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def success_response(data, status: int = 200):
    return jsonify({"success": True,
                    "request_id": getattr(g, "request_id", None),
                    "timestamp": utcnow_iso(),
                    "data": data}), status


def error_response(status: int, code: str, message: str):
    return jsonify({"success": False,
                    "request_id": getattr(g, "request_id", None),
                    "timestamp": utcnow_iso(),
                    "error": {"code": code, "message": message}}), status


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def _api_error(err: ApiError):
        return error_response(err.status, err.code, err.message)

    @app.errorhandler(ValueError)
    def _value_error(err: ValueError):
        # Raised by the packaged prediction/risk validation layers.
        return error_response(400, "VALIDATION_ERROR", str(err))

    @app.errorhandler(404)
    def _not_found(_err):
        return error_response(404, "NOT_FOUND", "The requested resource "
                                                 "does not exist.")

    @app.errorhandler(405)
    def _method_not_allowed(_err):
        return error_response(405, "METHOD_NOT_ALLOWED",
                              "Method not allowed for this endpoint.")

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        logger.exception("Unhandled error: %s", err)
        return error_response(500, "INTERNAL_ERROR",
                              "An internal error occurred. Please try "
                              "again later.")
