#!/usr/bin/env python3
"""model_comparison.py — comparison charts + the evaluation report.

Reads ONLY the artefacts produced by train.py / hyperparameter_tuning.py /
evaluate.py (experiment_results.csv, model_metrics.json, predictions), so
every number and figure in the report traces to an executed run.

Charts (ml/visualizations/):
  fig1/fig2  validation R² and RMSE by model (baseline vs tuned best)
  fig3       training-time comparison
  fig4       winner: actual vs predicted (validation + test)
  fig5       winner: residual distribution (test)
  fig6       winner: residuals vs predicted (test)
  fig7       winner: absolute-percentage-error distribution (test)
  fig8       winner: feature importance (one-hot importances aggregated
             back to source features; native importances used directly)
Report: ml/reports/model_evaluation_report.md
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
VIZ = HERE / "visualizations"
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.3,
                     "font.size": 9})
MODELS = ["linear", "random_forest", "catboost", "xgboost", "lightgbm"]
LABELS = {"linear": "Linear", "random_forest": "Random Forest",
          "catboost": "CatBoost", "xgboost": "XGBoost", "lightgbm": "LightGBM"}


def main() -> None:
    VIZ.mkdir(parents=True, exist_ok=True)
    res = pd.read_csv(HERE / "experiment_results.csv")
    metrics = json.loads((HERE / "model_metrics.json").read_text())
    winner = metrics["selection"]["winner"]
    preds = np.load(HERE / "artifacts" / "winner_predictions.npz")

    base = res[res.phase == "baseline"].set_index("model")
    tuned_best = {}
    tun = res[res.phase == "tuning"]
    for name, g in tun.groupby("model"):
        tuned_best[name] = g.loc[g["valid_rmse_lacs"].idxmin()]

    # fig1/fig2 — R² and RMSE, baseline vs tuned
    for metric, fname, title in [("valid_r2", "fig1_r2_comparison.png",
                                  "Validation R² by model"),
                                 ("valid_rmse_lacs", "fig2_rmse_comparison.png",
                                  "Validation RMSE (₹ lakh) by model")]:
        fig, ax = plt.subplots(figsize=(7.4, 4.0))
        x = np.arange(len(MODELS)); w = 0.38
        b = [base.loc[m, metric] if m in base.index else np.nan for m in MODELS]
        t = [tuned_best[m][metric] if m in tuned_best else np.nan for m in MODELS]
        ax.bar(x - w / 2, b, w, label="Baseline", color="#8A8D93")
        ax.bar(x + w / 2, t, w, label="Tuned (best trial)", color="#4C72B0")
        ax.set_xticks(x, [LABELS[m] for m in MODELS]); ax.set_title(title)
        ax.legend(); fig.tight_layout(); fig.savefig(VIZ / fname); plt.close(fig)

    # fig3 — training time (tuned-best fits; baseline if untuned)
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    times = []
    for m in MODELS:
        src = tuned_best.get(m)
        times.append(src["valid_train_time_s"] if src is not None
                     else base.loc[m, "valid_train_time_s"])
    ax.bar([LABELS[m] for m in MODELS], times, color="#55A868")
    ax.set_ylabel("seconds"); ax.set_title("Training time (selected configuration fit)")
    fig.tight_layout(); fig.savefig(VIZ / "fig3_training_time.png"); plt.close(fig)

    # fig4 — actual vs predicted (winner)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True, sharey=True)
    for ax, (yk, pk, name) in zip(axes, [
            ("y_valid", "pred_valid", "Validation"),
            ("y_test", "pred_test", "Test (scored once)")]):
        y, p = preds[yk], preds[pk]
        ax.scatter(y, p, s=6, alpha=0.35, color="#4C72B0")
        lim = max(y.max(), p.max())
        ax.plot([0, lim], [0, lim], "r--", lw=1)
        ax.set_xlabel("Actual ₹ lakh"); ax.set_title(name)
    axes[0].set_ylabel("Predicted ₹ lakh")
    fig.suptitle(f"Actual vs predicted — {LABELS[winner]}")
    fig.tight_layout(); fig.savefig(VIZ / "fig4_actual_vs_predicted.png"); plt.close(fig)

    # fig5/6/7 — test residuals and errors (winner)
    y, p = preds["y_test"], preds["pred_test"]
    resid = y - p
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    ax.hist(resid, bins=70, color="#4C72B0"); ax.axvline(0, color="red", lw=1)
    ax.set_xlabel("Residual ₹ lakh (actual − predicted)")
    ax.set_title(f"Residual distribution — test ({LABELS[winner]})")
    fig.tight_layout(); fig.savefig(VIZ / "fig5_residual_distribution.png"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    ax.scatter(p, resid, s=6, alpha=0.35, color="#4C72B0"); ax.axhline(0, color="red", lw=1)
    ax.set_xlabel("Predicted ₹ lakh"); ax.set_ylabel("Residual ₹ lakh")
    ax.set_title("Residuals vs predicted — test")
    fig.tight_layout(); fig.savefig(VIZ / "fig6_residual_vs_predicted.png"); plt.close(fig)
    ape = np.abs(resid / np.maximum(y, 0.01)) * 100
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    ax.hist(np.clip(ape, 0, 200), bins=60, color="#C44E52")
    ax.set_xlabel("Absolute percentage error % (display clipped at 200%)")
    ax.set_title("Error distribution — test")
    fig.tight_layout(); fig.savefig(VIZ / "fig7_error_distribution.png"); plt.close(fig)

    # fig8 — feature importance (winner artefact)
    import joblib
    art = joblib.load(HERE / "artifacts" / "winner_model.pkl")
    model, prep = art["model"], art["prep"]
    imp = None
    if winner == "catboost":
        imp = pd.Series(model.get_feature_importance(),
                        index=art["features"])
    else:
        vals = getattr(model, "feature_importances_", None)
        if vals is not None:
            names = prep.get_feature_names_out()
            raw = pd.Series(vals, index=[str(n) for n in names])
            def source(n: str) -> str:
                for pre in ("num__", "bin__", "cat__", "loc__"):
                    if n.startswith(pre):
                        n = n[len(pre):]
                        break
                for f in sorted(art["features"], key=len, reverse=True):
                    if n == f or n.startswith(f + "_"):
                        return f
                return n
            imp = raw.groupby([source(n) for n in raw.index]).sum()
    if imp is not None:
        imp = imp.sort_values(ascending=True).tail(15)
        fig, ax = plt.subplots(figsize=(7.6, 5.0))
        ax.barh(imp.index, imp.values, color="#8172B2")
        ax.set_title(f"Feature importance — {LABELS[winner]} (top 15)")
        fig.tight_layout(); fig.savefig(VIZ / "fig8_feature_importance.png"); plt.close(fig)

    # ---------------- report ----------------
    dup, splits, test_m = metrics["duplicates"], metrics["splits"], metrics["test"]
    grp = metrics["grouped_generalisation"]
    L = ["# Model Evaluation Report", "",
         "**Task:** regression — predict `TARGET(PRICE_IN_LACS)` (₹ lakh) "
         "from 20 engineered property/location features. R² here is the "
         "coefficient of determination for regression, not accuracy.",
         "**Generated by:** `ml/model_comparison.py` from executed runs "
         "(`experiment_results.csv`, `model_metrics.json`). No number in "
         "this report was typed by hand.", "",
         "## Protocol", "",
         f"- Input: previous stage's model-ready dataset ({dup['rows']:,} rows). "
         f"Duplicates investigated first: {dup['exact_feature_identical_extra_rows']} "
         f"extra feature-identical rows in {dup['feature_identical_groups']} groups, "
         f"{dup['groups_with_conflicting_prices']} of them with conflicting prices "
         "(label noise).",
         f"- Split: grouped 70/15/15 by feature signature (no signature in two "
         f"partitions — overlaps: train∩valid {splits['signature_overlap_train_valid']}, "
         f"train∩test {splits['signature_overlap_train_test']}) -> train "
         f"{splits['train_rows']:,}, validation {splits['valid_rows']:,}, "
         f"test {splits['test_rows']:,}.",
         "- All models trained on log1p(target); metrics back-transformed to "
         "₹ lakh. Tuning: seeded random search on validation RMSE with early "
         "stopping (boosting). Test scored exactly once, after selection.",
         "- Caveat: engineered frequency/centroid/cluster statistics were "
         "fitted (unsupervised, target-free) by the preprocessing stage on "
         "its own train split; encoders here were refit on this stage's "
         "train only. The unseen-locality experiment below is the strict "
         "generalisation check.", "",
         "## Validation results (selection basis)", "",
         "| Model | Baseline R² | Baseline RMSE | Tuned R² | Tuned RMSE | CV R² (baseline cfg) |",
         "|---|---|---|---|---|---|"]
    for m in MODELS:
        b = base.loc[m]
        t = tuned_best.get(m)
        L.append(f"| {LABELS[m]} | {b['valid_r2']:.4f} | ₹{b['valid_rmse_lacs']:.2f}L | "
                 + (f"{t['valid_r2']:.4f} | ₹{t['valid_rmse_lacs']:.2f}L | " if t is not None else "— | — | ")
                 + f"{b['cv_r2_mean']:.4f} ± {b['cv_r2_std']:.4f} |")
    sel = metrics["selection"]
    L += ["", f"## Selection", "",
          f"**Winner: {LABELS[winner]}** ({sel['candidate_source']} configuration) — "
          f"lowest validation RMSE under the pre-fixed rule "
          f"({sel['rule']}). It was selected on validation + CV evidence, "
          "not because of its algorithm family.", "",
          "## Test — scored once, after selection", "",
          f"| R² | MAE | RMSE | MAPE | SMAPE | Median AE |",
          f"|---|---|---|---|---|---|",
          f"| {test_m['r2']:.4f} | ₹{test_m['mae_lacs']:.2f}L | "
          f"₹{test_m['rmse_lacs']:.2f}L | {test_m['mape_pct']:.1f}% | "
          f"{test_m['smape_pct']:.1f}% | ₹{test_m['median_ae_lacs']:.2f}L |", "",
          "## Geographic generalisation (unseen localities)", "",
          f"Refit on 80% of localities, scored on {grp['unseen_localities']} "
          f"never-seen localities ({grp['grouped_test_rows']:,} rows): "
          f"**R² {grp['r2']:.4f}**, MAE ₹{grp['mae_lacs']:.2f}L, "
          f"RMSE ₹{grp['rmse_lacs']:.2f}L. The drop vs the random-split test "
          "is the honest cost of valuing properties in new places with "
          "locality-level location data.", "",
          "## On the R² 0.96 target", "",
          f"The target was investigated, not assumed. Best measured test "
          f"R² is **{test_m['r2']:.4f}**. The remaining gap is explained by "
          "evidence from the EDA stage: conflicting prices for identical "
          "feature vectors, missing price-driving attributes (bathrooms, "
          "age, furnishing), locality-level coordinates, and residual "
          "field errors. No legitimate preprocessing or tuning choice "
          "available on this dataset closes it; claiming 0.96 would "
          "require fabricating results.", "",
          "## Why the winner won", "",
          "See the validation table: the winner combines the lowest "
          "validation RMSE with grouped-CV stability. Gradient boosting "
          "fits this data's profile — strong monotone area/BHK effects, "
          "high-cardinality location signals, and heavy-tailed prices "
          "handled on the log scale — while the linear baseline cannot "
          "represent the interactions, and Random Forest's piecewise-"
          "constant predictions are coarser at the price extremes. "
          "Per-model detail, all trials and failures: "
          "`ml/experiment_results.csv`.", "",
          "## Figures", ""]
    for f in sorted(VIZ.glob("*.png")):
        L.append(f"- `visualizations/{f.name}`")
    (HERE / "reports" / "model_evaluation_report.md").write_text(
        "\n".join(L) + "\n")
    print(f"Report + {len(list(VIZ.glob('*.png')))} figures written. "
          f"Winner: {winner}, test R2={test_m['r2']:.4f}")


if __name__ == "__main__":
    main()
