#!/usr/bin/env python3
"""shap_visualizations.py — SHAP plots for the packaged model.

Global (over a sample of the data the model was fitted on):
  * shap_beeswarm.png          — canonical SHAP summary beeswarm in the
                                 model's encoded feature space (top 20).
  * shap_source_importance.png — global bar of mean |SHAP| aggregated
                                 to the 20 source features.
  * shap_dependence_<F>.png    — dependence plots (source feature value
                                 vs its aggregated SHAP) for the three
                                 most important numeric source features.

Local:
  * waterfall_for(record, path) — waterfall over the 20 aggregated
    source features for one property; exact by construction, because
    the aggregated contributions sum to the model output.

Run as a script to (re)generate the global plots:
    python shap_visualizations.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shap

import explain as _explain
import predict as _predict

_HERE = Path(__file__).resolve().parent
VIZ = _HERE / "visualizations"
plt.rcParams.update({"figure.dpi": 110, "font.size": 9})


def build_global_plots(sample_frame, out_dir: Path = VIZ) -> dict:
    """Generate the global plots from a model-ready sample frame."""
    out_dir.mkdir(parents=True, exist_ok=True)
    g = _explain.global_shap(sample_frame)

    # Beeswarm in encoded space (the model's actual input space).
    plt.figure()
    shap.plots.beeswarm(g["explanation"], max_display=20, show=False)
    plt.tight_layout()
    beeswarm_path = out_dir / "shap_beeswarm.png"
    plt.savefig(beeswarm_path, bbox_inches="tight"); plt.close("all")

    # Source-feature global importance bar.
    ranking = g["ranking"]
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    names = [f for f, _ in ranking][::-1]
    vals = [v for _, v in ranking][::-1]
    ax.barh(names, vals, color="#4C72B0")
    ax.set_xlabel("mean |SHAP| (log-price units)")
    ax.set_title("Global feature importance — source features (aggregated SHAP)")
    fig.tight_layout()
    bar_path = out_dir / "shap_source_importance.png"
    fig.savefig(bar_path); plt.close(fig)

    # Dependence plots for the top-3 numeric source features.
    dep_paths = []
    numeric = [f for f, _ in ranking
               if f not in {"POSTED_BY", "BHK_OR_RK", "CITY", "LOCALITY",
                           "SQFT_BAND", "BHK_CONFIG", "GEO_CLUSTER",
                           "UNDER_CONSTRUCTION", "RERA", "RESALE"}][:3]
    agg = g["aggregated"]; feats = g["features"]
    for f in numeric:
        j = feats.index(f)
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        ax.scatter(sample_frame[f].to_numpy(dtype=float), agg[:, j],
                   s=6, alpha=0.35, color="#4C72B0")
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_xlabel(f); ax.set_ylabel(f"SHAP for {f} (log-price)")
        ax.set_title(f"Dependence — {f}")
        fig.tight_layout()
        p = out_dir / f"shap_dependence_{f.replace('.', '')}.png"
        fig.savefig(p); plt.close(fig)
        dep_paths.append(p)
    return {"beeswarm": beeswarm_path, "source_importance": bar_path,
            "dependence": dep_paths, "ranking": ranking,
            "base_value": g["base_value"]}


def waterfall_for(property_features: Mapping, out_path: Path) -> Path:
    """Waterfall plot over aggregated source features for one property."""
    frame = _predict._validate(property_features)
    info = _explain.explain_frame(frame)[0]
    row = frame.iloc[0]
    features = list(info["shap_source"].keys())
    values = np.array([info["shap_source"][f] for f in features])
    display = np.array([row[f] for f in features], dtype=object)
    exp = shap.Explanation(values=values, base_values=info["base_value_log"],
                           data=display, feature_names=features)
    plt.figure()
    shap.plots.waterfall(exp, max_display=12, show=False)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, bbox_inches="tight"); plt.close("all")
    return out_path


def _load_sample() -> "pd.DataFrame":  # noqa: F821 - build-time helper
    import pandas as pd
    goal_files = _HERE.parent.parent
    sys.path.insert(0, str(goal_files / "training_stage" / "ml"))
    from train import FEATURES, load_data, make_splits
    df = load_data()
    train, valid, _test, _ = make_splits(df)
    fitted_on = pd.concat([train, valid], ignore_index=True)
    return fitted_on.sample(n=min(2000, len(fitted_on)),
                            random_state=42)[FEATURES]


if __name__ == "__main__":
    sample = _load_sample()
    out = build_global_plots(sample)
    print("base value (log):", round(out["base_value"], 4))
    print("top source features:", [(f, round(v, 3)) for f, v in out["ranking"][:6]])
    for k in ["beeswarm", "source_importance"]:
        print(k, "->", out[k])
    for p in out["dependence"]:
        print("dependence ->", p)
