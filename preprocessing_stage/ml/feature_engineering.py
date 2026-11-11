#!/usr/bin/env python3
"""feature_engineering.py — train-fitted feature derivation for AVM tabular data.

One transformer, `FeatureEngineer`, turns cleaned property rows into the
model feature frame. It is used IDENTICALLY in training and (later) in the
Flask inference path, so the two can never diverge.

Fitted on TRAINING DATA ONLY (never the target):
  * city centroids      — median (lat, lon) of reliably labelled cities with
                          >= `centroid_min_rows` training rows; used to repair
                          corrupt city labels and as a coordinate fallback.
  * city_categories_    — cities with >= `city_min_rows` training rows;
                          rarer cities map to 'Other' at transform time.
  * city_freq_ / locality_freq_ — raw training counts (frequencies are
                          counts of TRAIN rows; an unseen locality gets 0,
                          which is information, not leakage).
  * geo_cluster_        — KMeans over training coordinates (geographic
                          clusters as a categorical feature, EXPERIMENTAL —
                          see feature dictionary; ablation at training stage).
  * coord_median_       — training median (lat, lon), last-resort fallback.

Deterministic (unfitted) derivations, identical for every row everywhere:
  * LOCALITY / CITY_RAW split from ADDRESS; state label 'Maharashtra' ->
    'Mumbai' (its localities and coordinate median are Mumbai's — EDA §6);
    corrupt label 'Lalitpur' reassigned to the nearest fitted centroid
    within 0.75 degrees, else 'Other'.
  * SQUARE_FT_PER_BHK, LOG_SQUARE_FT, DIST_TO_CITY_CENTROID,
    LAT_LON_INTERACTION, SQFT_BAND (fixed domain bands), BHK_CONFIG.
  * Categorical normalisation: surrounding whitespace stripped and known
    case-variants mapped to the canonical schema values, so ' owner ' and
    'Owner' cannot become two categories.

Coordinate policy: cleaned training rows are already validated, so this
never triggers in training. At transform time a row whose coordinates fall
outside India-plausible bounds is repaired to its (fitted) city centroid —
inventing a location would be worse, and silently keeping (0, 0) would
poison DIST_TO_CITY_CENTROID and GEO_CLUSTER.

PROHIBITED: any target-derived feature. PRICE_PER_SQFT is never created
here (EDA-only diagnostic). READY_TO_MOVE is not recreated as a separate
feature: it is the exact complement of UNDER_CONSTRUCTION (EDA finding),
so its information is already fully present.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.cluster import KMeans

TARGET = "TARGET(PRICE_IN_LACS)"
LAT_BOUNDS, LON_BOUNDS = (6.0, 38.0), (67.0, 98.0)
STATE_TO_CITY = {"Maharashtra": "Mumbai"}
CORRUPT_CITY_LABELS = {"Lalitpur"}
# Fixed domain bands for size category (NOT fitted — interpretable cut points)
SQFT_BANDS = [(600, "XS"), (1000, "S"), (1500, "M"), (2500, "L")]
SQFT_BAND_DEFAULT = "XL"
_CASE_FIX = {"owner": "Owner", "dealer": "Dealer", "builder": "Builder",
             "bhk": "BHK", "rk": "RK"}

# Column groups of the engineered frame (single source for preprocessing.py)
NUMERIC_FEATURES = ["BHK_NO.", "SQUARE_FT", "LATITUDE", "LONGITUDE",
                    "SQUARE_FT_PER_BHK", "LOG_SQUARE_FT",
                    "DIST_TO_CITY_CENTROID", "CITY_FREQ", "LOCALITY_FREQ",
                    "LAT_LON_INTERACTION"]
BINARY_FEATURES = ["UNDER_CONSTRUCTION", "RERA", "RESALE"]
CATEGORICAL_FEATURES = ["POSTED_BY", "BHK_OR_RK", "CITY", "SQFT_BAND",
                        "BHK_CONFIG", "GEO_CLUSTER"]
LOCALITY_FEATURE = "LOCALITY"
# Canonical output order (stable across runs, variants and column shuffles)
ENGINEERED_FEATURES = ["POSTED_BY", "UNDER_CONSTRUCTION", "RERA", "BHK_NO.",
                       "BHK_OR_RK", "SQUARE_FT", "RESALE", "CITY", "LOCALITY",
                       "LATITUDE", "LONGITUDE", "SQUARE_FT_PER_BHK",
                       "LOG_SQUARE_FT", "DIST_TO_CITY_CENTROID", "CITY_FREQ",
                       "LOCALITY_FREQ", "LAT_LON_INTERACTION", "SQFT_BAND",
                       "BHK_CONFIG", "GEO_CLUSTER"]


def split_address(address: object) -> tuple[str, str]:
    """(LOCALITY, CITY_RAW) from an 'Locality,...,City' string. Pure function."""
    parts = [p.strip() for p in str(address).split(",") if p.strip() != ""]
    if not parts:
        return "Unknown", "Other"
    if len(parts) == 1:
        return parts[0], "Other"
    return parts[0], parts[-1]


def _sqft_band(sqft: float) -> str:
    for limit, label in SQFT_BANDS:
        if sqft < limit:
            return label
    return SQFT_BAND_DEFAULT


class FeatureEngineer(BaseEstimator, TransformerMixin):
    """Cleaned rows in -> engineered feature frame out (see module docstring)."""

    def __init__(self, centroid_min_rows: int = 200, city_min_rows: int = 200,
                 max_dist_deg: float = 0.75, n_geo_clusters: int = 32,
                 random_state: int = 42):
        self.centroid_min_rows = centroid_min_rows
        self.city_min_rows = city_min_rows
        self.max_dist_deg = max_dist_deg
        self.n_geo_clusters = n_geo_clusters
        self.random_state = random_state

    # -- helpers ------------------------------------------------------------
    def _repair_city(self, city_raw: str, lat: float, lon: float) -> str:
        if city_raw in STATE_TO_CITY:
            return STATE_TO_CITY[city_raw]
        if city_raw in CORRUPT_CITY_LABELS:
            best, best_d = "Other", math.inf
            for c in self.centroids_:
                d = math.hypot(lat - c["lat"], lon - c["lon"])
                if d < best_d:
                    best, best_d = c["city"], d
            return best if best_d <= self.max_dist_deg else "Other"
        return city_raw

    def _normalise(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col in ("POSTED_BY", "BHK_OR_RK"):
            X[col] = X[col].apply(
                lambda v: _CASE_FIX.get(str(v).strip().lower(),
                                        str(v).strip())
                if pd.notna(v) else np.nan)
        X["ADDRESS"] = X["ADDRESS"].apply(
            lambda v: str(v).strip() if pd.notna(v) else np.nan)
        return X

    def _derive(self, X: pd.DataFrame, apply_grouping: bool) -> pd.DataFrame:
        X = self._normalise(X)
        loc_city = X["ADDRESS"].apply(
            lambda a: split_address(a) if pd.notna(a) else ("Unknown", "Other"))
        X["LOCALITY"] = [lc[0] for lc in loc_city]
        city_raw = [lc[1] for lc in loc_city]
        # coordinate validation / fallback (fitted state required)
        lat = pd.to_numeric(X["LATITUDE"], errors="coerce").astype(float)
        lon = pd.to_numeric(X["LONGITUDE"], errors="coerce").astype(float)
        cities_pre = [self._repair_city(cr, la, lo) for cr, la, lo
                      in zip(city_raw, lat, lon)]
        cent = {c["city"]: (c["lat"], c["lon"]) for c in self.centroids_}
        valid = lat.between(*LAT_BOUNDS) & lon.between(*LON_BOUNDS)
        if not valid.all():
            lat = lat.copy(); lon = lon.copy()
            for i in np.where(~valid)[0]:
                fallback = cent.get(cities_pre[i], self.coord_median_)
                lat.iloc[i], lon.iloc[i] = fallback
        X["LATITUDE"], X["LONGITUDE"] = lat, lon
        cities = cities_pre
        if apply_grouping:
            keep = set(self.city_categories_)
            cities = [c if c in keep else "Other" for c in cities]
        X["CITY"] = cities
        bhk_safe = X["BHK_NO."].replace(0, np.nan)
        X["SQUARE_FT_PER_BHK"] = X["SQUARE_FT"] / bhk_safe
        X["SQFT_BAND"] = X["SQUARE_FT"].map(
            lambda v: _sqft_band(v) if pd.notna(v) else np.nan)
        X["BHK_CONFIG"] = [f"{int(b)}{t}" if pd.notna(b) else np.nan
                           for b, t in zip(X["BHK_NO."], X["BHK_OR_RK"])]
        if hasattr(self, "city_freq_"):  # fitted state exists (not fit's pre-pass)
            X["LOG_SQUARE_FT"] = np.log1p(X["SQUARE_FT"])
            X["DIST_TO_CITY_CENTROID"] = [
                math.hypot(la - cent[ci][0], lo - cent[ci][1]) if ci in cent
                else np.nan
                for ci, la, lo in zip(X["CITY"], X["LATITUDE"], X["LONGITUDE"])]
            X["CITY_FREQ"] = X["CITY"].map(self.city_freq_).fillna(0).astype(float)
            X["LOCALITY_FREQ"] = (X["LOCALITY"].map(self.locality_freq_)
                                  .fillna(0).astype(float))
            X["LAT_LON_INTERACTION"] = X["LATITUDE"] * X["LONGITUDE"]
            clusters = self.geo_cluster_.predict(
                X[["LATITUDE", "LONGITUDE"]].to_numpy())
            X["GEO_CLUSTER"] = [f"C{c:02d}" for c in clusters]
            return X[ENGINEERED_FEATURES]
        return X

    # -- sklearn API ----------------------------------------------------------
    def fit(self, X: pd.DataFrame, y=None):
        Xn = self._normalise(X)
        loc_city = Xn["ADDRESS"].apply(split_address)
        city_raw = pd.Series([lc[1] for lc in loc_city], index=Xn.index)
        reliable = ~city_raw.isin(CORRUPT_CITY_LABELS | set(STATE_TO_CITY))
        grp = (Xn[reliable].assign(_cr=city_raw[reliable])
               .groupby("_cr")
               .agg(lat=("LATITUDE", "median"), lon=("LONGITUDE", "median"),
                    rows=("LATITUDE", "size")))
        grp = grp[grp["rows"] >= self.centroid_min_rows]
        self.centroids_ = [{"city": str(i), "lat": float(r.lat),
                            "lon": float(r.lon), "rows": int(r.rows)}
                           for i, r in grp.iterrows()]
        self.coord_median_ = (float(Xn["LATITUDE"].median()),
                              float(Xn["LONGITUDE"].median()))
        # Pre-pass with centroids_ (set above) to obtain repaired cities
        # for the grouping and frequency state.
        loc = Xn["ADDRESS"].apply(split_address)
        cities_pre = [self._repair_city(lc[1], la, lo) for lc, la, lo
                      in zip(loc, Xn["LATITUDE"], Xn["LONGITUDE"])]
        counts = pd.Series(cities_pre).value_counts()
        self.city_categories_ = sorted(
            [c for c in counts[counts >= self.city_min_rows].index
             if c != "Other"] + ["Other"])
        grouped = pd.Series(cities_pre).where(
            pd.Series(cities_pre).isin(self.city_categories_), "Other")
        self.city_freq_ = grouped.value_counts().to_dict()
        self.locality_freq_ = pd.Series(
            [lc[0] for lc in loc]).value_counts().to_dict()
        self.geo_cluster_ = KMeans(n_clusters=self.n_geo_clusters,
                                   n_init=10, random_state=self.random_state)
        self.geo_cluster_.fit(Xn[["LATITUDE", "LONGITUDE"]].to_numpy())
        self.feature_names_in_ = list(X.columns)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return self._derive(X, apply_grouping=True)

    def get_feature_names_out(self, input_features=None):
        return np.array(ENGINEERED_FEATURES, dtype=object)
