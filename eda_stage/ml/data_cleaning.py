#!/usr/bin/env python3
"""data_cleaning.py — deterministic, documented cleaning for the raw CSV.

Implements exactly the exclusion log of the data-quality report. Every rule
is a fixed, row-wise test: NOTHING is fitted or learned from the data here
(no medians, thresholds-from-data or category sets), so running this before
any train/test split cannot leak information across the split. Anything
learned (city centroids/grouping, imputers, encoders) belongs to the
modelling pipeline and is fitted on training data only — downstream of here.

Rules (evidence: dataset/reports/data_quality_report.md):
  C1  Drop exact duplicate rows (identical in every column).
  C2  Repair the swapped coordinate columns into correctly named
      LATITUDE / LONGITUDE, then drop rows outside India-plausible bounds
      under BOTH readings — their locations are corrupt and are never
      imputed with invented coordinates.
  C3  Drop rows whose SQUARE_FT is outside [100, 20,000] — physical-
      plausibility FIELD errors (raw max ≈ 254 million sq ft). Price is
      never a removal criterion, so genuine expensive properties survive.
  C4  Drop READY_TO_MOVE — the exact complement of UNDER_CONSTRUCTION
      in every row (pure redundancy).
  C5  Validate categorical values against the verified schema; raise on
      anything unexpected so silent category drift is impossible.

The target is deliberately NOT clipped, capped or deleted: the expensive
tail contains genuine luxury properties (see quality report, Q6), and
skew is handled at modelling time (log-target), not by deletion.

Outputs: dataset/processed/cleaned_dataset.csv
         dataset/processed/cleaning_log.json  (row reconciliation per step)

Usage:
  python ml/data_cleaning.py --input /path/to/train.csv \
      [--out dataset/processed/cleaned_dataset.csv]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

TARGET = "TARGET(PRICE_IN_LACS)"
LAT_BOUNDS, LON_BOUNDS = (6.0, 38.0), (67.0, 98.0)   # India-plausible
SQFT_RANGE = (100.0, 20_000.0)
KNOWN_VALUES = {
    "POSTED_BY": {"Owner", "Dealer", "Builder"},
    "BHK_OR_RK": {"BHK", "RK"},
}


def clean_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Apply C1–C5. Returns (cleaned_df, step_log) with full reconciliation."""
    log: list[dict] = []

    def record(step: str, frame: pd.DataFrame, removed: int = 0, note: str = ""):
        log.append({"step": step, "rows_after": int(len(frame)),
                    "rows_removed": int(removed), "note": note})

    record("C0 raw file loaded", df)

    # C1 — exact duplicates
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    record("C1 exact duplicate rows dropped", df, before - len(df))

    # C2 — coordinate repair: raw LONGITUDE holds latitudes and raw LATITUDE
    # holds longitudes, so read BOTH into temporaries before overwriting.
    df = df.copy()
    repaired_lat = pd.to_numeric(df["LONGITUDE"], errors="coerce")
    repaired_lon = pd.to_numeric(df["LATITUDE"], errors="coerce")
    df["LATITUDE"], df["LONGITUDE"] = repaired_lat, repaired_lon
    plausible = df["LATITUDE"].between(*LAT_BOUNDS) & df["LONGITUDE"].between(*LON_BOUNDS)
    before = len(df)
    df = df[plausible].reset_index(drop=True)
    record("C2 coordinates swapped; rows implausible under both readings dropped",
           df, before - len(df))

    # C3 — SQUARE_FT physical plausibility (field errors only, never price)
    plausible_sqft = df["SQUARE_FT"].between(*SQFT_RANGE)
    before = len(df)
    df = df[plausible_sqft].reset_index(drop=True)
    record("C3 SQUARE_FT outside [100, 20000] dropped", df, before - len(df))

    # C4 — redundant exact complement
    df = df.drop(columns=["READY_TO_MOVE"])
    record("C4 READY_TO_MOVE dropped (exact complement of UNDER_CONSTRUCTION)", df)

    # C5 — schema validation of categorical values
    for col, allowed in KNOWN_VALUES.items():
        unexpected = sorted(set(df[col].unique()) - allowed)
        if unexpected:
            raise ValueError(f"Unexpected categories in {col}: {unexpected}")
    record("C5 categorical values validated against verified schema", df)
    return df, log


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="dataset/processed/cleaned_dataset.csv")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cleaned, log = clean_dataset(pd.read_csv(args.input))
    cleaned.to_csv(out, index=False)
    (out.parent / "cleaning_log.json").write_text(json.dumps(log, indent=2))
    for row in log:
        print(f"{row['step']}: rows={row['rows_after']:,} "
              f"removed={row['rows_removed']:,}")
    print(f"Wrote {out} ({len(cleaned):,} rows x {cleaned.shape[1]} cols)")


if __name__ == "__main__":
    main()
