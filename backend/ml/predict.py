#!/usr/bin/env python3
"""predict.py — reusable inference for the packaged property-valuation model.

Usage (e.g. from a Flask route):

    from predict import predict_property
    price_lacs = predict_property({
        "POSTED_BY": "Owner", "UNDER_CONSTRUCTION": 0, "RERA": 1,
        "BHK_NO.": 3, "BHK_OR_RK": "BHK", "SQUARE_FT": 1450.0, "RESALE": 1,
        "CITY": "Mumbai", "LOCALITY": "Andheri West",
        "LATITUDE": 19.136, "LONGITUDE": 72.827,
        "SQUARE_FT_PER_BHK": 483.3, "LOG_SQUARE_FT": 7.279,
        "DIST_TO_CITY_CENTROID": 4.1, "CITY_FREQ": 5200.0,
        "LOCALITY_FREQ": 132.0, "SQFT_BAND": "1200_1500",
        "BHK_CONFIG": "3BHK", "GEO_CLUSTER": "C17", "LAT_LON_INTERACTION": 1394.6,
    })

The input contract is the model's 20 model-ready features, in the exact
order recorded in feature_schema.json (the same features the model was
trained on — see that file for each feature's origin: raw listing
attributes vs features derived by the preprocessing stage). The packaged
artifact (model.pkl) contains the COMPLETE fitted inference path —
preprocessing pipeline (imputers + categorical encoders fitted during
training) plus the estimator — never the estimator alone.

Validation behaviour:
  * Missing required features -> ValueError naming them.
  * Wrong types / non-numeric values in numeric fields -> ValueError.
  * SQUARE_FT <= 0, BHK outside 1..20, coordinates outside India's
    bounding box, binary flags not in {0, 1} -> ValueError.
  * Unseen categorical values are ACCEPTED: the training-time encoder
    was fitted with handle_unknown="ignore", exactly as in training.
  * DIST_TO_CITY_CENTROID may be None (legitimately undefined for the
    'Other' city group in training); the pipeline imputes it.
  * Unknown extra keys are ignored (callers may send listing metadata).

Returns the estimated price in Indian lakhs (₹ lakh) as a float.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import joblib
import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ARTIFACT: dict | None = None
_SCHEMA: dict | None = None

# Core listing attributes that must carry a real value (the pipeline's
# imputers exist for pipeline-internal robustness, not as a licence to
# price a property with no size or configuration).
_NON_NULLABLE = {"SQUARE_FT", "BHK_NO.", "LATITUDE", "LONGITUDE"}
_BINARY = {"UNDER_CONSTRUCTION", "RERA", "RESALE"}
_CATEGORICAL = {"POSTED_BY", "BHK_OR_RK", "CITY", "LOCALITY",
                "SQFT_BAND", "BHK_CONFIG", "GEO_CLUSTER"}


def _load() -> tuple[dict, dict]:
    global _ARTIFACT, _SCHEMA
    if _ARTIFACT is None:
        _ARTIFACT = joblib.load(_HERE / "model.pkl")
        _SCHEMA = json.loads((_HERE / "feature_schema.json").read_text())
    return _ARTIFACT, _SCHEMA


def _coerce_number(name: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name}: expected a number, got a boolean")
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        try:
            out = float(value.strip())
        except ValueError:
            raise ValueError(f"{name}: expected a number, got {value!r}")
    else:
        raise ValueError(f"{name}: expected a number, got "
                         f"{type(value).__name__}")
    if np.isnan(out):
        raise ValueError(f"{name}: value is NaN")
    return out


def _validate(property_features: Mapping) -> pd.DataFrame:
    """Validate the input mapping and return a one-row DataFrame with the
    exact training feature order."""
    _, schema = _load()
    features: list[str] = schema["feature_order"]
    if not isinstance(property_features, Mapping):
        raise ValueError("property_features must be a mapping of "
                         "feature name -> value")
    missing = [f for f in features if f not in property_features]
    if missing:
        raise ValueError(f"Missing required features: {missing}")

    row: dict[str, object] = {}
    for name in features:
        value = property_features[name]
        is_missing = value is None or (isinstance(value, float)
                                       and np.isnan(value))
        if is_missing:
            if name in _NON_NULLABLE:
                raise ValueError(f"{name}: a value is required")
            row[name] = np.nan  # pipeline imputes (matches training)
            continue
        if name in _CATEGORICAL:
            if name == "GEO_CLUSTER" and isinstance(value, (int, float)) \
                    and not isinstance(value, bool):
                value = f"C{int(value):02d}"  # cluster ids are 'C09' labels
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}: expected a non-empty string, "
                                 f"got {value!r}")
            row[name] = value
            continue
        num = _coerce_number(name, value)
        if name in _BINARY:
            if num not in (0.0, 1.0):
                raise ValueError(f"{name}: expected 0 or 1, got {value!r}")
            row[name] = int(num)
        elif name == "BHK_NO.":
            if num != int(num) or not (1 <= num <= 20):
                raise ValueError(f"BHK_NO.: expected an integer in "
                                 f"[1, 20], got {value!r}")
            row[name] = int(num)
        elif name == "SQUARE_FT":
            if num <= 0:
                raise ValueError(f"SQUARE_FT: must be positive, got {num}")
            if num > 1_000_000:
                raise ValueError(f"SQUARE_FT: {num} sq ft is outside any "
                                 f"plausible residential range")
            row[name] = num
        elif name == "LATITUDE":
            if not (5.0 <= num <= 40.0):
                raise ValueError(f"LATITUDE: {num} is outside India's "
                                 f"bounding box [5, 40]")
            row[name] = num
        elif name == "LONGITUDE":
            if not (65.0 <= num <= 100.0):
                raise ValueError(f"LONGITUDE: {num} is outside India's "
                                 f"bounding box [65, 100]")
            row[name] = num
        elif name in {"CITY_FREQ", "LOCALITY_FREQ", "SQUARE_FT_PER_BHK",
                      "DIST_TO_CITY_CENTROID"}:
            if num < 0:
                raise ValueError(f"{name}: must be non-negative, got {num}")
            row[name] = num
        else:  # LOG_SQUARE_FT, LAT_LON_INTERACTION and any future numeric
            row[name] = num
    return pd.DataFrame([row], columns=features)


def _predict_frame(frame: pd.DataFrame) -> float:
    artifact, schema = _load()
    if artifact.get("kind") == "ensemble":
        log_preds = []
        for member in artifact["members"]:
            raw = np.asarray(member["model"].predict(
                member["prep"].transform(frame)), dtype=float)
            log_preds.append(raw)
        point = float(np.mean(log_preds, axis=0)[0])
    else:
        raw = np.asarray(artifact["model"].predict(
            artifact["prep"].transform(frame)), dtype=float)
        point = float(raw[0])
    # Inverse target transformation (training used log1p; see metadata).
    if schema["target"]["transform"] == "log1p":
        hi = schema["target"].get("log_clip_upper")
        if hi is not None:
            point = float(np.clip(point, 0.0, hi))
        return float(np.expm1(point))
    return float(max(point, 0.0))


def predict_property(property_features: Mapping) -> float:
    """Predict the price (₹ lakh) for one property.

    property_features: mapping with the 20 model-ready features listed
    in feature_schema.json. Raises ValueError on missing or invalid
    input; unseen categorical values are handled by the encoder."""
    frame = _validate(property_features)
    return round(_predict_frame(frame), 2)


def predict_properties(records: list[Mapping]) -> list[float]:
    """Batch variant of predict_property (same validation per record)."""
    return [predict_property(r) for r in records]


def model_info() -> dict:
    """Training/selection metadata for the packaged model."""
    return json.loads((_HERE / "model_metadata.json").read_text())


if __name__ == "__main__":  # tiny smoke demo (not a test suite)
    info = model_info()
    print(f"Packaged model: {info['model']['name']} "
          f"(selected in {info['provenance']['stage']})")
    print(f"Validation R² {info['metrics']['validation']['r2']:.4f} · "
          f"Test R² {info['metrics']['test']['r2']:.4f}")
