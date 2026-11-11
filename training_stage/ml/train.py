#!/usr/bin/env python3
"""train.py — training system core: data, splits, metrics, model factories,
baseline training with grouped cross-validation.

PROTOCOL (fixed before any results are seen):
  * Input: the previous stage's model_ready_dataset.csv (20 engineered
    features + target). Its SPLIT column is IGNORED — this stage makes its
    own 70/15/15 split.
  * Duplicates first: rows that are identical across all 20 model features
    ("signature duplicates" — they arise because ADDRESS is not a feature,
    so distinct listings can collapse to the same feature vector) are used
    as GROUPS for splitting, so no signature can appear in two partitions.
  * Split: two-stage GroupShuffleSplit (seed 42) -> ~70% train / ~15%
    validation / ~15% test. Grouped splitting makes sizes approximate;
    actual sizes are recorded and reported.
  * Target: log1p for every model (train skew after log1p ~0.7 vs ~17 raw);
    all metrics are computed after expm1 back-transform, in ₹ lakh.
    Predictions are clipped to [0, log1p(50000)] in log space as numerical
    hygiene against pathological linear extrapolation; clip counts are
    recorded per model (boosting/tree models are expected to clip ~0 rows).
  * Selection signal: validation RMSE (primary) + 3-fold GroupKFold CV on
    the training partition (stability). The test partition is never touched
    by this file or by tuning — evaluate.py scores it exactly once.
  * Encoders/imputers are the previous stage's objects
    (preprocessing_stage/ml/preprocessing.py), fitted HERE on this stage's
    training partition only. Caveat, stated openly: the engineered
    frequency/centroid/cluster statistics inside model_ready_dataset were
    fitted (unsupervised, target-free) by the previous stage on its own
    80% train split. The geographic-generalisation experiment in
    evaluate.py (unseen localities) is the stricter guard.

MODEL VARIANTS (preprocessing differs by family, as designed last stage):
  linear   -> scaled one-hot pipeline      | catboost -> native categoricals
  rf, xgb  -> unscaled one-hot pipeline    | lightgbm -> native categoricals

Outputs: ml/experiment_results.csv, ml/model_metrics.json,
         ml/artifacts/split_assignment.csv, ml/artifacts/baseline_valid_predictions.npz
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "preprocessing_stage" / "ml"))
from feature_engineering import (BINARY_FEATURES, CATEGORICAL_FEATURES,  # noqa: E402
                                 LOCALITY_FEATURE, NUMERIC_FEATURES, TARGET)
from preprocessing import NativeCategoricalPrep, build_column_transformer  # noqa: E402

FEATURES = ["POSTED_BY", "UNDER_CONSTRUCTION", "RERA", "BHK_NO.", "BHK_OR_RK",
            "SQUARE_FT", "RESALE", "CITY", "LOCALITY", "LATITUDE", "LONGITUDE",
            "SQUARE_FT_PER_BHK", "LOG_SQUARE_FT", "DIST_TO_CITY_CENTROID",
            "CITY_FREQ", "LOCALITY_FREQ", "LAT_LON_INTERACTION", "SQFT_BAND",
            "BHK_CONFIG", "GEO_CLUSTER"]
SEED = 42
LOG_CLIP_HI = float(np.log1p(50_000))
DEFAULT_DATA = (HERE.parent.parent / "preprocessing_stage" / "dataset"
                / "processed" / "model_ready_dataset.csv")
RESULTS_CSV = HERE / "experiment_results.csv"
METRICS_JSON = HERE / "model_metrics.json"
ARTIFACTS = HERE / "artifacts"
VARIANT = {"linear": "linear", "random_forest": "tree", "xgboost": "tree",
           "catboost": "catboost", "lightgbm": "lightgbm"}
MODELS = ["linear", "random_forest", "catboost", "xgboost", "lightgbm"]


# --------------------------------------------------------------------------- #
# Data & splits                                                               #
# --------------------------------------------------------------------------- #
def load_data(path: Path = DEFAULT_DATA) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df[FEATURES + [TARGET]].reset_index(drop=True)


def signature_groups(df: pd.DataFrame) -> pd.Series:
    """Group id per feature-identical row (all 20 model features)."""
    key = df[FEATURES].astype(str).agg("|".join, axis=1)
    return pd.factorize(key)[0]


def duplicate_investigation(df: pd.DataFrame) -> dict:
    sig = df[FEATURES].duplicated(keep=False)
    grp = df[sig].groupby(FEATURES, dropna=False)[TARGET]
    prop = df.duplicated(subset=["LOCALITY", "CITY", "SQUARE_FT", "BHK_NO."],
                         keep=False)
    return {
        "rows": int(len(df)),
        "exact_feature_identical_extra_rows": int(df[FEATURES].duplicated().sum()),
        "rows_in_feature_identical_groups": int(sig.sum()),
        "feature_identical_groups": int(grp.ngroups),
        "groups_with_conflicting_prices": int((grp.nunique() > 1).sum()),
        "rows_in_repeated_property_groups_locality_city_sqft_bhk":
            int(prop.sum()),
        "note": "Exact raw duplicates were removed in the cleaning stage. "
                "Feature-identical rows remain because ADDRESS is not a "
                "feature; they are handled by grouped splitting, and "
                "conflicting-price groups are irreducible label noise.",
    }


def make_splits(df: pd.DataFrame):
    """Grouped 70/15/15 (seed 42). Returns (train, valid, test, info)."""
    groups = signature_groups(df)
    gss1 = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED)
    temp_idx, test_idx = next(gss1.split(df, groups=groups))
    temp = df.iloc[temp_idx]
    gss2 = GroupShuffleSplit(n_splits=1, test_size=0.15 / 0.85,
                             random_state=SEED)
    tr_idx, va_idx = next(gss2.split(temp, groups=groups[temp_idx]))
    train, valid, test = temp.iloc[tr_idx], temp.iloc[va_idx], df.iloc[test_idx]
    # overlap check on the raw signature strings (factorize is per-frame)
    def sigset(part):
        return set(part[FEATURES].astype(str).agg("|".join, axis=1))
    s_tr, s_va, s_te = sigset(train), sigset(valid), sigset(test)
    info = {"train_rows": int(len(train)), "valid_rows": int(len(valid)),
            "test_rows": int(len(test)),
            "signature_overlap_train_valid": len(s_tr & s_va),
            "signature_overlap_train_test": len(s_tr & s_te),
            "signature_overlap_valid_test": len(s_va & s_te),
            "method": "two-stage GroupShuffleSplit on feature-signature "
                      "groups, seed 42, target 70/15/15"}
    return (train.reset_index(drop=True), valid.reset_index(drop=True),
            test.reset_index(drop=True), info)


# --------------------------------------------------------------------------- #
# Metrics (single definitions; everything in ₹ lakh on the original scale)   #
# --------------------------------------------------------------------------- #
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                    train_time: float = 0.0, predict_time: float = 0.0) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.clip(np.asarray(y_pred, dtype=float), 0, None)
    resid = y_true - y_pred
    mse = float(np.mean(resid ** 2))
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    mape_mask = np.abs(y_true) >= 0.01  # ₹1,000 floor; dataset min is 0.25 lakh
    mape = float(np.mean(np.abs(resid[mape_mask] / y_true[mape_mask])) * 100)
    smape = float(np.mean(2 * np.abs(resid)
                          / (np.abs(y_true) + np.abs(y_pred))) * 100)
    return {
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0,
        "mae_lacs": float(np.mean(np.abs(resid))),
        "mse": mse, "rmse_lacs": float(np.sqrt(mse)),
        "mape_pct": mape, "mape_coverage_pct": float(100 * mape_mask.mean()),
        "smape_pct": smape,
        "explained_variance": float(
            1 - np.var(resid) / np.var(y_true)) if np.var(y_true) > 0 else 0.0,
        "median_ae_lacs": float(np.median(np.abs(resid))),
        "train_time_s": round(float(train_time), 2),
        "predict_time_s": round(float(predict_time), 4),
        "n": int(len(y_true)),
    }


def predict_lakh(prep, model, X: pd.DataFrame) -> tuple[np.ndarray, int]:
    Xt = prep.transform(X)
    raw_log = np.asarray(model.predict(Xt), dtype=float)
    clipped = int(((raw_log < 0) | (raw_log > LOG_CLIP_HI)).sum())
    return np.expm1(np.clip(raw_log, 0, LOG_CLIP_HI)), clipped


# --------------------------------------------------------------------------- #
# Preprocessing + model factories                                             #
# --------------------------------------------------------------------------- #
def build_prep(variant: str):
    if variant in ("catboost", "lightgbm"):
        return NativeCategoricalPrep()
    return build_column_transformer(scale_numeric=(variant == "linear"))


def make_model(name: str, params: dict | None = None, seed: int = SEED):
    params = dict(params or {})
    if name == "linear":
        from sklearn.linear_model import LinearRegression
        return LinearRegression()
    if name == "random_forest":
        from sklearn.ensemble import RandomForestRegressor
        base = dict(n_estimators=300, max_depth=None, min_samples_split=2,
                    min_samples_leaf=1, n_jobs=-1, random_state=seed)
        base.update(params)
        return RandomForestRegressor(**base)
    if name == "catboost":
        from catboost import CatBoostRegressor
        base = dict(iterations=1500, depth=6, learning_rate=0.05,
                    l2_leaf_reg=3.0, random_seed=seed, verbose=0,
                    allow_writing_files=False, od_type="Iter", od_wait=200)
        base.update(params)
        return CatBoostRegressor(**base)
    if name == "xgboost":
        from xgboost import XGBRegressor
        base = dict(n_estimators=2000, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8, min_child_weight=1,
                    reg_alpha=0.0, reg_lambda=1.0, random_state=seed,
                    n_jobs=-1, early_stopping_rounds=100)
        base.update(params)
        return XGBRegressor(**base)
    if name == "lightgbm":
        from lightgbm import LGBMRegressor
        base = dict(n_estimators=2000, num_leaves=63, max_depth=-1,
                    learning_rate=0.05, feature_fraction=0.9,
                    bagging_fraction=0.9, bagging_freq=1, random_state=seed,
                    n_jobs=-1, verbose=-1)
        base.update(params)
        return LGBMRegressor(**base)
    raise ValueError(name)


CAT_COLS = CATEGORICAL_FEATURES + [LOCALITY_FEATURE]


def fit_model(name: str, Xtr: pd.DataFrame, ytr_log: np.ndarray,
              Xva: pd.DataFrame | None = None, yva_log: np.ndarray | None = None,
              params: dict | None = None, seed: int = SEED):
    """Fit prep (on Xtr only) + model. Boosting models use the validation
    partition for early stopping when it is provided. Returns
    (prep, model, train_time_s, best_iteration_or_None)."""
    variant = VARIANT[name]
    prep = build_prep(variant)
    t0 = time.time()
    prep.fit(Xtr)
    Xtr_t = prep.transform(Xtr)
    params = dict(params or {})
    if name == "xgboost" and Xva is None:
        # XGBoost raises if early_stopping_rounds is set without an eval
        # set; CV fits therefore use a fixed, capped iteration count.
        params["early_stopping_rounds"] = None
        params.setdefault("n_estimators", 800)
    model = make_model(name, params, seed)
    best_iter = None
    if name == "catboost":
        Xva_t = prep.transform(Xva) if Xva is not None else None
        model.fit(Xtr_t, ytr_log, cat_features=CAT_COLS,
                  eval_set=(Xva_t, yva_log) if Xva is not None else None,
                  use_best_model=Xva is not None)
        bi = model.get_best_iteration()
        best_iter = int(bi if bi is not None and bi >= 0
                        else model.tree_count_)
    elif name == "lightgbm":
        from lightgbm import early_stopping
        Xva_t = prep.transform(Xva) if Xva is not None else None
        callbacks = [early_stopping(100, verbose=False)] if Xva is not None else None
        model.fit(Xtr_t, ytr_log,
                  eval_set=[(Xva_t, yva_log)] if Xva is not None else None,
                  callbacks=callbacks)
        bi = getattr(model, "best_iteration_", None)
        best_iter = int(bi if bi is not None and bi > 0
                        else model.n_estimators)
    elif name == "xgboost":
        Xva_t = prep.transform(Xva) if Xva is not None else None
        model.fit(Xtr_t, ytr_log,
                  eval_set=[(Xva_t, yva_log)] if Xva is not None else None,
                  verbose=False)
        try:
            bi = model.best_iteration  # raises when early stopping unused
        except AttributeError:
            bi = None
        best_iter = int(bi if bi is not None and bi >= 0
                        else model.n_estimators)
    else:
        model.fit(Xtr_t, ytr_log)
    return prep, model, time.time() - t0, best_iter


# --------------------------------------------------------------------------- #
# Experiment bookkeeping                                                      #
# --------------------------------------------------------------------------- #
def append_results(rows: list[dict]) -> None:
    new = pd.DataFrame(rows)
    if RESULTS_CSV.exists():
        old = pd.read_csv(RESULTS_CSV)
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(RESULTS_CSV, index=False)


def load_metrics() -> dict:
    if METRICS_JSON.exists():
        return json.loads(METRICS_JSON.read_text())
    return {}


def save_metrics(m: dict) -> None:
    METRICS_JSON.write_text(json.dumps(m, indent=2, default=str))


def run_baselines() -> None:
    df = load_data()
    dup = duplicate_investigation(df)
    train, valid, test, sinfo = make_splits(df)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    assign = pd.concat([
        train.assign(partition="train"), valid.assign(partition="validation"),
        test.assign(partition="test")])
    assign.to_csv(ARTIFACTS / "split_assignment.csv", index=False)
    print(f"Splits: {sinfo}")
    print(f"Duplicates: {dup}")

    ytr = np.log1p(train[TARGET].to_numpy())
    yva = valid[TARGET].to_numpy()
    groups_tr = signature_groups(train)
    rows, valid_preds = [], {}
    for name in MODELS:
        # --- validation (fit on train, early stopping on validation) ---
        prep, model, t_train, best_iter = fit_model(
            name, train[FEATURES], ytr, valid[FEATURES], np.log1p(yva))
        t0 = time.time()
        pred, clipped = predict_lakh(prep, model, valid[FEATURES])
        t_pred = time.time() - t0
        m = compute_metrics(yva, pred, t_train, t_pred)
        valid_preds[name] = pred
        # --- 3-fold grouped CV inside train (no early stopping set) ---
        cv_r2, cv_rmse = [], []
        gkf = GroupKFold(n_splits=3)
        for tri, tei in gkf.split(train, groups=groups_tr):
            Xf, Xh = train.iloc[tri], train.iloc[tei]
            pf, mf, _, _ = fit_model(name, Xf[FEATURES],
                                     np.log1p(Xf[TARGET].to_numpy()))
            ph, _ = predict_lakh(pf, mf, Xh[FEATURES])
            mm = compute_metrics(Xh[TARGET].to_numpy(), ph)
            cv_r2.append(mm["r2"]); cv_rmse.append(mm["rmse_lacs"])
        row = {"phase": "baseline", "model": name, "trial": 0,
               "params": json.dumps({}), "best_iteration": best_iter,
               "clipped_predictions": clipped,
               "cv_r2_mean": float(np.mean(cv_r2)),
               "cv_r2_std": float(np.std(cv_r2)),
               "cv_rmse_mean": float(np.mean(cv_rmse)),
               **{f"valid_{k}": v for k, v in m.items()}}
        rows.append(row)
        append_results([row])  # checkpoint per model: a later failure
        # must not discard completed models' measured results
        print(f"[baseline] {name:14s} valid R2={m['r2']:.4f} "
              f"RMSE=₹{m['rmse_lacs']:.2f}L CV R2={row['cv_r2_mean']:.4f}"
              f"±{row['cv_r2_std']:.4f} ({t_train:.1f}s)")
    np.savez(ARTIFACTS / "baseline_valid_predictions.npz",
             y_valid=yva, **valid_preds)
    metrics = load_metrics()
    metrics.update({"data": {"rows": int(len(df)), "features": FEATURES,
                             "target": TARGET, "track": "log1p"},
                    "duplicates": dup, "splits": sinfo,
                    "baselines": {r["model"]: r for r in rows}})
    save_metrics(metrics)
    print("Baselines written to experiment_results.csv + model_metrics.json")


if __name__ == "__main__":
    run_baselines()
