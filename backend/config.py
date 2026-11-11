#!/usr/bin/env python3
"""config.py — environment-based configuration for the Flask backend.

All sensitive or deployment-specific values come from environment
variables (see .env.example). Nothing secret is hardcoded; the defaults
below are for local development only.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GOAL_FILES_DIR = BASE_DIR.parent


def _origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


class Config:
    ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-change-me")
    JSON_SORT_KEYS = False

    # ML artifacts (packaged in the packaging stage; loaded once at startup)
    MODEL_DIR = Path(os.getenv("MODEL_DIR", str(BASE_DIR / "ml")))

    # MongoDB (valuation history)
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "real_estate_valuation")
    HISTORY_COLLECTION = os.getenv("HISTORY_COLLECTION", "valuation_history")
    DB_TIMEOUT_MS = int(os.getenv("DB_TIMEOUT_MS", "1500"))
    # "mongo" (default) or "memory" (local development without a server;
    # history is then process-local and lost on restart).
    HISTORY_BACKEND = os.getenv("HISTORY_BACKEND", "mongo")

    # CORS for the React (Vite) frontend
    CORS_ORIGINS = _origins()

    # Tokenisation (prototype): one token per ₹10,000 of value, supply
    # floored — see services/token_service.py.
    TOKEN_DENOMINATION_INR = int(os.getenv("TOKEN_DENOMINATION_INR", "10000"))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Optional stage artifacts for /api/models/compare (read-only).
    TRAINING_METRICS_PATH = Path(os.getenv(
        "TRAINING_METRICS_PATH",
        str(GOAL_FILES_DIR / "training_stage" / "ml" / "model_metrics.json")))
    OPTIMIZATION_LOG_PATH = Path(os.getenv(
        "OPTIMIZATION_LOG_PATH",
        str(GOAL_FILES_DIR / "optimization_stage" / "ml"
            / "experiment_log.csv")))
    OPTIMIZATION_CHAMPION_PATH = Path(os.getenv(
        "OPTIMIZATION_CHAMPION_PATH",
        str(GOAL_FILES_DIR / "optimization_stage" / "ml" / "artifacts"
            / "champion.json")))

    # Blockchain bridge (local Hardhat network). Secrets stay in the
    # environment: CHAIN_PRIVATE_KEY has no default in code — when unset,
    # the bridge uses the local node's first unlocked account (Hardhat
    # local node only; never suitable for a real network).
    CHAIN_RPC_URL = os.getenv("CHAIN_RPC_URL", "http://127.0.0.1:8545")
    CHAIN_DEPLOYMENT_FILE = Path(os.getenv(
        "CHAIN_DEPLOYMENT_FILE",
        str(GOAL_FILES_DIR / "blockchain" / "deployments"
            / "localhost.json")))
    CHAIN_ABI_FILE = Path(os.getenv(
        "CHAIN_ABI_FILE",
        str(GOAL_FILES_DIR / "blockchain" / "abi" / "PropertyToken.json")))
    CHAIN_PRIVATE_KEY = os.getenv("CHAIN_PRIVATE_KEY", "")

    # Administrative operations (chain register/mint) require this key
    # in the X-Admin-Key header WHEN SET. Unset = local development
    # only; production startup refuses the default SECRET_KEY and warns
    # loudly if ADMIN_API_KEY is missing (see app.py).
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
    CHAIN_TX_TIMEOUT_S = int(os.getenv("CHAIN_TX_TIMEOUT_S", "60"))
    CHAIN_COLLECTION = os.getenv("CHAIN_COLLECTION", "tokenisations")


class TestConfig(Config):
    TESTING = True
    LOG_LEVEL = "WARNING"
