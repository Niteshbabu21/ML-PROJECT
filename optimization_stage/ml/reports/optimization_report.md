# Optimisation & Performance Investigation Report

Stage question: is R² = 0.96 realistically achievable on this dataset, investigated without inflating training performance, without removing legitimate expensive properties, without target-derived features, and without tuning on the test set. All selection used the grouped validation partition (4,301 rows) and grouped CV only.

## Experiment comparison (validation)

| ID | Model | Change | Valid R² | Valid MAE ₹L | Valid RMSE ₹L | Time s |
|---|---|---|---|---|---|---|
| E00 | xgboost | none (previous stage winner, log track) | 0.8333 | 22.47 | 78.65 | 0.0 |
| E01 | xgboost | none (Optuna best configuration) | 0.8432 | 22.64 | 76.28 | 0.0 |
| E02 | catboost | none (Optuna best configuration) | 0.8381 | 22.21 | 77.50 | 0.0 |
| E03 | lightgbm | none (Optuna best configuration) | 0.8171 | 22.27 | 82.38 | 0.0 |
| E04a | catboost | encoding/loss variant | 0.8374 | 22.63 | 77.68 | 46.5 |
| E04b | catboost | encoding/loss variant | 0.7964 | 24.42 | 86.91 | 80.2 |
| E04c | catboost | encoding/loss variant | -91.4549 | 126.55 | 1852.19 | 308.5 |
| E05a | xgboost | none | -67088.1289 | 49893.44 | 49893.81 | 1.7 |
| E05b | xgboost | none | 0.8146 | 22.81 | 82.94 | 15.3 |
| E06 | xgboost | target: RAW instead of log1p | 0.7351 | 27.37 | 99.14 | 5.3 |
| E07 | xgboost | training target capped at train p99 (₹720L); validation/test | 0.6018 | 27.41 | 121.55 | 8.9 |
| E08a | xgboost | drop experimental pair (geo cluster, lat×lon) | 0.8180 | 23.12 | 82.18 | 9.0 |
| E08b | xgboost | drop locality + its frequency (high-cardinality cost test) | 0.7652 | 25.27 | 93.33 | 5.7 |
| E08c | xgboost | drop low-value trio (quasi-constant, weak, univariate-weak) | 0.8386 | 22.84 | 77.38 | 11.4 |
| E08d | xgboost | core-only: schema v1.1.0 feature set | 0.7430 | 24.92 | 97.66 | 8.7 |
| E09 | ensemble | average of tuned XGB+CB+LGBM (log space) | 0.8415 | 21.34 | 76.70 | 179.7 |
| E10 | xgboost | grouped 3-fold CV of champion E01 | 0.8248 | nan | nan | 28.8 |
| E11 | xgboost | champion refit on train+validation; test scored ONCE in this | 0.7423 | 21.46 | 74.38 | 17.2 |

Optuna detail: E01 = 20 XGBoost trials (best: trial 14), E02 = 16 CatBoost trials, E03 = 20 LightGBM trials — every trial is a row in experiment_log.csv.

## Key diagnostic findings

- Train vs validation R² (A1): XGBoost 0.957 vs 0.833, LightGBM 0.969 vs 0.831, CatBoost 0.921 vs 0.831, Random Forest 0.939 vs 0.782, Linear 0.475 vs 0.575 (underfitting). Capacity is not the constraint; the boosters already fit train near 0.96.
- Duplicate leakage (A6): the same winner configuration on a PLAIN RANDOM split scores validation R² 0.8856 vs 0.8333 grouped — about +0.05 of R² is duplicate leakage that the grouped protocol correctly excludes.
- Noise ceiling (A5): for feature-identical listings the implied maximum R² on covered rows is 0.9978 (3.58% of rows covered). Duplicate label conflicts are therefore real but SMALL in aggregate — they are not the main blocker. The dominant limiter is unobserved heterogeneity: properties whose prices differ for reasons the 20 features cannot see (no bathrooms, age, floor, furnishing or amenity data), confirmed by the twin analysis (A6: validation rows with a repeated-property twin in train score R² 0.9956 vs 0.8301 without — the model prices what it can identify almost perfectly, and the residual error lives in what the features don't describe).
- Learning curve (A7): validation R² 0.744 → 0.785 → 0.826 → 0.842 at 25/50/75/100% of train — still rising slowly, so more data helps a little, but the slope is far too shallow to reach 0.96 by data volume alone.
- Location (A3/A4 in analysis.json): errors concentrate in thin-evidence localities and the >₹400L band; geographic generalisation (previous stage) was R² 0.6056 on unseen localities.
- Failed directions, kept in the log: CatBoost Huber loss diverged (E04c), XGBoost pseudo-Huber diverged (E05a), raw target cost ~0.10 R² (E06), winsorising training targets hurt badly (E07, R² 0.602), dropping locality cost ~0.07 R² (E08b) while dropping the low-value trio slightly helped the OLD configuration (E08c).

## Best validated model

**E01 — Optuna-tuned XGBoost**: validation R² 0.8432, RMSE ₹76.28L; grouped CV R² 0.8248 ± 0.0564 (E10); test, scored once after selection (E11): R² 0.7423, MAE ₹21.46L, RMSE ₹74.38L. The E09 three-booster ensemble was close (validation RMSE ₹76.70L) but did not beat it.

## Verdict on R² = 0.96

**Not realistically achievable with this dataset and feature set.** The gap is not model capacity (train R² already ≈0.96) and only slightly label noise from conflicting duplicates (A5: binds on ~3.6% of rows). It is mostly unobserved price-driving variation — missing attributes (bathrooms, property age, floor, furnishing, amenities), locality-level rather than property-level coordinates, thin evidence for rare localities, and a sparse, hard luxury segment (validation MAE ₹228.7L above ₹400L, with systematic under-prediction). The next scientifically justified improvements, in order: (1) acquire richer property attributes; (2) property-level geocoding and external location features (distances to CBD/transit, locality price indices from independent sources); (3) per-city / luxury-segment models; (4) more listings — the learning curve says data volume alone buys roughly +0.01–0.02, not +0.12.
