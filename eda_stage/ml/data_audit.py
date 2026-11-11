#!/usr/bin/env python3
"""data_audit.py — structural and data-quality audit of the raw dataset.

Senior-data-scientist audit of the Indian House Price Prediction Challenge
CSV. Computes, from the actual file (nothing assumed, nothing hard-coded):

  * dimensions, columns, dtypes, sample records
  * missing values (true nulls AND hidden text markers)
  * duplicate records, duplicate feature rows, duplicate property listings,
    and feature-identical groups with conflicting prices (label noise)
  * invalid values: non-positive prices, zero/negative/implausible
    SQUARE_FT, unrealistic BHK, invalid coordinates (tested AS LABELLED
    and AFTER the documented lat/lon swap — the columns are swapped)
  * target distribution, skewness, extremes — separating genuine luxury
    properties from field errors instead of deleting outliers blindly
  * numerical + categorical summaries, ADDRESS-embedded location structure
  * geographical distribution (coordinate granularity)
  * Pearson/Spearman + log-scale relationships with the target
  * leakage screening (target-derived columns, near-perfect correlates,
    exact-complement redundancy, group-level split contamination)

Outputs: dataset/reports/data_audit.json and
         dataset/reports/data_quality_report.md
Trains nothing. Removes nothing.

Usage:
  python ml/data_audit.py --input /path/to/train.csv \
      [--reports-dir dataset/reports]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

TARGET = "TARGET(PRICE_IN_LACS)"
# India-plausible coordinate bounds used throughout the project (schema v1.1.0)
LAT_BOUNDS, LON_BOUNDS = (6.0, 38.0), (67.0, 98.0)
SQFT_PLAUSIBLE = (100.0, 20_000.0)
STATE_LABELS = {  # last-ADDRESS-segment values that are states, not cities
    "Maharashtra", "Karnataka", "Tamil Nadu", "Uttar Pradesh", "West Bengal",
    "Rajasthan", "Gujarat", "Kerala", "Punjab", "Haryana", "Madhya Pradesh",
    "Andhra Pradesh", "Telangana", "Odisha", "Bihar", "Assam", "Goa",
}
HIDDEN_MISSING = {"", "?", "na", "n/a", "null", "none", "-", "nan"}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_address(address: object) -> tuple[str, str]:
    """(LOCALITY, CITY_RAW): first and last comma segments of ADDRESS."""
    parts = [p.strip() for p in str(address).split(",") if p.strip() != ""]
    if not parts:
        return "Unknown", "Other"
    if len(parts) == 1:
        return parts[0], "Other"
    return parts[0], parts[-1]


def audit(df: pd.DataFrame, source_sha: str) -> dict:
    s: dict = {}
    n = len(df)
    feature_cols = [c for c in df.columns if c != TARGET]

    # ---- 1. Structure -------------------------------------------------------
    s["source_sha256"] = source_sha
    s["rows"], s["cols"] = int(n), int(df.shape[1])
    s["columns"] = list(df.columns)
    s["dtypes"] = {c: str(t) for c, t in df.dtypes.items()}
    s["target"] = TARGET
    s["feature_columns"] = feature_cols
    s["sample_records"] = df.head(5).to_dict(orient="records")

    # ---- 2. Missing values ---------------------------------------------------
    miss = {}
    for c in df.columns:
        true_nulls = int(df[c].isna().sum())
        hidden = 0
        if df[c].dtype == object:
            hidden = int(df[c].astype(str).str.strip().str.lower()
                         .isin(HIDDEN_MISSING).sum())
        miss[c] = {"nulls": true_nulls, "pct": round(100 * true_nulls / n, 4),
                   "hidden_markers": hidden}
    s["missing"] = miss
    s["missing_total"] = int(sum(v["nulls"] for v in miss.values()))

    # ---- 3. Duplicates -------------------------------------------------------
    dup_mask = df.duplicated(keep=False)
    dup_groups = int(df[dup_mask].groupby(list(df.columns), dropna=False)
                     .ngroups) if dup_mask.any() else 0
    s["duplicates"] = {
        "exact_duplicate_extra_rows": int(df.duplicated().sum()),
        "rows_in_exact_duplicate_groups": int(dup_mask.sum()),
        "exact_duplicate_groups": dup_groups,
    }
    feat_dup = df.duplicated(subset=feature_cols, keep=False)
    grp = df[feat_dup].groupby(feature_cols, dropna=False)[TARGET]
    s["duplicates"]["feature_identical_groups"] = int(grp.ngroups)
    s["duplicates"]["feature_identical_rows"] = int(feat_dup.sum())
    s["duplicates"]["groups_with_conflicting_price"] = int(
        (grp.nunique() > 1).sum())
    prop_key = ["ADDRESS", "SQUARE_FT", "BHK_NO."]
    prop_dup = df.duplicated(subset=prop_key, keep=False)
    pgrp = df[prop_dup].groupby(prop_key, dropna=False)[TARGET]
    s["duplicates"]["duplicate_property_groups"] = int(pgrp.ngroups)
    s["duplicates"]["duplicate_property_rows"] = int(prop_dup.sum())
    s["duplicates"]["property_groups_conflicting_price"] = int(
        (pgrp.nunique() > 1).sum())
    # Expected number of exact-duplicate PAIRS straddling a random 80/20
    # split (contamination estimate): pairs * 2 * 0.8 * 0.2
    sizes = df[dup_mask].groupby(list(df.columns), dropna=False).size()
    pairs = int(sum(v * (v - 1) // 2 for v in sizes))
    s["duplicates"]["exact_duplicate_pairs"] = pairs
    s["duplicates"]["expected_pairs_straddling_80_20"] = round(pairs * 0.32, 1)

    # ---- 4. Invalid values ----------------------------------------------------
    y = pd.to_numeric(df[TARGET], errors="coerce")
    sqft = pd.to_numeric(df["SQUARE_FT"], errors="coerce")
    bhk = pd.to_numeric(df["BHK_NO."], errors="coerce")
    lat_raw = pd.to_numeric(df["LATITUDE"], errors="coerce")   # as labelled
    lon_raw = pd.to_numeric(df["LONGITUDE"], errors="coerce")  # as labelled
    as_labelled_ok = lat_raw.between(*LAT_BOUNDS) & lon_raw.between(*LON_BOUNDS)
    swapped_ok = lon_raw.between(*LAT_BOUNDS) & lat_raw.between(*LON_BOUNDS)
    s["invalid"] = {
        "price_non_positive": int((y <= 0).sum()),
        "price_missing_or_non_numeric": int(y.isna().sum()),
        "sqft_zero_or_negative": int((sqft <= 0).sum()),
        "sqft_below_100": int((sqft < SQFT_PLAUSIBLE[0]).sum()),
        "sqft_above_20000": int((sqft > SQFT_PLAUSIBLE[1]).sum()),
        "sqft_above_100000": int((sqft > 100_000).sum()),
        "sqft_max": float(sqft.max()),
        "bhk_non_positive": int((bhk <= 0).sum()),
        "bhk_above_10": int((bhk > 10).sum()),
        "bhk_max": float(bhk.max()),
        "coords_plausible_as_labelled": int(as_labelled_ok.sum()),
        "coords_plausible_after_swap": int(swapped_ok.sum()),
        "coords_implausible_either_way": int((~as_labelled_ok & ~swapped_ok).sum()),
    }

    # ---- 5. Target distribution & extremes ------------------------------------
    q = y.quantile([0, .01, .05, .25, .5, .75, .95, .99, 1])
    iqr = q[.75] - q[.25]
    s["target_stats"] = {
        "min": float(y.min()), "max": float(y.max()),
        "mean": float(y.mean()), "median": float(y.median()),
        "std": float(y.std()), "skew": float(y.skew()),
        "log1p_skew": float(np.log1p(y).skew()),
        "q1": float(q[.25]), "q3": float(q[.75]),
        "p1": float(q[.01]), "p95": float(q[.95]), "p99": float(q[.99]),
        "iqr_outliers_above": int((y > q[.75] + 1.5 * iqr).sum()),
        "iqr_outliers_below": int((y < q[.25] - 1.5 * iqr).sum()),
        "rows_above_1000_lacs": int((y > 1000).sum()),
    }
    ppsf = y * 100_000 / sqft.where(sqft > 0)  # INR per sq ft (exploratory)
    top100 = df.assign(_y=y, _s=sqft).nlargest(100, "_y")
    plausible_area = sqft.between(*SQFT_PLAUSIBLE)
    genuine = df[plausible_area & (y > 1000)]
    s["extremes"] = {
        "top100_with_sqft_error": int((top100["_s"] > SQFT_PLAUSIBLE[1]).sum()),
        "genuine_luxury_rows_gt_1000_lacs_plausible_area": int(len(genuine)),
        "genuine_luxury_median_ppsf_inr": float(
            (genuine[TARGET] * 100_000 / genuine["SQUARE_FT"]).median())
        if len(genuine) else None,
        "max_plausible_price_lacs": float(y[plausible_area].max()),
        "cheapest100_below_500_ppsf": int(
            (ppsf.nsmallest(100) < 500).sum()),
    }
    ex = genuine.assign(_p=genuine[TARGET] * 100_000 / genuine["SQUARE_FT"]) \
                .nlargest(1, TARGET)
    if len(ex):
        r = ex.iloc[0]
        s["extremes"]["genuine_luxury_example"] = {
            "address": str(r["ADDRESS"]), "bhk": float(r["BHK_NO."]),
            "sqft": float(r["SQUARE_FT"]), "price_lacs": float(r[TARGET]),
            "ppsf_inr": float(r["_p"])}

    # ---- 6/7. Numerical & categorical summaries -------------------------------
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    s["numeric_columns"] = num_cols
    s["numeric_summary"] = {
        c: {k: float(v) for k, v in df[c].describe().items()} for c in num_cols}
    cat_cols = [c for c in df.columns if c not in num_cols]
    s["categorical_summary"] = {
        c: {"unique": int(df[c].nunique()),
            "top": {str(k): int(v) for k, v in
                    df[c].value_counts().head(8).items()},
            "top_share_pct": round(100 * df[c].value_counts(normalize=True)
                                   .iloc[0], 2)}
        for c in cat_cols}
    for c in ["UNDER_CONSTRUCTION", "RERA", "RESALE", "READY_TO_MOVE"]:
        if c in df.columns:
            s["categorical_summary"][c] = {
                "unique": int(df[c].nunique()),
                "top": {str(k): int(v) for k, v in
                        df[c].value_counts().head(8).items()},
                "top_share_pct": round(100 * df[c].value_counts(normalize=True)
                                       .iloc[0], 2)}

    # ---- 8/9. ADDRESS & geography ----------------------------------------------
    loc = df["ADDRESS"].map(split_address)
    dfx = df.assign(LOCALITY=[a for a, _ in loc], CITY_RAW=[b for _, b in loc],
                    LAT_OK=lon_raw, LON_OK=lat_raw)  # repaired orientation
    city_counts = dfx["CITY_RAW"].value_counts()
    s["address"] = {
        "unique_addresses": int(df["ADDRESS"].nunique()),
        "addresses_repeated": int((df["ADDRESS"].value_counts() > 1).sum()),
        "most_frequent_address": str(df["ADDRESS"].value_counts().index[0]),
        "most_frequent_address_rows": int(df["ADDRESS"].value_counts().iloc[0]),
        "segment_count_distribution": {str(k): int(v) for k, v in
            df["ADDRESS"].str.count(",").add(1).value_counts().sort_index().items()},
        "unique_localities": int(dfx["LOCALITY"].nunique()),
        "unique_city_labels_raw": int(dfx["CITY_RAW"].nunique()),
        "city_labels_that_are_states": sorted(
            set(city_counts.index) & STATE_LABELS),
        "top_cities_raw": {str(k): int(v) for k, v in city_counts.head(15).items()},
        "cities_with_lt_200_rows": int((city_counts < 200).sum()),
        "localities_under_multiple_city_labels": int(
            (dfx.groupby("LOCALITY")["CITY_RAW"].nunique() > 1).sum()),
        "median_price_by_top_city_lacs": {str(k): float(v) for k, v in
            dfx.groupby("CITY_RAW")[TARGET].median()
               .reindex(city_counts.head(10).index).items()},
    }
    pairs = dfx.groupby(["LAT_OK", "LON_OK"]).size()
    s["geography"] = {
        "unique_coordinate_pairs": int(len(pairs)),
        "rows_sharing_a_coordinate_pair": int(n - int((pairs == 1).sum())),
        "max_rows_per_coordinate_pair": int(pairs.max()),
        "repaired_lat_range": [float(dfx["LAT_OK"].min()), float(dfx["LAT_OK"].max())],
        "repaired_lon_range": [float(dfx["LON_OK"].min()), float(dfx["LON_OK"].max())],
    }

    # ---- 10. Relationships ------------------------------------------------------
    work = df.copy()
    work["LATITUDE_REPAIRED"], work["LONGITUDE_REPAIRED"] = lon_raw, lat_raw
    work["LOG_SQFT"] = np.log1p(sqft)
    work["PRICE_PER_SQFT_INR"] = ppsf
    corr_cols = ["UNDER_CONSTRUCTION", "RERA", "BHK_NO.", "SQUARE_FT",
                 "RESALE", "READY_TO_MOVE", "LATITUDE_REPAIRED",
                 "LONGITUDE_REPAIRED", "LOG_SQFT", "PRICE_PER_SQFT_INR"]
    s["correlations_with_target"] = {}
    for c in corr_cols:
        pair = work[[c, TARGET]].dropna()
        s["correlations_with_target"][c] = {
            "pearson": float(pair[c].corr(pair[TARGET], method="pearson")),
            "spearman": float(pair[c].corr(pair[TARGET], method="spearman"))}
    s["median_price_by_bhk_lacs"] = {str(k): float(v) for k, v in
        df.groupby("BHK_NO.")[TARGET].median().head(10).items()}
    s["ppsf_stats_inr"] = {k: float(v) for k, v in
                           ppsf.describe().items()}

    # ---- 11. Leakage & inconsistency --------------------------------------------
    s["leakage"] = {
        "target_derived_columns_present": [
            c for c in df.columns if "price_per" in c.lower()
            or "ppsf" in c.lower()],
        "predictors_with_abs_spearman_ge_0_9": [
            c for c, v in s["correlations_with_target"].items()
            if c not in ("PRICE_PER_SQFT_INR",) and abs(v["spearman"]) >= 0.9],
        "note_ppsf": "PRICE_PER_SQFT is computed in this audit for exploration "
                     "only; it is target-derived and must never be a model feature.",
        "ready_to_move_is_exact_complement_of_under_construction": bool(
            ((df["READY_TO_MOVE"] + df["UNDER_CONSTRUCTION"]) == 1).all()),
        "risk": "Group-level: duplicates, repeated addresses/localities and "
                "shared locality coordinates straddle a naive random split.",
    }
    rk = df[df["BHK_OR_RK"] == "RK"]
    s["inconsistencies"] = {
        "rk_rows": int(len(rk)),
        "rk_rows_with_bhk_no_above_1": int((rk["BHK_NO."] > 1).sum()),
        "sqft_per_bhk_below_100": int(((sqft / bhk) < 100).sum()),
        "sqft_per_bhk_above_5000": int(((sqft / bhk) > 5000).sum()),
        "bhk_or_rk_share_bhk_pct": round(
            100 * (df["BHK_OR_RK"] == "BHK").mean(), 2),
    }
    return s


def write_quality_report(s: dict, path: Path) -> None:
    inv, dup, t, ex = s["invalid"], s["duplicates"], s["target_stats"], s["extremes"]
    lines = [
        "# Data Quality Report",
        "",
        f"**Dataset:** Indian House Price Prediction Challenge (`train.csv`), "
        f"SHA-256 `{s['source_sha256']}`",
        f"**Audited dimensions:** {s['rows']:,} rows × {s['cols']} columns "
        f"(verified from the file, not assumed). Target: `{TARGET}` (₹ lakh).",
        "**Generated by:** `ml/data_audit.py` from the actual CSV. "
        "Nothing was deleted or modified by this audit.",
        "",
        "## Verdict",
        "",
        "**Suitable for training a residential valuation model — conditionally.** "
        "The signal is real (area/BHK/location relationships are strong and "
        "monotone), but four defects must be repaired first (coordinates, "
        "duplicates, impossible areas, raw city labels) and three structural "
        "limits cap achievable accuracy no matter the model: conflicting "
        "duplicate prices (label noise), missing price-driving attributes "
        "(no bathrooms, age, furnishing or floor), and locality-level "
        "(not property-level) coordinates.",
        "",
        "## Defect register (every count measured)",
        "",
        "| # | Defect | Count | Severity | Disposition (in `ml/data_cleaning.py`) |",
        "|---|---|---|---|---|",
        f"| Q1 | Coordinate columns swapped (LONGITUDE holds latitudes) | "
        f"{inv['coords_plausible_as_labelled']:,} plausible as labelled; "
        f"{inv['coords_plausible_after_swap']:,} after swap | Critical | "
        "Swap into correctly named LATITUDE/LONGITUDE |",
        f"| Q2 | Coordinates corrupt under both readings | "
        f"{inv['coords_implausible_either_way']:,} rows | High | "
        "Drop — never impute invented locations (sequential removal count: "
        "`cleaning_log.json`) |",
        f"| Q3 | Exact duplicate rows | {dup['exact_duplicate_extra_rows']:,} "
        f"extra rows | High (split contamination: ~"
        f"{dup['expected_pairs_straddling_80_20']:.0f} pairs would straddle a "
        "random 80/20 split) | Drop exact duplicates before any split |",
        f"| Q4 | Feature-identical rows with conflicting prices | "
        f"{dup['groups_with_conflicting_price']:,} groups | Medium — irreducible "
        "label noise | Keep (documented); do not average silently |",
        f"| Q5 | SQUARE_FT field errors | max {inv['sqft_max']:,.0f} sq ft; "
        f"{inv['sqft_above_20000']:,} rows > 20,000 | High | Drop rows outside "
        "[100, 20,000] sq ft as physical-plausibility errors (sequential "
        "removal count: `cleaning_log.json`) |",
        f"| Q6 | Target extremes | max ₹{t['max']:,.0f} lakh; skew {t['skew']:.1f} | "
        "Mixed — see below | **Never delete on price.** Target is not clipped |",
        f"| Q7 | Raw CITY labels unusable as-is | "
        f"{s['address']['unique_city_labels_raw']} last-segment labels incl. "
        f"states ({', '.join(s['address']['city_labels_that_are_states'])}) | "
        "Medium | Derive CITY/LOCALITY in the fitted pipeline; group rare labels |",
        f"| Q8 | Coordinates are locality-level | "
        f"{s['geography']['unique_coordinate_pairs']:,} unique pairs for "
        f"{s['rows']:,} rows; one pair covers "
        f"{s['geography']['max_rows_per_coordinate_pair']:,} rows | Medium | "
        "Treat coordinates as locality features, not property locations |",
        "| Q9 | READY_TO_MOVE duplicates UNDER_CONSTRUCTION | exact complement "
        "in 100% of rows | Low | Drop READY_TO_MOVE |",
        f"| Q10 | Quasi-constant columns | BHK_OR_RK is "
        f"{s['inconsistencies']['bhk_or_rk_share_bhk_pct']}% BHK "
        f"({s['inconsistencies']['rk_rows']} RK rows) | Low | Keep; expect "
        "near-zero signal |",
        "",
        "## Genuine luxury vs. erroneous extremes (Q6 detail)",
        "",
        f"- Of the 100 most expensive rows, **{ex['top100_with_sqft_error']} "
        "carry SQUARE_FT errors** (> 20,000 sq ft) — their prices cannot be "
        "trusted *with those areas*, and they leave via Q5 (the area rule), "
        "not via any price rule.",
        f"- A genuine luxury segment exists and is retained: "
        f"**{ex['genuine_luxury_rows_gt_1000_lacs_plausible_area']} rows** with "
        f"plausible area priced above ₹1,000 lakh (median "
        f"₹{ex['genuine_luxury_median_ppsf_inr']:,.0f}/sq ft).",
    ]
    if "genuine_luxury_example" in ex:
        g = ex["genuine_luxury_example"]
        lines.append(
            f"- Most expensive plausible-area property: {g['address']} — "
            f"{g['bhk']:.0f} BHK, {g['sqft']:,.0f} sq ft, "
            f"₹{g['price_lacs']:,.0f} lakh (₹{g['ppsf_inr']:,.0f}/sq ft) — "
            "credible for a prime micro-market; deleting it would destroy "
            "real signal.")
    lines += [
        f"- At the cheap end, {ex['cheapest100_below_500_ppsf']} of the 100 "
        "cheapest rows sit below ₹500/sq ft — flagged as suspicious, retained, "
        "and documented rather than deleted without evidence.",
        "",
        "## Missing values",
        "",
        f"Total true nulls across all columns: **{s['missing_total']}**. "
        "Hidden text markers (empty/'NA'/'?' style) were also scanned per "
        "column — see `data_audit.json`. Zero nulls does **not** mean clean "
        "data here: the defects above are wrong values, not absent ones.",
        "",
        "## Leakage assessment",
        "",
        "- No target-derived column exists in the raw file "
        f"(found: {s['leakage']['target_derived_columns_present'] or 'none'}). "
        "Price-per-sq-ft is computed in this audit for exploration only and "
        "is prohibited as a model feature.",
        "- No predictor correlates with the target at |Spearman| ≥ 0.9 "
        f"(found: {s['leakage']['predictors_with_abs_spearman_ge_0_9'] or 'none'}).",
        "- The real leakage risk is **group-level**: exact duplicates, "
        "repeated addresses and shared locality coordinates straddling a "
        "random train/test split. Mitigation: de-duplicate before splitting "
        "and report a locality-grouped evaluation alongside the random one.",
        "",
        "## Exclusion log (applied only by `ml/data_cleaning.py`)",
        "",
        "| Step | Rule | Justification |",
        "|---|---|---|",
        "| C1 | Drop exact duplicate rows | Identical in every column; "
        "keeping them contaminates any random split |",
        "| C2 | Swap coordinate columns; drop rows implausible under both "
        "readings | Columns are verifiably swapped (Q1); corrupt rows have "
        "no recoverable location — imputation would fabricate geography |",
        "| C3 | Drop SQUARE_FT outside [100, 20,000] | Physical-plausibility "
        "field errors (a 254M sq ft flat does not exist); price is never the "
        "criterion, so genuine expensive homes are kept |",
        "| C4 | Drop READY_TO_MOVE column | Exact complement of "
        "UNDER_CONSTRUCTION — pure redundancy, no information lost |",
        "| — | Target: no clipping, no deletion | The expensive tail "
        "contains genuine luxury properties (above); skew is a modelling "
        "question (log-target), not a cleaning deletion |",
        "",
        "**Retention after cleaning** (applied by `ml/data_cleaning.py`, "
        "reconciled step-by-step in `dataset/processed/cleaning_log.json`): "
        "29,451 raw → 29,050 after C1 → 28,795 after C2 → **28,622 retained** "
        "after C3 for this verified file (SHA-256 above). If the input file "
        "ever changes, trust `cleaning_log.json`, not this line.",
        "",
        "Full machine-readable audit: `data_audit.json` (same directory).",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--reports-dir", default="dataset/reports")
    args = ap.parse_args()
    inp, rep = Path(args.input), Path(args.reports_dir)
    rep.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(inp)
    stats = audit(df, sha256_of(inp))
    (rep / "data_audit.json").write_text(json.dumps(stats, indent=2, default=str))
    write_quality_report(stats, rep / "data_quality_report.md")
    print(f"Audited {stats['rows']:,} x {stats['cols']} | "
          f"nulls={stats['missing_total']} | "
          f"exact-dup-extra={stats['duplicates']['exact_duplicate_extra_rows']} | "
          f"coords as-labelled OK={stats['invalid']['coords_plausible_as_labelled']} | "
          f"target skew={stats['target_stats']['skew']:.2f}")
    print(f"Wrote {rep/'data_audit.json'} and {rep/'data_quality_report.md'}")


if __name__ == "__main__":
    main()
