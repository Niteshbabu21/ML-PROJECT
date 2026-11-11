# Preprocessing & Feature Engineering Report

Input: cleaned dataset (28,622 rows, previous EDA stage). Split before fitting: train 22,897 / test 5,725.
Kept cities (train-fitted, >= 200 rows): 18 incl. 'Other'. Geo clusters: 32 (KMeans on training coordinates).

## Target skewness

Train target skew: **16.79** raw -> **0.68** after log1p. Recommendation: train/evaluate on the log1p track as primary and report metrics back-transformed to ₹ lakh. The target itself is never clipped or winsorised (genuine luxury tail — EDA).

## Encoded widths per model family (fitted on train)

| Variant | Representation | Width |
|---|---|---|
| tree | one-hot matrix | 243 |
| linear | one-hot matrix + scaling | 243 |
| catboost | native categorical frame | 20 |
| lightgbm | native categorical frame | 20 |

## Feature selection (training split only)

Keep: 15 · Keep flagged: 4 · Drop candidates: 1

- **POSTED_BY** — keep: train association 0.647 (median-spread ratio)
- **UNDER_CONSTRUCTION** — keep: train association 0.082 (median-spread ratio)
- **RERA** — keep: train association 0.264 (median-spread ratio)
- **BHK_NO.** — keep: train association 0.502 (Spearman)
- **BHK_OR_RK** — keep_flagged: quasi-constant (99.9% one value) — near-zero signal expected; retained for schema stability, drop if ablation agrees
- **SQUARE_FT** — keep: train association 0.561 (Spearman)
- **RESALE** — keep: train association 0.049 (median-spread ratio)
- **CITY** — keep: train association 1.771 (median-spread ratio)
- **LOCALITY** — keep_flagged: very high cardinality (5152) — encoded with min_frequency=25 / native fallback so rare and unseen localities are safe
- **LATITUDE** — keep: train association 0.156 (Spearman)
- **LONGITUDE** — keep: train association 0.177 (Spearman)
- **SQUARE_FT_PER_BHK** — keep: train association 0.282 (Spearman)
- **LOG_SQUARE_FT** — keep: train association 0.561 (Spearman)
- **DIST_TO_CITY_CENTROID** — drop_candidate: near-zero monotone association with target on train (|Spearman| 0.005)
- **CITY_FREQ** — keep: train association 0.073 (Spearman)
- **LOCALITY_FREQ** — keep: train association 0.249 (Spearman)
- **LAT_LON_INTERACTION** — keep_flagged: experimental engineered feature — retained for the training stage to ablate, not assumed useful
- **SQFT_BAND** — keep: train association 3.822 (median-spread ratio)
- **BHK_CONFIG** — keep: train association 11.153 (median-spread ratio)
- **GEO_CLUSTER** — keep_flagged: experimental engineered feature — retained for the training stage to ablate, not assumed useful

Full per-feature statistics: `feature_selection.json`. Validation probes (missing / unseen / invalid / ordering / leakage): `ml/validate_preprocessing.py` — results in the stage delivery message and re-runnable at any time.

