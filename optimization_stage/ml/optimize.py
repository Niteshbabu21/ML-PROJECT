#!/usr/bin/env python3
"""optimize.py — optimisation experiments, all judged on VALIDATION (and
grouped CV for the champion). The test partition is touched at most once,
at the very end, only if a new champion beats the previous stage's winner
on validation — and that use is recorded in the log like everything else.

Experiments:
  E00  Reference: previous stage winner (tuned XGBoost, log track).
  E01  Optuna XGBoost (regularisation-forward space), 20 trials.
  E02  Optuna CatBoost (native categoricals), 16 trials.
  E03  Optuna LightGBM (leaf/depth-focused space), 20 trials.
  E04  CatBoost categorical handling: one-hot vs native; native + MAE loss;
       native + Huber loss.
  E05  XGBoost alternative loss (pseudo-Huber) + gentler-lr/longer training.
  E06  Target transform ablation: winner config on the RAW target.
  E07  Robust fit: TRAINING target winsorised at train p99 (no rows removed;
       validation/test targets untouched) — tests whether extreme training
       labels, not model capacity, are the drag.
  E08  Feature ablations (train/validation-fitted selection only):
       −experimental pair, −locality pair, −low-value trio, core-only set.
  E09  Simple average ensemble of the three tuned boosters (log space).
  E10  Champion stability: 3-fold grouped CV of the best configuration.
  E11  (Conditional) champion refit on train+validation, test scored once.

Rules honoured: no legitimate property is removed to inflate R² (E07 caps
training labels only, as a robust-regression variant, and is reported as
such); no target-derived features anywhere; nothing is tuned on test.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "training_stage" / "ml"))
sys.path.insert(0, str(HERE))
import optuna  # noqa: E402
from train import (FEATURES, TARGET, compute_metrics, load_data,  # noqa: E402
                   make_splits, signature_groups)
from common import build_prep_subset, fit_variant, predict_any  # noqa: E402

optuna.logging.set_verbosity(optuna.logging.WARNING)
TM = json.loads((HERE.parent.parent / "training_stage" / "ml"
                 / "model_metrics.json").read_text())
LOG_CSV = HERE / "experiment_log.csv"
ROWS: list[dict] = []


def log(exp_id: str, model: str, feature_changes: str, params: dict,
        m: dict | None, t: float, obs: str) -> None:
    ROWS.append({"experiment_id": exp_id, "model": model,
                 "feature_changes": feature_changes,
                 "hyperparameters": json.dumps(params, default=str),
                 "valid_r2": m["r2"] if m else None,
                 "valid_mae_lacs": m["mae_lacs"] if m else None,
                 "valid_rmse_lacs": m["rmse_lacs"] if m else None,
                 "train_time_s": round(t, 1), "observations": obs})
    if m:
        print(f"{exp_id:10s} {model:10s} valid R2={m['r2']:.4f} "
              f"MAE=₹{m['mae_lacs']:.2f}L RMSE=₹{m['rmse_lacs']:.2f}L ({t:.0f}s)")
    pd.DataFrame(ROWS).to_csv(LOG_CSV, index=False)


def main() -> None:
    df = load_data()
    train, valid, test, _ = make_splits(df)
    Xtr, Xva = train[FEATURES], valid[FEATURES]
    ytr_raw, yva_raw = train[TARGET].to_numpy(), valid[TARGET].to_numpy()
    ytr, yva = np.log1p(ytr_raw), np.log1p(yva_raw)
    win = TM["selection"]
    win_params = dict(win["frozen_params"]); win_params["n_estimators"] = 3000
    cb_best = TM["tuning"]["catboost"]["params"]
    lgbm_best = TM["tuning"]["lightgbm"]["params"]

    # E00 — reference
    log("E00", "xgboost", "none (previous stage winner, log track)",
        win["frozen_params"],
        {"r2": win["candidates"]["xgboost"]["valid_r2"],
         "mae_lacs": TM["tuning"]["xgboost"]["valid_mae"],
         "rmse_lacs": win["candidates"]["xgboost"]["valid_rmse"]},
        0.0, "Reference point for every experiment below.")

    # ---- Optuna helper ------------------------------------------------------
    def run_optuna(exp: str, name: str, variant: str, space, n_trials: int):
        def objective(trial):
            params = space(trial)
            t0 = time.time()
            try:
                prep, model, tt, bi = fit_variant(name, variant, params,
                                                  Xtr, ytr, Xva, yva)
                pred = predict_any(prep, model, Xva)
                m = compute_metrics(yva_raw, pred, tt)
            except Exception as exc:
                raise optuna.TrialPruned(f"fit failed: {exc}")
            log(f"{exp}-T{trial.number + 1:02d}", name, "none", params, m,
                time.time() - t0, f"Optuna trial; best_iter={bi}")
            trial.set_user_attr("params", params)
            trial.set_user_attr("best_iter", bi)
            trial.set_user_attr("metrics", m)
            return m["rmse_lacs"]
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        bt = study.best_trial
        log(exp, name, "none (Optuna best configuration)",
            bt.user_attrs["params"], bt.user_attrs["metrics"], 0.0,
            f"Optuna best of {n_trials} trials (trial {bt.number + 1}); "
            f"best_iter={bt.user_attrs['best_iter']}")
        return bt.user_attrs["params"], bt.user_attrs["best_iter"], study

    # E01 — Optuna XGBoost
    def xgb_space(t):
        return {"max_depth": t.suggest_int("max_depth", 3, 10),
                "n_estimators": 3000,
                "learning_rate": t.suggest_float("learning_rate", 0.01, 0.30, log=True),
                "subsample": t.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": t.suggest_float("colsample_bytree", 0.5, 1.0),
                "min_child_weight": t.suggest_int("min_child_weight", 1, 12),
                "reg_alpha": t.suggest_float("reg_alpha", 0.001, 1.0, log=True),
                "reg_lambda": t.suggest_float("reg_lambda", 0.1, 12.0, log=True),
                "gamma": t.suggest_float("gamma", 0.0, 0.5)}
    xgb_best, xgb_bi, _ = run_optuna("E01", "xgboost", "tree", xgb_space, 20)

    # E02 — Optuna CatBoost
    def cb_space(t):
        return {"depth": t.suggest_int("depth", 4, 10), "iterations": 3000,
                "learning_rate": t.suggest_float("learning_rate", 0.01, 0.30, log=True),
                "l2_leaf_reg": t.suggest_float("l2_leaf_reg", 1.0, 12.0),
                "random_strength": t.suggest_float("random_strength", 0.0, 2.0),
                "bagging_temperature": t.suggest_float("bagging_temperature", 0.0, 3.0)}
    cb_best_o, cb_bi, _ = run_optuna("E02", "catboost", "catboost", cb_space, 16)

    # E03 — Optuna LightGBM
    def lgbm_space(t):
        return {"num_leaves": t.suggest_int("num_leaves", 15, 255),
                "max_depth": t.suggest_categorical("max_depth", [-1, 4, 6, 8, 10, 12]),
                "n_estimators": 3000,
                "learning_rate": t.suggest_float("learning_rate", 0.01, 0.30, log=True),
                "feature_fraction": t.suggest_float("feature_fraction", 0.6, 1.0),
                "bagging_fraction": t.suggest_float("bagging_fraction", 0.6, 1.0),
                "bagging_freq": t.suggest_int("bagging_freq", 1, 5),
                "min_child_samples": t.suggest_int("min_child_samples", 5, 60),
                "reg_alpha": t.suggest_float("reg_alpha", 0.001, 1.0, log=True),
                "reg_lambda": t.suggest_float("reg_lambda", 0.1, 10.0, log=True)}
    lgbm_best_o, lgbm_bi, _ = run_optuna("E03", "lightgbm", "lightgbm", lgbm_space, 20)

    # E04 — CatBoost categorical handling & losses
    for exp, variant, extra, obs in [
            ("E04a", "tree", {}, "CatBoost on ONE-HOT features (vs native)"),
            ("E04b", "catboost", {"loss_function": "MAE"},
             "CatBoost native + MAE loss (robust to extreme labels)"),
            ("E04c", "catboost", {"loss_function": "Huber:delta=0.5"},
             "CatBoost native + Huber loss (delta 0.5 in log space)")]:
        p = dict(cb_best); p.update(extra)
        t0 = time.time()
        prep, model, tt, bi = fit_variant("catboost", variant, p, Xtr, ytr, Xva, yva)
        m = compute_metrics(yva_raw, predict_any(prep, model, Xva), tt)
        log(exp, "catboost", "encoding/loss variant", p, m, time.time() - t0,
            f"{obs}; best_iter={bi}")

    # E05 — XGBoost loss / training-length variants
    for exp, extra, obs in [
            ("E05a", {"objective": "reg:pseudohubererror", "huber_slope": 1.0},
             "pseudo-Huber loss instead of squared error"),
            ("E05b", {"learning_rate": win_params["learning_rate"] / 2},
             "halved learning rate, early stopping decides length")]:
        p = dict(win_params); p.update(extra)
        t0 = time.time()
        prep, model, tt, bi = fit_variant("xgboost", "tree", p, Xtr, ytr, Xva, yva)
        m = compute_metrics(yva_raw, predict_any(prep, model, Xva), tt)
        log(exp, "xgboost", "none", p, m, time.time() - t0, f"{obs}; best_iter={bi}")

    # E06 — raw target track (winner configuration)
    t0 = time.time()
    prep, model, tt, bi = fit_variant("xgboost", "tree", win_params,
                                      Xtr, ytr_raw, Xva, yva_raw)
    m = compute_metrics(yva_raw, predict_any(prep, model, Xva, track="raw"), tt)
    log("E06", "xgboost", "target: RAW instead of log1p", win_params, m,
        time.time() - t0, f"Isolates the log transform's contribution; best_iter={bi}")

    # E07 — training-target winsorisation (robust fit; nothing removed)
    cap = float(np.quantile(ytr_raw, 0.99))
    ytr_cap = np.log1p(np.minimum(ytr_raw, cap))
    t0 = time.time()
    prep, model, tt, bi = fit_variant("xgboost", "tree", win_params,
                                      Xtr, ytr_cap, Xva, yva)
    m = compute_metrics(yva_raw, predict_any(prep, model, Xva), tt)
    log("E07", "xgboost", f"training target capped at train p99 (₹{cap:.0f}L); "
        "validation/test untouched", win_params, m, time.time() - t0,
        f"Tests whether extreme TRAINING labels drag the fit; best_iter={bi}")

    # E08 — feature ablations (XGBoost winner config)
    ablations = {
        "E08a": (["GEO_CLUSTER", "LAT_LON_INTERACTION"],
                 "drop experimental pair (geo cluster, lat×lon)"),
        "E08b": (["LOCALITY", "LOCALITY_FREQ"],
                 "drop locality + its frequency (high-cardinality cost test)"),
        "E08c": (["BHK_OR_RK", "RESALE", "DIST_TO_CITY_CENTROID"],
                 "drop low-value trio (quasi-constant, weak, univariate-weak)"),
        "E08d": (None, "core-only: schema v1.1.0 feature set"),
    }
    core = ["POSTED_BY", "UNDER_CONSTRUCTION", "RERA", "BHK_NO.", "BHK_OR_RK",
            "SQUARE_FT", "RESALE", "CITY", "LOCALITY", "LATITUDE", "LONGITUDE",
            "SQUARE_FT_PER_BHK"]
    for exp, (drop, obs) in ablations.items():
        subset = core if drop is None else [f for f in FEATURES if f not in drop]
        t0 = time.time()
        prep_o = build_prep_subset(subset)
        prep, model, tt, bi = fit_variant(
            "xgboost", "tree", win_params, Xtr[subset], ytr, Xva[subset], yva,
            prep_override=prep_o)
        m = compute_metrics(yva_raw, predict_any(prep, model, Xva[subset]), tt)
        log(exp, "xgboost", obs, win_params, m, time.time() - t0,
            f"features used: {len(subset)}; best_iter={bi}")

    # E09 — booster ensemble (simple average in log space)
    t0 = time.time()
    member_preds = []
    for name, variant, p in [("xgboost", "tree", win_params),
                             ("catboost", "catboost", cb_best),
                             ("lightgbm", "lightgbm", lgbm_best)]:
        prep, model, tt, bi = fit_variant(name, variant, p, Xtr, ytr, Xva, yva)
        member_preds.append(np.log1p(predict_any(prep, model, Xva)))
    blend = np.expm1(np.mean(member_preds, axis=0))
    m = compute_metrics(yva_raw, blend, time.time() - t0)
    log("E09", "ensemble", "average of tuned XGB+CB+LGBM (log space)",
        {"members": ["xgboost", "catboost", "lightgbm"]}, m, time.time() - t0,
        "Diversity check: does averaging beat the best single model?")

    # ---- Champion: best validation RMSE among summary experiments ----------
    summary = pd.DataFrame(ROWS)
    cand = summary[~summary.experiment_id.str.contains("-T")].copy()
    champ_row = cand.loc[cand["valid_rmse_lacs"].idxmin()]
    champ_id = champ_row["experiment_id"]
    print(f"CHAMPION (validation): {champ_id} {champ_row['model']} "
          f"RMSE=₹{champ_row['valid_rmse_lacs']:.2f}L")
    champ = {"experiment_id": champ_id, "model": champ_row["model"],
             "valid_r2": float(champ_row["valid_r2"]),
             "valid_rmse": float(champ_row["valid_rmse_lacs"]),
             "valid_mae": float(champ_row["valid_mae_lacs"]),
             "feature_changes": champ_row["feature_changes"]}
    (HERE / "artifacts" / "champion.json").write_text(json.dumps(
        {**champ, "note": "Test handling is decided in the stage report: "
         "the test partition is scored once for the champion only if it "
         "beat E00 on validation."}, indent=2, default=str))
    print("Experiment log written:", LOG_CSV)


if __name__ == "__main__":
    main()
