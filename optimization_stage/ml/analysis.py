#!/usr/bin/env python3
"""analysis.py — performance investigation of the training stage's results.

Every diagnostic is computed from executed artefacts or fresh fits on the
SAME grouped partitions as the training stage (imported, not re-invented):

  A1  Train vs validation gap per model (tuned configs) — over/underfitting.
  A2  Target skew & extremes per partition; winner residuals by price band.
  A3  Location analysis: winner validation error by city; error vs locality
      frequency (does the model fail where location evidence is thin?).
  A4  Segment performance: BHK band, size band, construction/RERA status.
  A5  Noise ceiling: within-group price variance for feature-identical
      listings — an empirical upper bound on achievable R² for the rows
      concerned, because NO model can distinguish identical inputs.
  A6  Duplicate-leakage quantification: (a) winner performance on
      validation rows that share a repeated-property key with train vs
      those that don't; (b) the same winner configuration refit on a
      PLAIN RANDOM split — the validation inflation duplicates would have
      caused without grouped splitting.
  A7  Learning curve (winner config, 25/50/75/100% of train): is the model
      data-starved (more data would help) or at the noise ceiling?

Outputs: ml/artifacts/analysis.json, visualizations/figA*.png
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "training_stage" / "ml"))
from train import (FEATURES, TARGET, compute_metrics, fit_model, load_data,  # noqa: E402
                   make_splits, predict_lakh)
sys.path.insert(0, str(HERE))
from common import fit_variant  # noqa: E402

TRAIN_METRICS = (HERE.parent.parent / "training_stage" / "ml"
                 / "model_metrics.json")
VIZ = HERE / "visualizations"
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.3,
                     "font.size": 9})


def main() -> None:
    VIZ.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    tm = json.loads(TRAIN_METRICS.read_text())
    df = load_data()
    train, valid, test, _ = make_splits(df)
    ytr_log = np.log1p(train[TARGET].to_numpy())
    yva = valid[TARGET].to_numpy()

    # Winner predictions (training stage artefacts)
    wz = np.load(HERE.parent.parent / "training_stage" / "ml" / "artifacts"
                 / "winner_predictions.npz")
    pred_valid = wz["pred_valid"]

    # ---- A1 train vs validation gap (tuned configs; linear = baseline) ----
    gaps = {}
    configs = {name: (tm["tuning"][name]["params"] if name in tm.get("tuning", {})
                      and tm["tuning"][name] else {})
               for name in ["linear", "random_forest", "catboost", "xgboost",
                            "lightgbm"]}
    for name, params in configs.items():
        prep, model, tt, _ = fit_model(name, train[FEATURES], ytr_log,
                                       valid[FEATURES], np.log1p(yva),
                                       params=params)
        ptr, _ = predict_lakh(prep, model, train[FEATURES])
        pva, _ = predict_lakh(prep, model, valid[FEATURES])
        mtr = compute_metrics(train[TARGET].to_numpy(), ptr)
        mva = compute_metrics(yva, pva)
        gaps[name] = {"train_r2": mtr["r2"], "valid_r2": mva["r2"],
                      "train_rmse": mtr["rmse_lacs"],
                      "valid_rmse": mva["rmse_lacs"],
                      "gap_r2": mtr["r2"] - mva["r2"]}
        print(f"A1 {name:14s} train R2={mtr['r2']:.4f} valid R2={mva['r2']:.4f} "
              f"gap={gaps[name]['gap_r2']:.4f}")
    out["A1_train_valid_gap"] = gaps

    # ---- A2 skew / extremes / residual by price band (winner) --------------
    bands = pd.cut(yva, [0, 40, 75, 150, 400, 100000],
                   labels=["<40L", "40-75L", "75-150L", "150-400L", ">400L"])
    seg = pd.DataFrame({"band": bands, "y": yva, "p": pred_valid})
    band_rows = []
    for b, g in seg.groupby("band", observed=True):
        m = compute_metrics(g["y"].to_numpy(), g["p"].to_numpy())
        band_rows.append({"band": str(b), "n": int(len(g)), **m,
                          "bias_lacs": float((g["y"] - g["p"]).mean())})
    out["A2_residual_by_price_band"] = band_rows
    out["A2_target_by_partition"] = {
        part: {"skew": float(d[TARGET].skew()),
               "p99": float(d[TARGET].quantile(0.99)),
               "max": float(d[TARGET].max()), "std": float(d[TARGET].std())}
        for part, d in [("train", train), ("valid", valid), ("test", test)]}
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.bar([r["band"] for r in band_rows],
           [r["mae_lacs"] for r in band_rows], color="#C44E52")
    ax.set_ylabel("MAE ₹ lakh"); ax.set_xlabel("Actual price band")
    ax.set_title("Winner validation MAE by price band")
    fig.tight_layout(); fig.savefig(VIZ / "figA2_mae_by_price_band.png"); plt.close(fig)

    # ---- A3 location analysis ----------------------------------------------
    v = valid.copy(); v["pred"] = pred_valid
    v["ae"] = (v[TARGET] - v["pred"]).abs()
    city_rows = []
    for c, g in v.groupby("CITY"):
        if len(g) >= 100:
            m = compute_metrics(g[TARGET].to_numpy(), g["pred"].to_numpy())
            city_rows.append({"city": c, "n": int(len(g)), **m})
    city_rows.sort(key=lambda r: r["rmse_lacs"], reverse=True)
    out["A3_per_city_validation"] = city_rows
    lf = v.groupby("LOCALITY_FREQ")["ae"].mean()
    out["A3_error_vs_locality_freq"] = {
        "spearman_freq_vs_abs_error": float(
            v[["LOCALITY_FREQ", "ae"]].corr(method="spearman").iloc[0, 1]),
        "mae_unseen_locality_rows": float(
            v.loc[v["LOCALITY_FREQ"] == 0, "ae"].mean())
        if (v["LOCALITY_FREQ"] == 0).any() else None,
        "mae_established_locality_rows": float(
            v.loc[v["LOCALITY_FREQ"] >= 25, "ae"].mean())}
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    top = city_rows[:10]
    ax.barh([r["city"] for r in top][::-1],
            [r["mae_lacs"] for r in top][::-1], color="#4C72B0")
    ax.set_xlabel("MAE ₹ lakh")
    ax.set_title("Winner validation MAE by city (worst 10, n≥100)")
    fig.tight_layout(); fig.savefig(VIZ / "figA3_mae_by_city.png"); plt.close(fig)

    # ---- A4 segment performance ---------------------------------------------
    def seg_metrics(mask_col, labels_map=None):
        rows = []
        for key, g in v.groupby(mask_col):
            if len(g) >= 50:
                m = compute_metrics(g[TARGET].to_numpy(), g["pred"].to_numpy())
                rows.append({"segment": str(key), "n": int(len(g)), **m})
        return rows
    v["BHK_BAND"] = pd.cut(v["BHK_NO."], [0, 1, 2, 3, 4, 20],
                           labels=["1", "2", "3", "4", "5+"])
    out["A4_by_bhk_band"] = seg_metrics("BHK_BAND")
    out["A4_by_sqft_band"] = seg_metrics("SQFT_BAND")
    out["A4_by_under_construction"] = seg_metrics("UNDER_CONSTRUCTION")
    out["A4_by_rera"] = seg_metrics("RERA")

    # ---- A5 noise ceiling from identical inputs ------------------------------
    def ceiling(keys: list[str]) -> dict:
        sub = df[keys + [TARGET]].copy()
        sizes = sub.groupby(keys)[TARGET].transform("size")
        multi = sub[sizes >= 2]
        means = multi.groupby(keys)[TARGET].transform("mean")
        within_ss = float(((multi[TARGET] - means) ** 2).sum())
        total_ss = float(((multi[TARGET] - multi[TARGET].mean()) ** 2).sum())
        return {"keys": keys, "rows_covered": int(len(multi)),
                "coverage_pct": round(100 * len(multi) / len(df), 2),
                "implied_max_r2_on_covered_rows":
                    round(1 - within_ss / total_ss, 4) if total_ss else None}
    out["A5_noise_ceiling"] = {
        "feature_signature": ceiling(FEATURES),
        "property_key": ceiling(["LOCALITY", "CITY", "SQUARE_FT", "BHK_NO."]),
        "note": "For feature-identical rows, the best ANY model can do is "
                "predict the conditional mean; the price variance inside "
                "those groups is irreducible without new attributes."}

    # ---- A6 duplicate leakage quantification ---------------------------------
    prop = ["LOCALITY", "CITY", "SQUARE_FT", "BHK_NO."]
    tr_keys = set(map(tuple, train[prop].to_numpy()))
    has_twin = np.array([tuple(r) in tr_keys for r in valid[prop].to_numpy()])
    out["A6_twin_analysis"] = {
        "valid_rows_with_property_twin_in_train": int(has_twin.sum()),
        "metrics_with_twin": compute_metrics(yva[has_twin], pred_valid[has_twin]),
        "metrics_without_twin": compute_metrics(yva[~has_twin], pred_valid[~has_twin])}
    # (b) plain random split refit of the winner configuration
    wparams = tm["selection"]["frozen_params"]
    tri, vai = train_test_split(df, test_size=0.15, random_state=42)
    tri, vai = tri.reset_index(drop=True), vai.reset_index(drop=True)
    # match the grouped protocol's two-stage sizes approximately: use a
    # 70/15 split of the remainder for a fair validation comparison
    tri2, vai2 = train_test_split(tri, test_size=0.15 / 0.85, random_state=42)
    prep, model, _, _ = fit_variant(
        "xgboost", "tree", dict(wparams, n_estimators=3000),
        tri2[FEATURES].reset_index(drop=True),
        np.log1p(tri2[TARGET].to_numpy()),
        vai2[FEATURES].reset_index(drop=True),
        np.log1p(vai2[TARGET].to_numpy()))
    from train import predict_lakh as _pl
    pr, _ = _pl(prep, model, vai2[FEATURES].reset_index(drop=True))
    m_rand = compute_metrics(vai2[TARGET].to_numpy(), pr)
    out["A6_random_split_comparison"] = {
        "random_split_valid": m_rand,
        "grouped_split_valid_winner_r2": tm["selection"]["candidates"]
            ["xgboost"]["valid_r2"],
        "grouped_split_valid_winner_rmse": tm["selection"]["candidates"]
            ["xgboost"]["valid_rmse"],
        "note": "Same configuration, same approximate sizes; the only "
                "difference is whether feature-identical listings may "
                "straddle train/validation."}
    print(f"A6 random-split valid R2={m_rand['r2']:.4f} vs grouped "
          f"{out['A6_random_split_comparison']['grouped_split_valid_winner_r2']:.4f}")

    # ---- A7 learning curve -----------------------------------------------------
    curve = []
    for frac in [0.25, 0.5, 0.75, 1.0]:
        sub = train.sample(frac=frac, random_state=42).reset_index(drop=True)
        prep, model, tt, _ = fit_variant(
            "xgboost", "tree", dict(wparams, n_estimators=3000),
            sub[FEATURES], np.log1p(sub[TARGET].to_numpy()),
            valid[FEATURES], np.log1p(yva))
        pv, _ = _pl(prep, model, valid[FEATURES])
        m = compute_metrics(yva, pv)
        curve.append({"train_fraction": frac, "train_rows": int(len(sub)),
                      "valid_r2": m["r2"], "valid_rmse": m["rmse_lacs"],
                      "train_time_s": round(tt, 1)})
        print(f"A7 frac={frac}: valid R2={m['r2']:.4f} RMSE=₹{m['rmse_lacs']:.2f}L")
    out["A7_learning_curve"] = curve
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    ax.plot([c["train_rows"] for c in curve], [c["valid_r2"] for c in curve],
            "o-", color="#4C72B0")
    ax.axhline(0.96, color="red", ls="--", lw=1, label="stretch target 0.96")
    ax.set_xlabel("Training rows"); ax.set_ylabel("Validation R²")
    ax.set_title("Learning curve — XGBoost (winner configuration)")
    ax.legend(); fig.tight_layout()
    fig.savefig(VIZ / "figA7_learning_curve.png"); plt.close(fig)

    (HERE / "artifacts" / "analysis.json").write_text(json.dumps(out, indent=2, default=str))
    print("Analysis written to artifacts/analysis.json")


if __name__ == "__main__":
    main()
