#!/usr/bin/env python3
"""services/valuation_service.py — prediction + explanation use cases,
including history persistence (best-effort: a database failure never
fails a valuation; it is logged and reported as history_saved=False).
"""
from __future__ import annotations

import logging

from models.history import DatabaseUnavailable, build_record  # noqa: E402

logger = logging.getLogger("backend.valuation_service")


class ValuationService:
    def __init__(self, ml_service, history_repository, model_id: str):
        self._ml = ml_service
        self._history = history_repository
        self._model_id = model_id

    def _persist(self, request_id: str, endpoint: str, features: dict,
                 price: float) -> bool:
        try:
            self._history.insert(build_record(
                request_id=request_id, endpoint=endpoint,
                property_features=features, predicted_price_lacs=price,
                model_id=self._model_id))
            return True
        except DatabaseUnavailable as exc:
            logger.error("History write failed (%s): %s", endpoint, exc)
            return False

    def predict(self, request_id: str, features: dict) -> dict:
        price = self._ml.predict(features)
        saved = self._persist(request_id, "valuation/predict", features, price)
        return {"predicted_price_lacs": price, "history_saved": saved}

    def explain(self, request_id: str, features: dict) -> dict:
        explanation = self._ml.explain(features)
        saved = self._persist(request_id, "valuation/explain", features,
                              explanation["predicted_price_lacs"])
        return {"explanation": explanation, "history_saved": saved}
