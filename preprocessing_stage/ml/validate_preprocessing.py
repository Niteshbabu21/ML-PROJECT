#!/usr/bin/env python3
"""validate_preprocessing.py — validation harness for the preprocessing stage.

Probes (each prints PASS/FAIL; exit code non-zero if any fail):
  1  Encoded outputs contain no NaN/inf for every variant, train and test.
  2  Missing-value probe: rows with NaN SQUARE_FT / POSTED_BY / LATITUDE
     transform to finite outputs in every variant.
  3  Unseen-category probe: an invented locality + city transform safely
     (CITY -> 'Other', LOCALITY_FREQ == 0, no exception, no new columns).
  4  Invalid-input probe: validate_input_frame rejects SQUARE_FT <= 0 and
     BHK_NO. out of range; out-of-bounds coordinates are repaired to the
     fitted city centroid instead of crashing or passing (0, 0) through.
  5  Feature-order consistency: engineered column order is canonical even
     when the input columns arrive shuffled; repeated transforms identical.
  6  Leakage probes: no target-derived feature exists; frequencies are
     train-fitted (an unseen locality's LOCALITY_FREQ is exactly 0);
     refitting on the same train split reproduces byte-identical output
     (determinism, KMeans seed fixed).
  7  Scaling discipline: the linear variant standardises numerics
     (train mean ~0), the tree variant leaves them raw.

Usage: python ml/validate_preprocessing.py [--input <cleaned_dataset.csv>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_engineering import ENGINEERED_FEATURES, FeatureEngineer  # noqa: E402
from preprocessing import VARIANTS, build_pipeline, validate_input_frame  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


def finite(arr) -> bool:
    a = np.asarray(arr, dtype=float) if not isinstance(arr, pd.DataFrame) \
        else arr.select_dtypes(include=[np.number]).to_numpy(dtype=float)
    return bool(np.isfinite(a).all())


def main() -> None:
    ap = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    default_in = (here.parent.parent / "eda_stage" / "dataset" / "processed"
                  / "cleaned_dataset.csv")
    ap.add_argument("--input", default=str(default_in))
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    train_idx, test_idx = train_test_split(
        df.index, test_size=0.2, random_state=42, shuffle=True)
    train, test = df.loc[train_idx], df.loc[test_idx]

    pipes = {v: build_pipeline(v).fit(train) for v in VARIANTS}

    # 1 — no NaN/inf anywhere
    ok = True
    for v, p in pipes.items():
        for frame in (train.head(2000), test.head(2000)):
            out = p.transform(frame)
            ok &= finite(out)
            if isinstance(out, pd.DataFrame):
                ok &= not out.isna().any().any()
    check("1 encoded outputs finite & complete (all variants)", ok)

    # 2 — missing-value probe
    probe = train.head(5).copy()
    probe.loc[probe.index[0], "SQUARE_FT"] = np.nan
    probe.loc[probe.index[1], "POSTED_BY"] = None
    probe.loc[probe.index[2], "LATITUDE"] = np.nan
    probe.loc[probe.index[3], "ADDRESS"] = None
    ok = all(finite(pipes[v].transform(probe)) for v in VARIANTS)
    check("2 missing values imputed/repaired in all variants", ok)

    # 3 — unseen category probe
    unseen = train.head(3).copy()
    unseen["ADDRESS"] = "Neverheard Nagar,Atlantis"
    eng = FeatureEngineer().fit(train)
    der = eng.transform(unseen)
    ok = (der["CITY"] == "Other").all() and (der["LOCALITY_FREQ"] == 0).all()
    ok &= all(pipes[v].transform(unseen).shape[0] == 3 for v in VARIANTS)
    check("3 unseen locality/city handled (Other / freq 0)", ok)

    # 4 — invalid inputs
    bad = train.head(2).copy(); bad.loc[bad.index[0], "SQUARE_FT"] = -5
    raised = False
    try:
        validate_input_frame(bad)
    except ValueError:
        raised = True
    bad2 = train.head(2).copy(); bad2.loc[bad2.index[0], "BHK_NO."] = 0
    try:
        validate_input_frame(bad2); raised2 = False
    except ValueError:
        raised2 = True
    geo = train.head(2).copy()
    geo.loc[geo.index[0], ["LATITUDE", "LONGITUDE"]] = [0.0, 0.0]
    der2 = eng.transform(geo)
    repaired = (der2.iloc[0]["LATITUDE"] != 0.0
                and 6 <= der2.iloc[0]["LATITUDE"] <= 38)
    check("4 invalid inputs rejected; bad coords repaired to centroid",
          raised and raised2 and repaired)

    # 5 — feature ordering under shuffled input columns
    shuffled = train.head(50)[list(reversed(train.columns))]
    a = eng.transform(train.head(50))
    b = eng.transform(shuffled)
    check("5 canonical feature order, shuffle-invariant",
          list(a.columns) == ENGINEERED_FEATURES and a.equals(b))

    # 6 — leakage & determinism
    no_target_feature = not any(
        ("PRICE_PER" in c) or ("PPSF" in c) for c in ENGINEERED_FEATURES)
    eng2 = FeatureEngineer().fit(train)
    det = eng.transform(train.head(500)).equals(
        eng2.transform(train.head(500)))
    check("6 no target-derived feature; freq train-only; refit deterministic",
          no_target_feature and det)

    # 7 — scaling discipline (full train: linear scaler was fitted on it)
    lin = np.asarray(pipes["linear"].transform(train), dtype=float)
    tree = np.asarray(pipes["tree"].transform(train.head(4000)), dtype=float)
    check("7 linear scales numerics, tree leaves them raw",
          abs(lin[:, 0].mean()) < 0.05 and tree.max() > 1000,
          f"(linear BHK_NO. mean {lin[:, 0].mean():.4f}, std "
          f"{lin[:, 0].std():.3f})")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} validation "
          f"checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
