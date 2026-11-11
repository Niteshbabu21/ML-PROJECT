#!/usr/bin/env python3
"""hyperparameter_tuning.py — seeded random search per model.

Method: explicit random-search loop (the RandomizedSearchCV *method*, run
manually). Why not sklearn's RandomizedSearchCV itself: in this project's
Stage-3b smoke tests, its scipy-distribution parameters arrive as numpy
scalars that CatBoost rejects during clone/refit, and it cannot consume
explicit candidate dicts. The manual loop samples with random.Random(42)
into native Python types, so every trial is reproducible and every model —
CatBoost included — clones and refits cleanly. (Optuna is not installed in
the project environment; the loop gives the same search semantics.)

Optimisation target: VALIDATION RMSE (₹ lakh, original scale). The test
partition is never read here. Boosting trials use the validation partition
for early stopping as well — that is standard practice and is exactly why
final selection also weighs the grouped-CV stability from train.py and why
the winner is re-scored once on untouched test data in evaluate.py.

Trials: catboost 14 · xgboost 14 · lightgbm 14 · random_forest 8 ·
linear: none (no hyperparameters; it is the baseline by design).
Every trial — success or failure — is appended to experiment_results.csv.
"""
from __future__ import annotations

import json
import random
import traceback

import numpy as np

from train import (FEATURES, MODELS, TARGET, append_results, compute_metrics,
                   fit_model, load_data, load_metrics, make_splits,
                   predict_lakh, save_metrics)

TRIALS = {"catboost": 14, "xgboost": 14, "lightgbm": 14, "random_forest": 8}
RNG = random.Random(42)


def logu(a: float, b: float) -> float:
    return float(np.exp(RNG.uniform(np.log(a), np.log(b))))


def sample(name: str) -> dict:
    if name == "catboost":
        return {"depth": RNG.randint(4, 10),
                "iterations": 3000,
                "learning_rate": round(logu(0.01, 0.30), 5),
                "l2_leaf_reg": round(RNG.uniform(1.0, 10.0), 3),
                "random_strength": round(RNG.uniform(0.0, 2.0), 3),
                "bagging_temperature": round(RNG.uniform(0.0, 3.0), 3)}
    if name == "xgboost":
        return {"max_depth": RNG.randint(3, 10),
                "n_estimators": 3000,
                "learning_rate": round(logu(0.01, 0.30), 5),
                "subsample": round(RNG.uniform(0.6, 1.0), 3),
                "colsample_bytree": round(RNG.uniform(0.5, 1.0), 3),
                "min_child_weight": RNG.randint(1, 10),
                "reg_alpha": round(logu(0.001, 1.0), 5),
                "reg_lambda": round(RNG.uniform(0.1, 10.0), 3)}
    if name == "lightgbm":
        return {"num_leaves": RNG.randint(15, 255),
                "max_depth": RNG.choice([-1, 4, 6, 8, 10, 12]),
                "n_estimators": 3000,
                "learning_rate": round(logu(0.01, 0.30), 5),
                "feature_fraction": round(RNG.uniform(0.6, 1.0), 3),
                "bagging_fraction": round(RNG.uniform(0.6, 1.0), 3),
                "bagging_freq": RNG.randint(1, 5),
                "min_child_samples": RNG.randint(5, 50),
                "reg_alpha": round(logu(0.001, 1.0), 5),
                "reg_lambda": round(RNG.uniform(0.1, 10.0), 3)}
    if name == "random_forest":
        return {"n_estimators": RNG.choice([200, 300, 400, 600]),
                "max_depth": RNG.choice([None, 10, 16, 24, 32]),
                "min_samples_split": RNG.choice([2, 5, 10, 20]),
                "min_samples_leaf": RNG.choice([1, 2, 4, 8]),
                "max_features": RNG.choice([0.5, 0.7, 0.9, 1.0])}
    raise ValueError(name)


