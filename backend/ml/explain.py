#!/usr/bin/env python3
"""explain.py — SHAP explainability core for the packaged valuation model.

The packaged model is an XGBoost tree ensemble, so explanations use
shap.TreeExplainer — the exact, model-specific explainer — applied to
the TRANSFORMED feature matrix produced by the packaged preprocessing
pipeline (the same 258 encoded features the model actually consumes).

Encoded SHAP values are then aggregated back to the 20 source features
by summing each source feature's one-hot columns. Summation is exact
for SHAP: base_value + Σ source contributions == model output (in
log1p space), which this module verifies on every explanation.

Nothing here is hardcoded per property: every number is computed from
the packaged model and the caller's actual input.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import shap

import predict as _predict  # same package: artifact loading + validation

_HERE = Path(__file__).resolve().parent
_CONFIG = json.loads((_HERE / "shap_config.json").read_text())
_EXPLAINER: shap.TreeExplainer | None = None
_SOURCE_MAP: list[str] | None = None


def _artifact() -> dict:
    artifact, _schema = _predict._load()
    return artifact


def get_explainer() -> shap.TreeExplainer:
    """TreeExplainer over the packaged XGBoost estimator (cached)."""
    global _EXPLAINER
    if _EXPLAINER is None:
        _EXPLAINER = shap.TreeExplainer(_artifact()["model"])
    return _EXPLAINER


def base_value() -> float:
    """Explainer expected value (log1p ₹ lakh)."""
    ev = get_explainer().expected_value
    return float(np.asarray(ev).ravel()[0])


def source_feature_map() -> list[str]:
    """For each encoded column (in pipeline output order), the source
    feature it came from.

    Built per transformer block from each fitted transformer's own
    output names, matching the longest input-column prefix. This stays
    correct where a naive len(categories_) count fails: the LOCALITY
    encoder was fitted with min_frequency=25, so it stores 5,285 fitted
    categories but emits only 168 columns (frequent levels plus the
    infrequent bucket)."""
    global _SOURCE_MAP
    if _SOURCE_MAP is not None:
        return _SOURCE_MAP
    prep = _artifact()["prep"]
    mapping: list[str] = []
    for _name, transformer, cols in prep.transformers_:
        if transformer is None or (isinstance(transformer, str)
                                   and transformer == "drop"):
            continue
        cols = list(cols)
        block_names = list(transformer.get_feature_names_out(cols))
        for out_name in block_names:
            tail = str(out_name).split("__")[-1]
            match = None
            for col in cols:
                if tail == col or tail.startswith(col + "_"):
                    if match is None or len(col) > len(match):
                        match = col
            assert match is not None, (out_name, cols)
            mapping.append(match)
    names = list(prep.get_feature_names_out())
    assert len(mapping) == len(names), (len(mapping), len(names))
    _SOURCE_MAP = mapping
    return mapping


def transform(frame: pd.DataFrame) -> np.ndarray:
    return np.asarray(_artifact()["prep"].transform(frame), dtype=float)


def explain_encoded(frame: pd.DataFrame) -> dict:
    """SHAP for a validated one-row (or n-row) model-ready frame.

    Returns base value, raw model outputs (log space), the encoded SHAP
    matrix, and the additivity error max|base + Σ SHAP − output|."""
    explainer = get_explainer()
    X = transform(frame)
    shap_values = np.asarray(explainer.shap_values(X), dtype=float)
    if shap_values.ndim == 3:  # (n, features, outputs) guard
        shap_values = shap_values[:, :, 0]
    raw_output = np.asarray(_artifact()["model"].predict(X), dtype=float)
    base = base_value()
    recon = base + shap_values.sum(axis=1)
    return {"base_value": base, "model_output_log": raw_output,
            "shap_encoded": shap_values,
            "additivity_max_abs_error": float(np.max(np.abs(recon - raw_output)))}


def aggregate_to_source(shap_encoded_row: np.ndarray) -> dict[str, float]:
    """Sum one encoded row's SHAP values into the 20 source features."""
    mapping = source_feature_map()
    out: dict[str, float] = {}
    for value, source in zip(shap_encoded_row, mapping):
        out[source] = out.get(source, 0.0) + float(value)
    # Preserve the model's exact feature order for stable output.
    return {f: out.get(f, 0.0) for f in _artifact()["features"]}


def explain_frame(frame: pd.DataFrame) -> list[dict]:
    """Full per-row explanation internals (encoded + aggregated)."""
    enc = explain_encoded(frame)
    rows = []
    for i in range(len(frame)):
        rows.append({
            "base_value_log": enc["base_value"],
            "model_output_log": float(enc["model_output_log"][i]),
            "shap_source": aggregate_to_source(enc["shap_encoded"][i]),
            "additivity_abs_error": enc["additivity_max_abs_error"],
        })
    return rows


def global_shap(sample_frame: pd.DataFrame) -> dict:
    """SHAP over a sample frame (model-ready features, no validation —
    for dataset rows). Returns the SHAP Explanation in encoded space,
    the aggregated source-space matrix, and mean |SHAP| rankings."""
    explainer = get_explainer()
    X = transform(sample_frame)
    explanation = explainer(X)  # shap.Explanation, encoded space
    values = np.asarray(explanation.values, dtype=float)
    mapping = source_feature_map()
    features = _artifact()["features"]
    src_idx = {f: [j for j, s in enumerate(mapping) if s == f]
               for f in features}
    aggregated = np.column_stack(
        [values[:, idx].sum(axis=1) for idx in src_idx.values()])
    mean_abs = np.abs(aggregated).mean(axis=0)
    ranking = sorted(zip(features, mean_abs), key=lambda t: -t[1])
    return {"explanation": explanation, "values_encoded": values,
            "aggregated": aggregated, "features": features,
            "ranking": [(f, float(v)) for f, v in ranking],
            "base_value": base_value()}
