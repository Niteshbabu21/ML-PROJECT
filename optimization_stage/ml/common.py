#!/usr/bin/env python3
"""common.py — shared fitting helpers for the optimisation stage.

Extends the training stage's factories with the two things its fit_model
deliberately did not support: (a) choosing the preprocessing variant
independently of the model (e.g. CatBoost on one-hot features, to compare
categorical handling), and (b) a raw-target track (to measure the log
transform's effect honestly). Everything else — data, splits, metrics,
column recipes — is imported from the training stage so protocols match.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "training_stage" / "ml"))
sys.path.insert(0, str(HERE.parent.parent / "preprocessing_stage" / "ml"))
from train import CAT_COLS, LOG_CLIP_HI, build_prep, make_model  # noqa: E402
from feature_engineering import (BINARY_FEATURES, CATEGORICAL_FEATURES,  # noqa: E402
                                 LOCALITY_FEATURE, NUMERIC_FEATURES)


def fit_variant(name: str, variant: str, params: dict | None,
                Xtr: pd.DataFrame, ytr: np.ndarray,
                Xva: pd.DataFrame | None = None, yva: np.ndarray | None = None,
                prep_override=None):
    """Fit prep (train only) + model with early stopping when Xva is given.
    ytr/yva are in the caller's chosen track (log1p or raw). Returns
    (prep, model, train_time_s, best_iteration)."""
    prep = prep_override if prep_override is not None else build_prep(variant)
    t0 = time.time()
    prep.fit(Xtr)
    Xtr_t = prep.transform(Xtr)
    params = dict(params or {})
    if name == "xgboost" and Xva is None:
        params["early_stopping_rounds"] = None
        params.setdefault("n_estimators", 800)
    model = make_model(name, params)
    best_iter = None
    native = isinstance(Xtr_t, pd.DataFrame)
    if name == "catboost":
        Xva_t = prep.transform(Xva) if Xva is not None else None
        model.fit(Xtr_t, ytr, cat_features=CAT_COLS if native else None,
                  eval_set=(Xva_t, yva) if Xva is not None else None,
                  use_best_model=Xva is not None)
        bi = model.get_best_iteration()
        best_iter = int(bi if bi is not None and bi >= 0 else model.tree_count_)
    elif name == "lightgbm":
        from lightgbm import early_stopping
        Xva_t = prep.transform(Xva) if Xva is not None else None
        model.fit(Xtr_t, ytr,
                  eval_set=[(Xva_t, yva)] if Xva is not None else None,
                  callbacks=[early_stopping(100, verbose=False)]
                  if Xva is not None else None)
        bi = getattr(model, "best_iteration_", None)
        best_iter = int(bi if bi is not None and bi > 0 else model.n_estimators)
    elif name == "xgboost":
        Xva_t = prep.transform(Xva) if Xva is not None else None
        model.fit(Xtr_t, ytr, eval_set=[(Xva_t, yva)] if Xva is not None else None,
                  verbose=False)
        try:
            bi = model.best_iteration
        except AttributeError:
            bi = None
        best_iter = int(bi if bi is not None and bi >= 0 else model.n_estimators)
    else:
        model.fit(Xtr_t, ytr)
    return prep, model, time.time() - t0, best_iter


def predict_any(prep, model, X: pd.DataFrame, track: str = "log") -> np.ndarray:
    raw = np.asarray(model.predict(prep.transform(X)), dtype=float)
    if track == "log":
        return np.expm1(np.clip(raw, 0, LOG_CLIP_HI))
    return np.clip(raw, 0, None)


def build_prep_subset(feature_subset: list[str]) -> ColumnTransformer:
    """The training stage's tree (one-hot) recipe restricted to a feature
    subset — used only by the ablation experiments."""
    num = [c for c in NUMERIC_FEATURES if c in feature_subset]
    bin_ = [c for c in BINARY_FEATURES if c in feature_subset]
    cat = [c for c in CATEGORICAL_FEATURES if c in feature_subset]
    transformers = []
    if num:
        transformers.append(("num", Pipeline(
            [("imputer", SimpleImputer(strategy="median"))]), num))
    if bin_:
        transformers.append(("bin", SimpleImputer(strategy="most_frequent"), bin_))
    if cat:
        transformers.append(("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore",
                                     sparse_output=False))]), cat))
    if LOCALITY_FEATURE in feature_subset:
        transformers.append(("loc", Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=25,
                                     sparse_output=False))]), [LOCALITY_FEATURE]))
    return ColumnTransformer(transformers=transformers, remainder="drop")
