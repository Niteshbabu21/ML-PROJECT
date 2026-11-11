#!/usr/bin/env python3
"""build_package.py — package the optimisation stage's selected model
(E01, Optuna-tuned XGBoost) into backend/ml/ for Flask integration.

The champion is reconstructed EXACTLY as the optimisation stage's
finalize.py fitted it for its single test evaluation: same grouped
partitions, same hyperparameters frozen at the validation best iteration
(1,154 trees), fitted on train+validation, log1p target. The packaged
artifact contains the complete inference path — the fitted preprocessing
pipeline (imputers + one-hot encoders) AND the estimator — and this
script verifies the packaged objects reproduce the recorded E11 test
metrics before writing anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ML_OUT = HERE / "ml"
GOAL_FILES = HERE.parent
sys.path.insert(0, str(GOAL_FILES / "training_stage" / "ml"))
sys.path.insert(0, str(GOAL_FILES / "optimization_stage" / "ml"))
from train import (FEATURES, LOG_CLIP_HI, TARGET, compute_metrics,  # noqa: E402
                   load_data, make_splits)
from common import fit_variant, predict_any  # noqa: E402
from finalize import best_iter_of, freeze_iters  # noqa: E402

OPT = GOAL_FILES / "optimization_stage" / "ml"
CHAMP = json.loads((OPT / "artifacts" / "champion.json").read_text())
LOG = pd.read_csv(OPT / "experiment_log.csv")

ORIGIN = {
    "POSTED_BY": "listing attribute", "UNDER_CONSTRUCTION": "listing attribute",
    "RERA": "listing attribute", "BHK_NO.": "listing attribute",
    "BHK_OR_RK": "listing attribute", "SQUARE_FT": "listing attribute",
    "RESALE": "listing attribute", "LATITUDE": "listing attribute",
    "LONGITUDE": "listing attribute",
    "CITY": "derived from ADDRESS by the preprocessing stage",
    "LOCALITY": "derived from ADDRESS by the preprocessing stage",
    "SQUARE_FT_PER_BHK": "engineered by the preprocessing stage",
    "LOG_SQUARE_FT": "engineered by the preprocessing stage",
    "DIST_TO_CITY_CENTROID": "engineered by the preprocessing stage (train-fitted city centroids)",
    "CITY_FREQ": "engineered by the preprocessing stage (train-fitted frequency)",
    "LOCALITY_FREQ": "engineered by the preprocessing stage (train-fitted frequency)",
    "SQFT_BAND": "engineered by the preprocessing stage",
    "BHK_CONFIG": "engineered by the preprocessing stage",
    "GEO_CLUSTER": "engineered by the preprocessing stage (train-fitted KMeans, experimental)",
    "LAT_LON_INTERACTION": "engineered by the preprocessing stage (experimental)",
}
CATEGORICAL = {"POSTED_BY", "BHK_OR_RK", "CITY", "LOCALITY", "SQFT_BAND",
               "BHK_CONFIG", "GEO_CLUSTER"}
BINARY = {"UNDER_CONSTRUCTION", "RERA", "RESALE"}


def main() -> None:
    assert CHAMP["champion"] == "E01", CHAMP["champion"]
    e01 = LOG[LOG.experiment_id == "E01"].iloc[0]
    params = json.loads(e01["hyperparameters"])
    bi = best_iter_of(LOG, "E01")
    frozen = freeze_iters("xgboost", params, bi)
    print(f"E01 params frozen at {bi} iterations: {frozen}")

    df = load_data()
    train, valid, test, _ = make_splits(df)
    trva = pd.concat([train, valid], ignore_index=True)
    prep, model, tt, _ = fit_variant(
        "xgboost", "tree", frozen, trva[FEATURES],
        np.log1p(trva[TARGET].to_numpy()))
    # Verify the packaged objects reproduce the recorded E11 test metrics.
    pred_test = predict_any(prep, model, test[FEATURES])
    m = compute_metrics(test[TARGET].to_numpy(), pred_test)
    ref = CHAMP["test"]
    print(f"packaged test: R2={m['r2']:.4f} RMSE=₹{m['rmse_lacs']:.2f}L | "
          f"E11 record: R2={ref['r2']:.4f} RMSE=₹{ref['rmse_lacs']:.2f}L")
    assert abs(m["rmse_lacs"] - ref["rmse_lacs"]) < 0.05, "packaged model diverges from E11"
    assert abs(m["r2"] - ref["r2"]) < 0.002, "packaged model diverges from E11"

    artifact = {"kind": "single", "model_name": "xgboost", "prep": prep,
                "model": model, "features": FEATURES,
                "target_transform": "log1p", "log_clip_hi": LOG_CLIP_HI,
                "hyperparameters": frozen, "best_iteration": bi,
                "source_experiment": "optimization_stage E01 (Optuna best)"}
    joblib.dump(artifact, ML_OUT / "model.pkl")

    # ---- feature_schema.json -------------------------------------------
    categories: dict[str, list] = {}
    for name, transformer, cols in prep.transformers_:
        if not hasattr(transformer, "named_steps"):
            continue
        enc = transformer.named_steps.get("onehot")
        if enc is not None and hasattr(enc, "categories_"):
            for col, cats in zip(cols, enc.categories_):
                categories[col] = [str(c) for c in cats]
    features_doc = []
    for i, f in enumerate(FEATURES):
        kind = ("categorical" if f in CATEGORICAL else
                "binary" if f in BINARY else "numeric")
        entry = {"position": i, "name": f, "kind": kind, "origin": ORIGIN[f],
                 "required": True}
        if f in categories:
            entry["known_levels"] = categories[f]
            entry["unseen_levels"] = "accepted (encoder handle_unknown='ignore')"
        if f == "DIST_TO_CITY_CENTROID":
            entry["nullable"] = True
        features_doc.append(entry)
    schema = {"schema_version": "1.0.0-packaged-model",
              "feature_order": FEATURES, "features": features_doc,
              "target": {"name": TARGET, "unit": "Indian lakh (₹ lakh)",
                         "transform": "log1p",
                         "inverse_transform": "expm1",
                         "log_clip_upper": LOG_CLIP_HI},
              "input_contract_note": "Inputs are the 20 model-ready "
              "features produced by the preprocessing stage; raw listing "
              "attributes alone are not sufficient because CITY/LOCALITY "
              "and the engineered features are derived upstream."}
    (ML_OUT / "feature_schema.json").write_text(json.dumps(schema, indent=2))

    # ---- model_metadata.json -------------------------------------------
    metadata = {
        "model": {"name": "XGBoost Regressor (Optuna-tuned, experiment E01)",
                  "library": "xgboost", "library_version": "3.0.5",
                  "kind": "single",
                  "hyperparameters": frozen, "best_iteration": bi,
                  "preprocessing": "ColumnTransformer fitted on the "
                  "training data of this stage: median imputation for "
                  "numerics, most-frequent for binary/categorical, "
                  "one-hot encoding (LOCALITY with min_frequency=25), "
                  "no scaling (tree model)"},
        "training": {"fitted_on": "train + validation partitions "
                     "(24,328 rows) with hyperparameters and iteration "
                     "count frozen from validation-based selection",
                     "data": "preprocessing stage model_ready_dataset.csv "
                     "(28,622 rows, 20 engineered features)",
                     "split_protocol": "grouped 70/15/15 by feature "
                     "signature, seed 42 (train 20,037 / validation 4,301 "
                     "/ test 4,284; zero signature overlap)",
                     "target_transform": "log1p (inverse: expm1, clipped "
                     "to [0, log1p(50000)] in log space)",
                     "selection_rule": "lowest validation RMSE across all "
                     "optimisation-stage experiments (E01: ₹76.28L vs "
                     "previous winner E00: ₹78.65L; ensemble E09: ₹76.70L)"},
        "metrics": {
            "validation": {"r2": float(e01["valid_r2"]),
                           "mae_lacs": float(e01["valid_mae_lacs"]),
                           "rmse_lacs": float(e01["valid_rmse_lacs"]),
                           "note": "Optuna best trial 14 of 20"},
            "grouped_cv": {"r2_mean": CHAMP["cv_r2_mean"],
                           "r2_std": CHAMP["cv_r2_std"],
                           "folds_r2": [0.8273, 0.8927, 0.7546],
                           "note": "3-fold GroupKFold by feature signature, "
                           "inside the training partition (experiment E10)"},
            "test": {**{k: ref[k] for k in
                        ["r2", "mae_lacs", "mse", "rmse_lacs", "mape_pct",
                         "smape_pct", "explained_variance",
                         "median_ae_lacs", "n"]},
                     "note": "Scored exactly once in the optimisation "
                     "stage (experiment E11), after selection, on the "
                     "untouched grouped test partition; reproduced by "
                     "this packaged artifact at build time."}},
        "environment": {"python": "3.12.3", "numpy": "2.0.2",
                        "pandas": "2.3.3", "scikit_learn": "1.6.1",
                        "xgboost": "3.0.5", "joblib": "1.6.0"},
        "provenance": {"stage": "optimisation stage (post-training "
                       "performance investigation)",
                       "experiment_log": "optimization_stage/ml/experiment_log.csv",
                       "supersedes": "training stage winner (tuned XGBoost, "
                       "validation R² 0.8333, test R² 0.7368)"},
    }
    (ML_OUT / "model_metadata.json").write_text(json.dumps(metadata, indent=2))

    (ML_OUT / "requirements-ml.txt").write_text(
        "# Inference requirements for the packaged valuation model\n"
        "# Model: XGBoost (optimisation-stage experiment E01), Python 3.12.3\n"
        "numpy==2.0.2\npandas==2.3.3\nscikit-learn==1.6.1\n"
        "xgboost==3.0.5\njoblib==1.6.0\n")
    print("Packaged:", *[str(p) for p in sorted(ML_OUT.iterdir())], sep="\n  ")


if __name__ == "__main__":
    main()
