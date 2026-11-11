#!/usr/bin/env python3
"""preprocessing.py — per-model-family preprocessing pipelines + dataset build.

Pipeline variants (ALL fitted on training data only; the split happens
BEFORE any fitting — see main()):
  tree     — Random Forest / XGBoost / HistGradientBoosting style:
             median-impute numerics (NO scaling — tree splits don't need it),
             most-frequent-impute binaries, one-hot categoricals
             (handle_unknown='ignore'), locality one-hot with
             min_frequency=25 and 'Unknown' for missing.
  linear   — Linear/Ridge/ElasticNet: identical to `tree` PLUS
             StandardScaler on numerics (fitted on train). Scaling is applied
             ONLY here, where the algorithm actually requires it.
  catboost — native categorical handling: engineered frame with categorical
             columns cast to pandas 'category' using TRAIN-fitted category
             sets; unseen categories map to a fitted fallback ('Other' for
             CITY, 'Unknown' for LOCALITY, train mode elsewhere) instead of
             inventing a new category; numerics median-imputed.
  lightgbm — same native representation as catboost (LightGBM consumes
             pandas category dtype directly).

The same `build_pipeline(variant)` object is what a future Flask service
loads and calls — training and inference share this exact code path.

Target handling: the target is never a pipeline input. Skew is addressed
with a log1p target transform at the modelling layer (helpers below);
metrics are always reported after inverse-transforming to ₹ lakh.

Running this file builds the stage artefacts:
  dataset/processed/model_ready_dataset.csv  (engineered, interpretable
      form + TARGET + SPLIT; encoders stay in the pipelines, not the CSV)
  ml/preprocessing_config.json               (measured fit record)
  dataset/reports/feature_selection.json     (via feature_selection.py)
  dataset/reports/feature_dictionary.md      (from ml/feature_schema.json)
  dataset/reports/preprocessing_report.md

Usage:
  python ml/preprocessing.py [--input ../eda_stage/dataset/processed/cleaned_dataset.csv]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from feature_engineering import (BINARY_FEATURES, CATEGORICAL_FEATURES,
                                 ENGINEERED_FEATURES, LOCALITY_FEATURE,
                                 NUMERIC_FEATURES, TARGET, FeatureEngineer)

REQUIRED_INPUT_COLUMNS = ["POSTED_BY", "UNDER_CONSTRUCTION", "RERA", "BHK_NO.",
                          "BHK_OR_RK", "SQUARE_FT", "RESALE", "ADDRESS",
                          "LATITUDE", "LONGITUDE"]
VARIANTS = ["tree", "linear", "catboost", "lightgbm"]


# --------------------------------------------------------------------------- #
# Input validation (the API boundary reuses exactly this)                     #
# --------------------------------------------------------------------------- #
def validate_input_frame(df: pd.DataFrame) -> None:
    """Raise ValueError with a precise message for structurally invalid input.

    Novel VALUES (a new locality, a new city) are valid — the pipeline maps
    them safely. Structurally impossible values are not.
    """
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    sqft = pd.to_numeric(df["SQUARE_FT"], errors="coerce")
    if (sqft.dropna() <= 0).any():
        raise ValueError("SQUARE_FT must be positive (got <= 0)")
    bhk = pd.to_numeric(df["BHK_NO."], errors="coerce")
    if (bhk.dropna() < 1).any() or (bhk.dropna() > 20).any():
        raise ValueError("BHK_NO. must be between 1 and 20")


# --------------------------------------------------------------------------- #
# Native (CatBoost / LightGBM) preparation                                    #
# --------------------------------------------------------------------------- #
class NativeCategoricalPrep(BaseEstimator, TransformerMixin):
    """Impute + cast categoricals to 'category' with TRAIN-fitted categories.

    Unseen categories never create a new level: CITY -> 'Other',
    LOCALITY -> 'Unknown', other categoricals -> their training mode.
    Numeric medians and categorical modes are fitted on training data only.
    """

    FALLBACKS = {"CITY": "Other", LOCALITY_FEATURE: "Unknown"}

    def fit(self, X: pd.DataFrame, y=None):
        X = X.copy()
        self.num_median_ = X[NUMERIC_FEATURES].median().to_dict()
        self.bin_mode_ = {c: X[c].mode(dropna=True).iloc[0]
                          for c in BINARY_FEATURES}
        self.cat_values_, self.cat_mode_ = {}, {}
        for c in CATEGORICAL_FEATURES + [LOCALITY_FEATURE]:
            vals = X[c].dropna().astype(str)
            self.cat_values_[c] = sorted(vals.unique())
            fb = self.FALLBACKS.get(c)
            if fb and fb not in self.cat_values_[c]:
                self.cat_values_[c].append(fb)
            self.cat_mode_[c] = fb if fb else vals.mode().iloc[0]
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for c in NUMERIC_FEATURES:
            X[c] = X[c].fillna(self.num_median_[c])
        for c in BINARY_FEATURES:
            X[c] = X[c].fillna(self.bin_mode_[c])
        for c in CATEGORICAL_FEATURES + [LOCALITY_FEATURE]:
            fb = self.cat_mode_[c]
            X[c] = X[c].astype(object).where(X[c].notna(), fb)
            X[c] = X[c].astype(str).where(X[c].isin(self.cat_values_[c]), fb)
            X[c] = pd.Categorical(X[c], categories=self.cat_values_[c])
        return X[ENGINEERED_FEATURES]

    def get_feature_names_out(self, input_features=None):
        return np.array(ENGINEERED_FEATURES, dtype=object)


# --------------------------------------------------------------------------- #
# Pipeline factory                                                            #
# --------------------------------------------------------------------------- #
def build_column_transformer(scale_numeric: bool) -> ColumnTransformer:
    numeric_steps: list = [("imputer", SimpleImputer(strategy="median"))]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline(numeric_steps), NUMERIC_FEATURES),
            ("bin", SimpleImputer(strategy="most_frequent"), BINARY_FEATURES),
            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore",
                                         sparse_output=False)),
            ]), CATEGORICAL_FEATURES),
            ("loc", Pipeline([
                ("imputer", SimpleImputer(strategy="constant",
                                          fill_value="Unknown")),
                ("onehot", OneHotEncoder(handle_unknown="ignore",
                                         min_frequency=25,
                                         sparse_output=False)),
            ]), [LOCALITY_FEATURE]),
        ], remainder="drop")


def build_pipeline(variant: str) -> Pipeline:
    """Full pipeline: cleaned rows in -> model-ready representation out."""
    if variant == "tree":
        return Pipeline([("derive", FeatureEngineer()),
                         ("prep", build_column_transformer(False))])
    if variant == "linear":
        return Pipeline([("derive", FeatureEngineer()),
                         ("prep", build_column_transformer(True))])
    if variant in ("catboost", "lightgbm"):
        return Pipeline([("derive", FeatureEngineer()),
                         ("prep", NativeCategoricalPrep())])
    raise ValueError(f"Unknown variant: {variant} (expected {VARIANTS})")


# --------------------------------------------------------------------------- #
# Target transform (modelling layer, never a feature)                         #
# --------------------------------------------------------------------------- #
def log1p_target(y: pd.Series) -> pd.Series:
    return np.log1p(y)


def inverse_log1p_target(y_log: pd.Series) -> pd.Series:
    return np.expm1(y_log)


# --------------------------------------------------------------------------- #
# Stage build                                                                 #
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    default_in = (here.parent.parent / "eda_stage" / "dataset" / "processed"
                  / "cleaned_dataset.csv")
    ap.add_argument("--input", default=str(default_in))
    ap.add_argument("--out-dir", default=str(here.parent / "dataset"))
    ap.add_argument("--config-out", default=str(here / "preprocessing_config.json"))
    args = ap.parse_args()

    from feature_selection import analyze_features  # local, train-only

    df = pd.read_csv(args.input)
    validate_input_frame(df)
    train_idx, test_idx = train_test_split(
        df.index, test_size=0.2, random_state=42, shuffle=True)
    train, test = df.loc[train_idx], df.loc[test_idx]
    print(f"Split BEFORE fitting: train {len(train):,} / test {len(test):,} "
          f"(80/20, seed 42)")

    # Fit the engineer on TRAIN ONLY, then transform everything.
    engineer = FeatureEngineer().fit(train)
    engineered = engineer.transform(df)
    ready = engineered.copy()
    ready[TARGET] = df[TARGET].to_numpy()
    ready["SPLIT"] = np.where(df.index.isin(train_idx), "train", "test")
    out_csv = Path(args.out_dir) / "processed" / "model_ready_dataset.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    ready.to_csv(out_csv, index=False)

    y_train = train[TARGET]
    skew_raw = float(y_train.skew())
    skew_log = float(log1p_target(y_train).skew())

    # Fit every variant on train; record encoded widths (evidence, not models)
    widths = {}
    for v in VARIANTS:
        pipe = build_pipeline(v).fit(train)
        Xt = pipe.transform(train.head(500))
        widths[v] = int(Xt.shape[1]) if not isinstance(Xt, pd.DataFrame) \
            else int(Xt.shape[1])
        if isinstance(Xt, pd.DataFrame):
            widths[v] = len(ENGINEERED_FEATURES)  # native frame: 20 columns

    selection = analyze_features(engineer.transform(train), y_train)
    rep_dir = Path(args.out_dir) / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / "feature_selection.json").write_text(
        json.dumps(selection, indent=2, default=str))

    config = {
        "preprocessing_version": "3.0.0-stage",
        "schema_file": "ml/feature_schema.json",
        "input_cleaned_dataset": str(args.input),
        "rows_in": int(len(df)), "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "split": "train_test_split 80/20 shuffle seed=42, BEFORE any fitting",
        "fitted_on": "training split only",
        "engineer": {
            "kept_cities": engineer.city_categories_,
            "n_city_centroids": len(engineer.centroids_),
            "n_geo_clusters": engineer.n_geo_clusters,
            "city_min_rows": engineer.city_min_rows,
            "centroid_min_rows": engineer.centroid_min_rows,
        },
        "target": {"name": TARGET, "raw_skew_train": skew_raw,
                   "log1p_skew_train": skew_log,
                   "transform": "log1p at modelling layer; metrics on ₹ lakh "
                                "after expm1 inverse",
                   "clipped": False},
        "variants_encoded_width": widths,
        "locality_encoding": "one-hot min_frequency=25 (tree/linear); "
                             "native category with 'Unknown' fallback "
                             "(catboost/lightgbm)",
        "prohibited": ["price_per_sqft or any target-derived feature",
                       "target encoding fitted outside the pipeline",
                       "any statistic fitted on validation/test data"],
    }
    Path(args.config_out).write_text(json.dumps(config, indent=2))

    # Feature dictionary from the schema file
    schema = json.loads((here / "feature_schema.json").read_text())
    lines = ["# Feature Dictionary", "",
             "Every feature in the model-ready dataset and the encoded "
             "pipelines. `Fitted` = the statistic is learned from the "
             "training split only. Target-derived features are prohibited.",
             "", "| Feature | Type | Source | Fitted? | Purpose |",
             "|---|---|---|---|---|"]
    for f in schema["features"]:
        lines.append(f"| {f['name']} | {f['kind']} | {f['source']} | "
                     f"{f['fitted']} | {f['purpose']} |")
    lines += ["", "## Excluded by design", ""]
    for e in schema["excluded"]:
        lines.append(f"- **{e['name']}** — {e['reason']}")
    (rep_dir / "feature_dictionary.md").write_text("\n".join(lines) + "\n")

    kept = [r for r in selection if r["recommendation"] == "keep"]
    flagged = [r for r in selection if r["recommendation"] == "keep_flagged"]
    dropc = [r for r in selection if r["recommendation"] == "drop_candidate"]
    report = [
        "# Preprocessing & Feature Engineering Report", "",
        f"Input: cleaned dataset ({len(df):,} rows, previous EDA stage). "
        f"Split before fitting: train {len(train):,} / test {len(test):,}.",
        f"Kept cities (train-fitted, >= {engineer.city_min_rows} rows): "
        f"{len(engineer.city_categories_)} incl. 'Other'. Geo clusters: "
        f"{engineer.n_geo_clusters} (KMeans on training coordinates).", "",
        "## Target skewness", "",
        f"Train target skew: **{skew_raw:.2f}** raw -> **{skew_log:.2f}** "
        "after log1p. Recommendation: train/evaluate on the log1p track as "
        "primary and report metrics back-transformed to ₹ lakh. The target "
        "itself is never clipped or winsorised (genuine luxury tail — EDA).",
        "", "## Encoded widths per model family (fitted on train)", "",
        "| Variant | Representation | Width |", "|---|---|---|",
    ]
    for v in VARIANTS:
        kind = ("native categorical frame" if v in ("catboost", "lightgbm")
                else "one-hot matrix" + (" + scaling" if v == "linear" else ""))
        report.append(f"| {v} | {kind} | {widths[v]} |")
    report += ["", "## Feature selection (training split only)", "",
               f"Keep: {len(kept)} · Keep flagged: {len(flagged)} · "
               f"Drop candidates: {len(dropc)}", ""]
    for r in selection:
        report.append(f"- **{r['feature']}** — {r['recommendation']}: "
                      f"{r['reason']}")
    report += ["", "Full per-feature statistics: `feature_selection.json`. "
               "Validation probes (missing / unseen / invalid / ordering / "
               "leakage): `ml/validate_preprocessing.py` — results in the "
               "stage delivery message and re-runnable at any time.", ""]
    (rep_dir / "preprocessing_report.md").write_text("\n".join(report) + "\n")
    print(f"Wrote {out_csv} ({len(ready):,} rows), config, selection, "
          f"dictionary, report. Widths: {widths}")


if __name__ == "__main__":
    main()