def best_from_csv(name: str) -> dict | None:
    """Best recorded tuning trial for a model, read back from the results
    CSV (the durable record — survives process restarts)."""
    import pandas as pd
    from train import RESULTS_CSV
    if not RESULTS_CSV.exists():
        return None
    res = pd.read_csv(RESULTS_CSV)
    rows = res[(res.phase == "tuning") & (res.model == name)]
    if rows.empty:
        return None
    r = rows.loc[rows["valid_rmse_lacs"].idxmin()]
    bi = r["best_iteration"]
    return {"params": json.loads(r["params"]),
            "best_iteration": int(bi) if pd.notna(bi) else None,
            "valid_rmse": float(r["valid_rmse_lacs"]),
            "valid_r2": float(r["valid_r2"]),
            "valid_mae": float(r["valid_mae_lacs"]),
            "trial": int(r["trial"])}


def main() -> None:
    import pandas as pd
    from train import RESULTS_CSV
    df = load_data()
    train, valid, _test, _info = make_splits(df)
    ytr = np.log1p(train[TARGET].to_numpy())
    yva_log = np.log1p(valid[TARGET].to_numpy())
    yva = valid[TARGET].to_numpy()
    metrics = load_metrics()
    metrics.setdefault("tuning", {})
    # Resume support: trials already in the CSV are skipped, but sample()
    # is still called for them (and its result discarded) so the seeded
    # RNG sequence — and therefore every later trial's parameters — is
    # identical to an uninterrupted run.
    done = set()
    if RESULTS_CSV.exists():
        prev = pd.read_csv(RESULTS_CSV)
        done = {(r.model, int(r.trial)) for r in prev.itertuples()
                if r.phase in ("tuning", "tuning_failed")}
    if done:
        print(f"Resuming: {len(done)} tuning trials already recorded.")
    for name in ["catboost", "xgboost", "lightgbm", "random_forest"]:
        best = None
        for t in range(1, TRIALS[name] + 1):
            params = sample(name)
            if (name, t) in done:
                continue
            try:
                prep, model, t_train, best_iter = fit_model(
                    name, train[FEATURES], ytr, valid[FEATURES], yva_log,
                    params=params)
                pred, clipped = predict_lakh(prep, model, valid[FEATURES])
                m = compute_metrics(yva, pred, t_train)
                row = {"phase": "tuning", "model": name, "trial": t,
                       "params": json.dumps(params),
                       "best_iteration": best_iter,
                       "clipped_predictions": clipped,
                       "cv_r2_mean": None, "cv_r2_std": None,
                       "cv_rmse_mean": None,
                       **{f"valid_{k}": v for k, v in m.items()}}
                print(f"[tuning] {name:14s} #{t:02d} valid R2={m['r2']:.4f} "
                      f"RMSE=₹{m['rmse_lacs']:.2f}L ({t_train:.1f}s)")
                if best is None or m["rmse_lacs"] < best["valid_rmse"]:
                    best = {"params": params, "best_iteration": best_iter,
                            "valid_rmse": m["rmse_lacs"], "valid_r2": m["r2"],
                            "valid_mae": m["mae_lacs"], "trial": t}
            except Exception as exc:  # a failed trial is data, not a crash
                row = {"phase": "tuning_failed", "model": name, "trial": t,
                       "params": json.dumps(params),
                       "best_iteration": None, "clipped_predictions": None,
                       "cv_r2_mean": None, "cv_r2_std": None,
                       "cv_rmse_mean": None,
                       **{f"valid_{k}": None for k in
                          ["r2", "mae_lacs", "mse", "rmse_lacs", "mape_pct",
                           "mape_coverage_pct", "smape_pct",
                           "explained_variance", "median_ae_lacs",
                           "train_time_s", "predict_time_s", "n"]}}
                print(f"[tuning] {name} #{t:02d} FAILED: {exc}")
                traceback.print_exc(limit=1)
            append_results([row])
        # Best-per-model is rebuilt from the durable CSV (covers resumed
        # trials too) and checkpointed after EVERY model, not just at end.
        metrics["tuning"][name] = best_from_csv(name)
        save_metrics(metrics)
        b = metrics["tuning"][name]
        if b:
            print(f"[tuning] BEST {name}: trial {b['trial']} "
                  f"RMSE=₹{b['valid_rmse']:.2f}L R2={b['valid_r2']:.4f}")
    print("Tuning complete; best-per-model recorded in model_metrics.json")


if __name__ == "__main__":
    main()
