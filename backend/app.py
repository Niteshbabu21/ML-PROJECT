#!/usr/bin/env python3
"""app.py — Flask application factory for the real-estate valuation,
SHAP explainability, risk assessment and prototype tokenisation API.

Run locally:
    python app.py                      # http://127.0.0.1:5000
Production (Render): gunicorn "app:app"

The trained model is loaded ONCE here at startup (see
services/ml_service.py). MongoDB history is wired through a repository
interface; if MongoDB is unreachable the API keeps serving valuations
and reports the degradation honestly (history_saved=false, history
endpoints 503).
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from flask import Flask, g, request  # noqa: E402
from flask_cors import CORS  # noqa: E402

from config import Config  # noqa: E402
from errors import register_error_handlers  # noqa: E402

logger = logging.getLogger("backend.app")


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _build_history_repository(cfg):
    if cfg["HISTORY_BACKEND"] == "memory":
        from models.history import InMemoryHistoryRepository
        logger.warning("History backend = memory (process-local, "
                       "development only)")
        return InMemoryHistoryRepository()
    from models.history import MongoHistoryRepository
    return MongoHistoryRepository(cfg["MONGO_URI"], cfg["MONGO_DB_NAME"],
                                  cfg["HISTORY_COLLECTION"],
                                  cfg["DB_TIMEOUT_MS"])


def _build_chain_store(cfg):
    if cfg["HISTORY_BACKEND"] == "memory":
        from models.chain_store import InMemoryChainStore
        return InMemoryChainStore()
    from models.chain_store import MongoChainStore
    return MongoChainStore(cfg["MONGO_URI"], cfg["MONGO_DB_NAME"],
                           cfg["CHAIN_COLLECTION"], cfg["DB_TIMEOUT_MS"])


def create_app(config_object: type = Config, *,
               history_repository=None, ml_service=None,
               chain_store=None) -> Flask:
    """Application factory. history_repository / ml_service may be
    injected (unit tests use an in-memory repository fixture; the ML
    service always wraps the real packaged model)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass

    app = Flask(__name__)
    app.config.from_object(config_object)
    _setup_logging(app.config["LOG_LEVEL"])

    # Production guards: never run publicly with the development
    # SECRET_KEY, and warn when administrative chain operations are
    # left unprotected.
    if app.config.get("ENV") == "production":
        if app.config.get("SECRET_KEY") == "dev-only-secret-change-me":
            raise RuntimeError(
                "SECRET_KEY must be set to a real secret in production.")
        if not app.config.get("ADMIN_API_KEY"):
            logger.warning("ADMIN_API_KEY is not set: chain register/mint "
                           "endpoints are UNPROTECTED in production.")

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    register_error_handlers(app)

    @app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

    @app.after_request
    def _log_and_tag(response):
        response.headers["X-Request-ID"] = g.get("request_id", "")
        logger.info("%s %s -> %s (req %s)", request.method, request.path,
                    response.status_code, g.get("request_id", ""))
        return response

    # --- service wiring (model loaded once, here) -------------------------
    from services.ml_service import MLService, MODEL_ID
    ml = ml_service or MLService(app.config["MODEL_DIR"])
    if ml_service is None:
        ml.load()

    repo = history_repository or _build_history_repository(app.config)

    from services.history_service import HistoryService
    from services.models_service import ModelsService
    from services.risk_service import RiskService
    from services.valuation_service import ValuationService

    app.extensions["ml"] = ml
    app.extensions["history_repo"] = repo
    app.extensions["valuation"] = ValuationService(ml, repo, MODEL_ID)
    app.extensions["risk"] = RiskService(ml)
    app.extensions["models"] = ModelsService(
        ml, app.config["TRAINING_METRICS_PATH"],
        app.config["OPTIMIZATION_CHAMPION_PATH"])
    app.extensions["history"] = HistoryService(repo)

    from services.chain_service import ChainService
    app.extensions["chain"] = ChainService(
        app.config, chain_store or _build_chain_store(app.config),
        app.extensions["valuation"], app.extensions["risk"])

    # --- blueprints ---------------------------------------------------------
    from routes.chain import bp as chain_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.models import bp as models_bp
    from routes.risk import bp as risk_bp
    from routes.system import bp as system_bp
    from routes.token import bp as token_bp
    from routes.valuation import bp as valuation_bp
    for blueprint in (system_bp, valuation_bp, risk_bp, token_bp,
                      models_bp, dashboard_bp, chain_bp):
        app.register_blueprint(blueprint)

    logger.info("Backend ready (model_loaded=%s, history_backend=%s)",
                ml.loaded, app.config["HISTORY_BACKEND"])
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "5000")))
