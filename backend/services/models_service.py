#!/usr/bin/env python3
"""services/models_service.py — model metrics & comparison data.

Sources (read-only, all measured artifacts — nothing recomputed or
invented here):
  * the packaged model's model_metadata.json (served model);
  * the training stage's model_metrics.json (five-model benchmark with
    baselines, tuning, the single test score, geographic
    generalisation);
  * the optimisation stage's champion record (the served model's own
    selection history).
Missing optional files degrade the comparison gracefully.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("backend.models_service")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:
        logger.warning("Optional artifact unreadable (%s): %s", path, exc)
        return None


class ModelsService:
    def __init__(self, ml_service, training_metrics_path: Path,
                 champion_path: Path):
        self._ml = ml_service
        self._training = _read_json(training_metrics_path)
        self._champion = _read_json(champion_path)

    def metrics(self) -> dict:
        """Metrics of the SERVED (packaged) model."""
        meta = self._ml.metadata()
        return {"model_id": "xgboost-e01",
                "model_name": meta["model"]["name"],
                "hyperparameters": meta["model"]["hyperparameters"],
                "training": meta["training"],
                "metrics": meta["metrics"],
                "environment": meta["environment"],
                "provenance": meta["provenance"]}

    def schema(self) -> dict:
        """The served model's exact input feature schema."""
        return self._ml.feature_schema()

    def shap_summary(self) -> dict:
        """Precomputed global SHAP summary for the served model
        (backend/ml/shap_summary.json, generated from the actual model
        on a documented sample — see its provenance field)."""
        import json as _json
        from pathlib import Path as _P
        path = _P(self._ml.model_dir) / "shap_summary.json"
        try:
            return _json.loads(path.read_text())
        except Exception as exc:
            logger.warning("shap_summary.json unavailable: %s", exc)
            from errors import ApiError
            raise ApiError(503, "SHAP_SUMMARY_UNAVAILABLE",
                           "Global SHAP summary is not available.")

    def compare(self) -> dict:
        """Validation/test comparison across the project's measured
        candidates, with the served model flagged."""
        entries: list[dict] = []
        if self._training:
            tm = self._training
            for name, base in tm.get("baselines", {}).items():
                tuned = (tm.get("tuning") or {}).get(name) or {}
                entries.append({
                    "model": name, "stage": "training_stage",
                    "tuned": bool(tuned),
                    "validation_r2": tuned.get("valid_r2", base.get("valid_r2")),
                    "validation_mae_lacs": tuned.get(
                        "valid_mae", base.get("valid_mae_lacs")),
                    "validation_rmse_lacs": tuned.get(
                        "valid_rmse", base.get("valid_rmse_lacs")),
                    "validation_mape_pct": base.get("valid_mape_pct"),
                    "baseline_train_time_s": base.get("valid_train_time_s"),
                    "cv_r2_mean": base.get("cv_r2_mean"),
                    "cv_r2_std": base.get("cv_r2_std"),
                    "selected": False})
            test = tm.get("test") or {}
            if test:
                entries.append({
                    "model": "xgboost (training-stage winner)",
                    "stage": "training_stage_final",
                    "test_r2": test.get("r2"),
                    "test_mae_lacs": test.get("mae_lacs"),
                    "test_rmse_lacs": test.get("rmse_lacs"),
                    "selected": False})
            geo = tm.get("grouped_generalisation") or {}
            if geo:
                entries.append({
                    "model": "xgboost (training-stage winner, unseen "
                             "localities)",
                    "stage": "geographic_generalisation",
                    "test_r2": geo.get("r2"),
                    "test_mae_lacs": geo.get("mae_lacs"),
                    "test_rmse_lacs": geo.get("rmse_lacs"),
                    "selected": False})
        if self._champion:
            ch = self._champion
            entries.append({
                "model": "xgboost (optimisation E01 — SERVED)",
                "stage": "optimisation_stage",
                "validation_r2": ch.get("valid_r2"),
                "validation_rmse_lacs": ch.get("valid_rmse"),
                "cv_r2_mean": ch.get("cv_r2_mean"),
                "cv_r2_std": ch.get("cv_r2_std"),
                "test_r2": (ch.get("test") or {}).get("r2"),
                "test_mae_lacs": (ch.get("test") or {}).get("mae_lacs"),
                "test_rmse_lacs": (ch.get("test") or {}).get("rmse_lacs"),
                "selected": True})
        return {"served_model_id": "xgboost-e01",
                "comparison": entries,
                "note": "All figures are measured results from the "
                        "training and optimisation stages (grouped "
                        "70/15/15 protocol; each stage's test partition "
                        "scored once, after its selection)."}
