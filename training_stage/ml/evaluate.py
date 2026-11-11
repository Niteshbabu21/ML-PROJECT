#!/usr/bin/env python3
"""evaluate.py — model selection, ONE test evaluation, geographic
generalisation. Run AFTER train.py and hyperparameter_tuning.py.

SELECTION RULE (fixed in advance): each model's candidate is its best
configuration by validation RMSE (baseline config vs tuned best, compared
fairly on the same validation partition). The winner is the candidate with
the lowest validation RMSE; grouped-CV stability from train.py is reported
alongside and would break a near-tie (< 0.5% RMSE). No model is favoured
for being 'advanced' — the numbers decide.

Then, and only then:
  1. the winner is refit on train+validation with its selected iteration
     count frozen (no early stopping against test, ever);
  2. the untouched test partition is scored EXACTLY ONCE;
  3. geographic generalisation: the winner's configuration is refit on a
     locality-grouped 80% and scored on the held-out 20% of localities —
     properties in places the model has never seen;
  4. the winner artefact (fitted prep + model) is saved for the API stage.
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from train import (ARTIFACTS, FEATURES, TARGET, append_results,
                   compute_metrics, fit_model, load_data, load_metrics,
                   make_splits, predict_lakh, save_metrics)

ITER_PARAM = {"catboost": "iterations", "xgboost": "n_estimators",
              "lightgbm": "n_estimators"}


def candidates(metrics: dict) -> dict:
    """model -> {source, params, valid_rmse, valid_r2, best_iteration}"""
    out = {}
    for name, base in metrics["baselines"].items():
        out[name] = {"source": "baseline", "params": {},
                     "valid_rmse": base["valid_rmse_lacs"],
                     "valid_r2": base["valid_r2"],
                     "best_iteration": base.get("best_iteration"),
                     "cv_r2_mean": base["cv_r2_mean"],
                     "cv_r2_std": base["cv_r2_std"]}
    for name, tuned in metrics.get("tuning", {}).items():
        if tuned and tuned["valid_rmse"] < out[name]["valid_rmse"]:
            out[name] = {"source": "tuned", "params": tuned["params"],
                         "valid_rmse": tuned["valid_rmse"],
                         "valid_r2": tuned["valid_r2"],
                         "best_iteration": tuned.get("best_iteration"),
                         "cv_r2_mean": out[name]["cv_r2_mean"],
                         "cv_r2_std": out[name]["cv_r2_std"]}
    return out


def with_frozen_iterations(name: str, cand: dict) -> dict:
    params = dict(cand["params"])
    if name in ITER_PARAM and cand.get("best_iteration"):
        params[ITER_PARAM[name]] = int(cand["best_iteration"])
    return params


def main() -> None:
    df = load_data()
    train, valid, test, _ = make_splits(df)
    metrics = load_metrics()
    cands = candidates(metrics)
    print("Candidates (validation):")
    for n, c in sorted(cands.items(), key=lambda kv: kv[1]["valid_rmse"]):
        print(f"  {n:14s} [{c['source']:8s}] RMSE=₹{c['valid_rmse']:.2f}L "
              f"R2={c['valid_r2']:.4f} CV R2={c['cv_r2_mean']:.4f}"
              f"±{c['cv_r2_std']:.4f}")
    ranked = sorted(cands.items(), key=lambda kv: kv[1]["valid_rmse"])
    winner, wc = ranked[0]
    # near-tie rule: within 0.5% RMSE, prefer the more CV-stable candidate
    near = [kv for kv in ranked
            if kv[1]["valid_rmse"] <= wc["valid_rmse"] * 1.005]
    if len(near) > 1:
        stable = max(near, key=lambda kv: kv[1]["cv_r2_mean"]
                     - kv[1]["cv_r2_std"])
        if stable[0] != winner:
            print(f"Near-tie on validation RMSE; CV stability selects "
                  f"{stable[0]} over {winner}")
            winner, wc = stable
    print(f"WINNER: {winner} ({wc['source']})")
    params = with_frozen_iterations(winner, wc)

    # Chart refit on train only (same config as the winning trial) for
    # validation predictions used by model_comparison.py.
    ytr = np.log1p(train[TARGET].to_numpy())
    prep_v, model_v, _, _ = fit_model(
        winner, train[FEATURES], ytr, valid[FEATURES],
        np.log1p(valid[TARGET].to_numpy()),
        params=dict(wc["params"]) if wc["source"] == "tuned" else {})
    pred_valid, _ = predict_lakh(prep_v, model_v, valid[FEATURES])

    # 1+2 — refit on train+validation, score test exactly once.
    both = pd.concat([train, valid], ignore_index=True)
    prep_f, model_f, t_train, _ = fit_model(
        winner, both[FEATURES], np.log1p(both[TARGET].to_numpy()),
        params=params)
    pred_test, clipped = predict_lakh(prep_f, model_f, test[FEATURES])
    m_test = compute_metrics(test[TARGET].to_numpy(), pred_test, t_train)
    print(f"TEST (once): R2={m_test['r2']:.4f} MAE=₹{m_test['mae_lacs']:.2f}L "
          f"RMSE=₹{m_test['rmse_lacs']:.2f}L MAPE={m_test['mape_pct']:.1f}%")

    # 3 — geographic generalisation (unseen localities)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    gtr_i, gte_i = next(gss.split(df, groups=df["LOCALITY"]))
    gtr, gte = df.iloc[gtr_i], df.iloc[gte_i]
    prep_g, model_g, _, _ = fit_model(
        winner, gtr[FEATURES], np.log1p(gtr[TARGET].to_numpy()),
        params=params)
    pred_g, _ = predict_lakh(prep_g, model_g, gte[FEATURES])
    m_grp = compute_metrics(gte[TARGET].to_numpy(), pred_g)
    print(f"GROUPED (unseen localities, {gte['LOCALITY'].nunique()} places): "
          f"R2={m_grp['r2']:.4f} MAE=₹{m_grp['mae_lacs']:.2f}L "
          f"RMSE=₹{m_grp['rmse_lacs']:.2f}L")

    # 4 — artefact + records
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"prep": prep_f, "model": model_f, "model_name": winner,
                 "features": FEATURES, "params": params,
                 "input_form": "model_ready engineered features "
                               "(preprocessing stage output)"},
                ARTIFACTS / "winner_model.pkl")
    np.savez(ARTIFACTS / "winner_predictions.npz",
             y_valid=valid[TARGET].to_numpy(), pred_valid=pred_valid,
             y_test=test[TARGET].to_numpy(), pred_test=pred_test,
             y_grouped=gte[TARGET].to_numpy(), pred_grouped=pred_g)
    append_results([
        {"phase": "final_test", "model": winner, "trial": 0,
         "params": json.dumps(params), "best_iteration": wc.get("best_iteration"),
         "clipped_predictions": clipped, "cv_r2_mean": None,
         "cv_r2_std": None, "cv_rmse_mean": None,
         **{f"valid_{k}": v for k, v in m_test.items()}},
        {"phase": "grouped_generalisation", "model": winner, "trial": 0,
         "params": json.dumps(params), "best_iteration": wc.get("best_iteration"),
         "clipped_predictions": None, "cv_r2_mean": None, "cv_r2_std": None,
         "cv_rmse_mean": None,
         **{f"valid_{k}": v for k, v in m_grp.items()}},
    ])
    metrics["selection"] = {"winner": winner, "candidate_source": wc["source"],
                            "rule": "lowest validation RMSE; near-tie (<0.5%) "
                                    "broken by grouped-CV stability",
                            "candidates": cands, "frozen_params": params}
    metrics["test"] = m_test
    metrics["grouped_generalisation"] = {
        **m_grp, "unseen_localities": int(gte["LOCALITY"].nunique()),
        "grouped_train_rows": int(len(gtr)), "grouped_test_rows": int(len(gte))}
    save_metrics(metrics)
    print("Saved winner artefact, predictions, test + grouped metrics.")


if __name__ == "__main__":
    main()
