#!/usr/bin/env python3
"""feature_selection.py — evidence for keeping, flagging or dropping features.

Runs on the TRAINING SPLIT ONLY (the target may be used to *evaluate* a
feature here — that is supervised selection on train, which is legitimate;
what is prohibited is creating target-derived FEATURES or fitting any
selection statistic on validation/test data).

Per feature it records: kind, cardinality, missing %, dominant-value share,
association with the target (Spearman for numerics; group-median spread for
categoricals), and a recommendation with a reason:
  keep           — use as designed
  keep_flagged   — use, with a documented caveat (quasi-constant, very high
                   cardinality, experimental)
  drop_candidate — evidence says it adds noise/complexity; final decision
                   belongs to the training stage's ablation, not this file
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from feature_engineering import (BINARY_FEATURES, CATEGORICAL_FEATURES,
                                 ENGINEERED_FEATURES, LOCALITY_FEATURE,
                                 NUMERIC_FEATURES, TARGET)


def analyze_features(engineered_train: pd.DataFrame,
                     y_train: pd.Series) -> list[dict]:
    df = engineered_train.copy()
    y = pd.Series(y_train).reset_index(drop=True)
    df = df.reset_index(drop=True)
    overall_median = float(y.median())
    results = []
    for col in ENGINEERED_FEATURES:
        s = df[col]
        row = {"feature": col, "missing_pct": round(100 * s.isna().mean(), 3),
               "cardinality": int(s.nunique(dropna=True))}
        top_share = float(s.value_counts(normalize=True, dropna=True)
                          .iloc[0] * 100) if s.notna().any() else 100.0
        row["top_value_share_pct"] = round(top_share, 2)
        if col in NUMERIC_FEATURES:
            row["kind"] = "numeric"
            pair = pd.DataFrame({"x": pd.to_numeric(s, errors="coerce"),
                                 "y": y}).dropna()
            row["spearman_with_target"] = round(
                float(pair["x"].corr(pair["y"], method="spearman")), 4)
            assoc = abs(row["spearman_with_target"])
        else:
            row["kind"] = "binary" if col in BINARY_FEATURES else "categorical"
            med = y.groupby(s.astype(str)).median()
            row["group_median_spread_ratio"] = round(
                float((med.max() - med.min()) / overall_median), 3) \
                if len(med) > 1 else 0.0
            assoc = row["group_median_spread_ratio"]
        # Recommendation logic (documented thresholds)
        if top_share >= 99.0:
            row["recommendation"] = "keep_flagged"
            row["reason"] = (f"quasi-constant ({top_share:.1f}% one value) — "
                             "near-zero signal expected; retained for schema "
                             "stability, drop if ablation agrees")
        elif col == LOCALITY_FEATURE:
            row["recommendation"] = "keep_flagged"
            row["reason"] = (f"very high cardinality ({row['cardinality']}) — "
                             "encoded with min_frequency=25 / native fallback "
                             "so rare and unseen localities are safe")
        elif col in ("GEO_CLUSTER", "LAT_LON_INTERACTION"):
            row["recommendation"] = "keep_flagged"
            row["reason"] = ("experimental engineered feature — retained for "
                             "the training stage to ablate, not assumed useful")
        elif col in NUMERIC_FEATURES and assoc < 0.02:
            row["recommendation"] = "drop_candidate"
            row["reason"] = (f"near-zero monotone association with target on "
                             f"train (|Spearman| {assoc:.3f})")
        else:
            row["recommendation"] = "keep"
            row["reason"] = (f"train association {assoc:.3f} "
                             f"({'Spearman' if col in NUMERIC_FEATURES else 'median-spread ratio'})")
        results.append(row)
    return results
