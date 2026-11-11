#!/usr/bin/env python3
"""services/ml_service.py — owns the packaged ML artifacts.

Loads the model exactly once (at application startup) through the
existing packaged modules in backend/ml (predict.py for inference,
shap_service.py for explanations). A load failure is captured, not
raised: the app keeps running in a degraded state, /api/health reports
it, and valuation endpoints answer a clean 503.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("backend.ml_service")

MODEL_ID = "xgboost-e01"  # optimisation-stage experiment E01


class MLService:
    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.loaded = False
        self.load_error: str | None = None
        self._predict = None
        self._shap_service = None
        self._metadata: dict | None = None
        self._feature_schema: dict | None = None

    def load(self) -> None:
        try:
            ml_dir = str(self.model_dir)
            if ml_dir not in sys.path:
                sys.path.insert(0, ml_dir)
            import predict as predict_module
            import shap_service as shap_module
            # Force the artifact load now so failures surface at startup.
            predict_module._load()
            self._predict = predict_module
            self._shap_service = shap_module
            self._metadata = predict_module.model_info()
            import json
            self._feature_schema = json.loads(
                (self.model_dir / "feature_schema.json").read_text())
            self.loaded = True
            logger.info("ML model loaded from %s (%s)", self.model_dir,
                        self.model_name)
        except Exception as exc:  # startup must survive a broken artifact
            self.load_error = f"{type(exc).__name__}: {exc}"
            logger.error("ML model failed to load: %s", self.load_error)

    @property
    def model_name(self) -> str:
        if self._metadata:
            return self._metadata["model"]["name"]
        return "unavailable"

    def require_loaded(self) -> None:
        if not self.loaded:
            from errors import ApiError
            raise ApiError(503, "MODEL_UNAVAILABLE",
                           "The valuation model is not available. "
                           "Please try again later.")

    def predict(self, property_features: dict) -> float:
        self.require_loaded()
        return self._predict.predict_property(property_features)

    def explain(self, property_features: dict) -> dict:
        self.require_loaded()
        return self._shap_service.explain_property(property_features)

    def metadata(self) -> dict:
        self.require_loaded()
        return self._metadata

    def feature_schema(self) -> dict:
        self.require_loaded()
        return self._feature_schema
