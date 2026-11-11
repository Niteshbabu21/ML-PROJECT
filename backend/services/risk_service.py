#!/usr/bin/env python3
"""services/risk_service.py — wraps the documented risk engine.

If the caller does not supply a predicted price, the service computes
one with the valuation model (when available) so the uncertainty
factor can be scored; the price used and its source are reported.
The risk engine itself remains independent of the ML model and SHAP.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SERVICES_DIR = str(Path(__file__).resolve().parent)
if _SERVICES_DIR not in sys.path:
    sys.path.insert(0, _SERVICES_DIR)
import risk_engine  # noqa: E402


class RiskService:
    def __init__(self, ml_service):
        self._ml = ml_service

    def assess(self, features: dict,
               predicted_price_lacs: float | None) -> dict:
        price_source = "provided"
        if predicted_price_lacs is None:
            if self._ml is not None and self._ml.loaded:
                predicted_price_lacs = self._ml.predict(features)
                price_source = "computed_by_valuation_model"
            else:
                price_source = "unavailable"
        result = risk_engine.assess_risk(features, predicted_price_lacs)
        result["predicted_price_lacs"] = predicted_price_lacs
        result["predicted_price_source"] = price_source
        return result
