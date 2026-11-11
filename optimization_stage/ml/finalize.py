#!/usr/bin/env python3
"""finalize.py — champion stability (E10) and the conditional single test
score (E11).

The champion is whichever summary experiment in experiment_log.csv has the
lowest validation RMSE. Its exact procedure is reconstructed from the log
(same dispatch the experiments used), then:

  E10  3-fold GroupKFold CV (grouped by feature signature, inside train)
       with iteration counts frozen at the champion's validation best —
       the stability evidence for the champion.
  E11  ONLY if the champion beat E00 (the previous stage's winner) on
       validation RMSE: refit on train+validation and score the test
       partition ONCE. Otherwise the test partition is not touched in
       this stage and the previous winner's test score stands.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "training_stage" / "ml"))
sys.path.insert(0, str(HERE))
from train import (FEATURES, TARGET, compute_metrics, load_data,  # noqa: E402
                   make_splits, signature_groups)
from common import build_prep_subset, fit_variant, predict_any  # noqa: E402

TM = json.loads((HERE.parent.parent / "training_stage" / "ml"
                 / "model_metrics.json").read_text())
LOG_CSV = HERE / "experiment_log.csv"
CORE = ["POSTED_BY", "UNDER_CONSTRUCTION", "RERA", "BHK_NO.", "BHK_OR_RK",
        "SQUARE_FT", "RESALE", "CITY", "LOCALITY", "LATITUDE", "LONGITUDE",
        "SQUARE_FT_PER_BHK"]
ABL_DROP = {"E08a": ["GEO_CLUSTER", "LAT_LON_INTERACTION"],
            "E08b": ["LOCALITY", "LOCALITY_FREQ"],
            "E08c": ["BHK_OR_RK", "RESALE", "DIST_TO_CITY_CENTROID"]}


def append_row(row: dict) -> None:
    old = pd.read_csv(LOG_CSV) if LOG_CSV.exists() else pd.DataFrame()
    pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(
        LOG_CSV, index=False)


def best_iter_of(log: pd.DataFrame, exp_id: str) -> int | None:
    rows = log[log.experiment_id == exp_id]
    if rows.empty:
        rows = log[log.experiment_id.str.startswith(exp_id.split("-")[0])
                   & log.experiment_id.str.contains("-T")]
        if rows.empty:
            return None
        rows = rows.loc[[rows.valid_rmse_lacs.idxmin()]]
    m = re.search(r"best_iter=(\d+)", str(rows.iloc[0]["observations"]))
    return int(m.group(1)) if m else None


def freeze_iters(name: str, params: dict, bi: int | None) -> dict:
    """Freeze a boosting model's iteration count at its validation best, so
    CV folds and the train+validation refit do not silently train the full
    3,000-tree cap without early stopping."""
    p = dict(params)
    if bi:
        if name == "catboost":
            p["iterations"] = int(bi)
        else:
            p["n_estimators"] = int(bi)
    return p


def champion_procedure(champ_id: str, log: pd.DataFrame):
    """Return (fit_predict_fn, description). fit_predict_fn(Xtr_df, ytr_raw,
    Xev_df) -> predictions in ₹ lakh on Xev rows."""
    win_params = dict(TM["selection"]["frozen_params"])
    win_params["n_estimators"] = 3000
    champ_bi = best_iter_of(log, champ_id)

    def single(name, variant, params, track="log", cap_y=False, subset=None):
        params = freeze_iters(name, params, champ_bi)
        def fp(Xtr_df, ytr_raw, Xev_df):
            cols = subset or FEATURES
            y = np.minimum(ytr_raw, np.quantile(ytr_raw, 0.99)) if cap_y \
                else ytr_raw
            y_fit = y if track == "raw" else np.log1p(y)
            kw = {}
            if subset is not None:
                kw["prep_override"] = build_prep_subset(subset)
            prep, model, tt, bi = fit_variant(name, variant, params,
                                              Xtr_df[cols], y_fit, **kw)
            return predict_any(prep, model, Xev_df[cols], track=track)
        return fp

    if champ_id == "E00":
        return single("xgboost", "tree", TM["selection"]["frozen_params"]), \
            "previous stage winner configuration"
    if champ_id.startswith("E01"):
        row = log[log.experiment_id.str.startswith("E01-T")].sort_values(
            "valid_rmse_lacs").iloc[0]
        return single("xgboost", "tree", json.loads(row["hyperparameters"])), \
            "Optuna XGBoost best"
    if champ_id.startswith("E02"):
        row = log[log.experiment_id.str.startswith("E02-T")].sort_values(
            "valid_rmse_lacs").iloc[0]
        return single("catboost", "catboost", json.loads(row["hyperparameters"])), \
            "Optuna CatBoost best"
    if champ_id.startswith("E03"):
        row = log[log.experiment_id.str.startswith("E03-T")].sort_values(
            "valid_rmse_lacs").iloc[0]
        return single("lightgbm", "lightgbm", json.loads(row["hyperparameters"])), \
            "Optuna LightGBM best"
    if champ_id.startswith("E04"):
        variant = "tree" if champ_id == "E04a" else "catboost"
        row = log[log.experiment_id == champ_id].iloc[0]
        return single("catboost", variant, json.loads(row["hyperparameters"])), \
            "CatBoost handling/loss variant"
    if champ_id.startswith("E05"):
        row = log[log.experiment_id == champ_id].iloc[0]
        return single("xgboost", "tree", json.loads(row["hyperparameters"])), \
            "XGBoost loss/lr variant"
    if champ_id == "E06":
        return single("xgboost", "tree", win_params, track="raw"), "raw-target XGBoost"
    if champ_id == "E07":
        return single("xgboost", "tree", win_params, cap_y=True), \
            "winsorised-training-target XGBoost"
    if champ_id.startswith("E08"):
        subset = CORE if champ_id == "E08d" else \
            [f for f in FEATURES if f not in ABL_DROP[champ_id]]
        return single("xgboost", "tree", win_params, subset=subset), \
            f"ablation {champ_id}"
    if champ_id == "E09":
        members = [("xgboost", "tree", TM["selection"]["frozen_params"]),
                   ("catboost", "catboost", freeze_iters(
                       "catboost", TM["tuning"]["catboost"]["params"],
                       TM["tuning"]["catboost"]["best_iteration"])),
                   ("lightgbm", "lightgbm", freeze_iters(
                       "lightgbm", TM["tuning"]["lightgbm"]["params"],
                       TM["tuning"]["lightgbm"]["best_iteration"]))]

        def ens(Xtr_df, ytr_raw, Xev_df):
            preds = []
            y = np.log1p(ytr_raw)
            for name, variant, p in members:
                prep, model, tt, bi = fit_variant(name, variant, p,
                                                  Xtr_df[FEATURES], y)
                preds.append(np.log1p(predict_any(prep, model, Xev_df[FEATURES])))
            return np.expm1(np.mean(preds, axis=0))
        return ens, "three-booster average ensemble"
    raise ValueError(f"unknown champion {champ_id}")


def main() -> None:
    log = pd.read_csv(LOG_CSV)
    summary = log[~log.experiment_id.str.contains("-T")
                  & ~log.experiment_id.isin(["E10", "E11"])]
    champ = summary.loc[summary.valid_rmse_lacs.idxmin()]
    champ_id = champ["experiment_id"]
    e00_rmse = float(summary.loc[summary.experiment_id == "E00",
                                 "valid_rmse_lacs"].iloc[0])
    fp, desc = champion_procedure(champ_id, log)
    print(f"Champion: {champ_id} ({desc}) valid RMSE ₹{champ['valid_rmse_lacs']:.2f}L "
          f"vs E00 ₹{e00_rmse:.2f}L")

    df = load_data()
    train, valid, test, _ = make_splits(df)
    groups = signature_groups(train)

    # E10 — grouped CV stability (no early stopping inside folds; the
    # champion's procedure is refit per fold as-is)
    t0 = time.time()
    cv = []
    for tr_idx, va_idx in GroupKFold(3).split(train, groups=groups):
        ftr = train.iloc[tr_idx].reset_index(drop=True)
        fva = train.iloc[va_idx].reset_index(drop=True)
        pred = fp(ftr, ftr[TARGET].to_numpy(), fva)
        cv.append(compute_metrics(fva[TARGET].to_numpy(), pred)["r2"])
    append_row({"experiment_id": "E10", "model": champ["model"],
                "feature_changes": f"grouped 3-fold CV of champion {champ_id}",
                "hyperparameters": champ["hyperparameters"],
                "valid_r2": float(np.mean(cv)), "valid_mae_lacs": None,
                "valid_rmse_lacs": None, "train_time_s": round(time.time() - t0, 1),
                "observations": f"Champion CV R² per fold: "
                                f"{[round(c, 4) for c in cv]} "
                                f"(mean {np.mean(cv):.4f} ± {np.std(cv):.4f})"})
    print(f"E10 CV R2: {[round(c, 4) for c in cv]}")

    result = {"champion": champ_id, "description": desc,
              "valid_rmse": float(champ["valid_rmse_lacs"]),
              "valid_r2": float(champ["valid_r2"]),
              "cv_r2_mean": float(np.mean(cv)), "cv_r2_std": float(np.std(cv)),
              "test_scored_this_stage": False}

    # E11 — conditional single test score
    if float(champ["valid_rmse_lacs"]) < e00_rmse and champ_id != "E00":
        trva = pd.concat([train, valid], ignore_index=True)
        t0 = time.time()
        pred_test = fp(trva, trva[TARGET].to_numpy(), test)
        m = compute_metrics(test[TARGET].to_numpy(), pred_test,
                            time.time() - t0)
        append_row({"experiment_id": "E11", "model": champ["model"],
                    "feature_changes": "champion refit on train+validation; "
                                       "test scored ONCE in this stage",
                    "hyperparameters": champ["hyperparameters"],
                    "valid_r2": m["r2"], "valid_mae_lacs": m["mae_lacs"],
                    "valid_rmse_lacs": m["rmse_lacs"],
                    "train_time_s": round(time.time() - t0, 1),
                    "observations": "TEST (not validation): second use of the "
                                    "test partition overall — once per stage, "
                                    "for that stage's selected model only."})
        result.update({"test_scored_this_stage": True, "test": m})
        print(f"E11 TEST: R2={m['r2']:.4f} MAE=₹{m['mae_lacs']:.2f}L "
              f"RMSE=₹{m['rmse_lacs']:.2f}L")
    else:
        print("E11 skipped: champion did not beat E00 on validation — the "
              "test partition stays untouched in this stage.")
    (HERE / "artifacts" / "champion.json").write_text(json.dumps(result, indent=2))
    print("finalize.py complete")


if __name__ == "__main__":
    main()
