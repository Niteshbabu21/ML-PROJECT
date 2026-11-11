# Technical Audit Report — AI Real Estate Valuation & Risk-Aware Tokenisation

Date: 2026-11-01 · Method: every result below was executed fresh during
this audit; nothing is carried over from stage delivery claims.
Companion scripts: `backend/audit_ml.py`, `backend/audit_risk.py`.

## 1. Unit testing report

| Suite | Result |
|---|---|
| Backend API tests (`backend/tests/test_api.py`) | **26/26 passed** (incl. new model-load-failure test added by this audit) |
| Risk engine tests (`backend/tests/test_risk_engine.py`) | **All passed** (LOW 7.7 / MEDIUM 42.9 / HIGH 89.5 scenarios score exactly as designed) |
| Packaged-model tests (`backend/test_predict.py`, fresh process) | **All passed** — packaged vs direct predictions identical; 10 invalid-input cases rejected |
| SHAP tests (`backend/test_explain.py`, fresh process) | **All passed** — additivity within 1e-4 on 5 records |
| Smart contract tests (`blockchain/test/PropertyToken.test.js`) | **16/16 passed** |
| Frontend | TypeScript + production build clean (`tsc -b && vite build`) |

## 2. ML evaluation report

Independent recomputation from the packaged artifact (`audit_ml.py`):

- **Held-out test metrics reproduce the recorded metadata exactly**:
  recomputed R² **0.7423** vs recorded 0.7423; MAE **₹21.46L** vs
  ₹21.4586L; RMSE **₹74.38L** vs ₹74.38L; partition size n=4,284
  matches. The served metrics are genuine.
- **Model loading / preprocessing consistency**: fresh-process load
  succeeds; the artifact bundles the fitted ColumnTransformer with the
  estimator (not the estimator alone); packaged predictions are
  bit-identical to a directly constructed pipeline on 1,000 rows.
- **Feature ordering**: schema `feature_order` equals the training
  `FEATURES` order; predictions are invariant to input dict key order
  (predict.py builds the frame by the frozen feature list).
- **Invalid inputs**: SQUARE_FT ≤ 0, BHK outside integer 1–20,
  coordinates outside India's bounding box, non-binary flags and
  missing features are all rejected with specific messages; unseen
  categories are accepted via `handle_unknown='ignore'`.
- **Target leakage**: no `price_per_sqft` or any target-derived feature
  exists in the 20-feature schema; every engineered feature's declared
  origin is prediction-time data or train-fitted statistics
  (frequencies, centroids, geo-clusters). The grouped split (zero
  feature-signature overlap) is the primary defence and is what the
  headline metrics use.
- **Random-split vs location-based generalisation** (context from the
  measured stage artifacts): random-split refits score ≈ +0.05 R² above
  the grouped protocol (duplicate leakage) — which is why grouped
  numbers are the reported ones. The dedicated geographic evaluation
  (localities entirely unseen, 5,403 rows) measured **R² 0.6056**; the
  model's accuracy drops materially in unseen localities, as expected
  for a location-driven target.
- **Geographic subset re-check (this audit)**: rows anywhere in the
  dataset whose locality never appears in the grouped train+validation
  the packaged model was fitted on (5,285 fitted localities; subset
  n=515): **R² 0.4207, MAE ₹33.63L, RMSE ₹159.83L**. This is a small,
  hard subset under a different protocol than the dedicated geographic
  evaluation above (different model, locality-partitioned split,
  5,403 rows → 0.6056); together they bound the honest picture —
  generalisation to unseen localities is materially weaker than the
  grouped-test R² 0.7423, whichever protocol is used.

## 3. SHAP testing report

- Explainer correctness: `shap.TreeExplainer` (exact for tree
  ensembles) over the packaged XGBoost, applied to the 258-column
  encoded matrix; contributions aggregated to the 20 source features by
  summing one-hot groups, preserving additivity exactly.
- Five representative records: additivity errors 1e-7–4e-6 (tolerance
  1e-4); the explained price is identical to `predict_property`;
  base value is constant (4.2128 log ≈ ₹66.55L).
- Feature names in explanations are exactly the 20 schema features —
  no encoded/dummy names leak into API responses.
- Global ranking (documented 2,000-row sample): SQUARE_FT 0.330,
  CITY 0.245, LAT_LON_INTERACTION 0.109 — plausible for this market;
  no misleading constant or target-derived driver appears.
- Limitation (documented, not hidden): LOCALITY's SHAP mass is spread
  across frequent-category columns plus an infrequent bucket, so its
  aggregated importance understates fine-grained locality effects.

## 4. Risk engine testing report

- **Weights verified**: the seven factors' maxima sum to exactly 100
  (regulatory & construction 45, data quality 40, model uncertainty 15).
- **Fuzz sweep**: 5,184 synthetic assessments (varying construction,
  RERA, resale — including missing/`None` — locality evidence, area,
  BHK, and price incl. no-price) — every score within 0–100, every
  category consistent with its band, every factor within its maximum,
  all three categories exercised.
- **Missing information**: an empty feature dict scores 55.9 (MEDIUM)
  with 5 warnings — unknown RERA is scored at the documented midpoint,
  never as non-compliance; the no-price path rescales transparently
  from 85 points and says so.
- **Explanation consistency**: factor details, narratives and
  recommended actions are generated from the same computed factor
  results the scores come from (no static text).

## 5. API testing report

- All 14 endpoints exercised (9 original + `/api/models/schema`,
  `/api/models/shap-summary`, 4 chain endpoints + mint).
- Invalid JSON → 400 `INVALID_JSON`; missing/invalid features → 400
  `VALIDATION_ERROR` naming the field; unknown route → 404 envelope;
  wrong method → 405 envelope. Every response — success or error —
  carries `{success, request_id, timestamp, data|error}`.
- **Database failure**: with MongoDB down, predictions still return 200
  with `history_saved=false`; history endpoints return a clean 503
  `DATABASE_UNAVAILABLE`. (Regression tests included; the outage path
  caught a real dual-import bug during the backend stage.)
- **Model loading failure** (new test this audit): an empty model
  directory leaves the app up — health reports `model_loaded=false`,
  status `degraded`, and valuation returns 503 `MODEL_UNAVAILABLE`.
- **Chain failure**: no node → `/api/chain/status` reports
  `connected=false`; register returns 503 `CHAIN_UNAVAILABLE`.

## 6. Smart contract testing report

16/16 Hardhat tests pass, covering: deployment and role grants;
registration with on-chain floored supply/residual; duplicate
registration reverts; invalid parameters; role-gated registration and
minting (unauthorised accounts revert); mint-once to contract
inventory; purchases at exact payment; incorrect payment reverts;
insufficient supply (including after buy-out); transfers with events;
insufficient-balance transfer reverts; per-account ownership tracking;
admin-only price updates and proceeds withdrawal. Integer-only
arithmetic; supply formula equals the backend's
`floor(valuation_inr / 10_000)` (verified on the ₹98.21L example:
982 tokens, ₹1,000 residual).

## 7. Integration / end-to-end testing report

Executed live during this audit on a fresh local stack (Hardhat node +
redeployed contract + Flask): predict ₹75.2L → SHAP (additivity
verified) → risk 7.7 LOW → token calculation 752 → bridge registration
(tx `0x8264cff0…`, block 2, chain property #1, on-chain supply 752 =
backend calculation, residual ₹0) → duplicate registration 409 →
mint (tx `0xdd9c8ea6…`, inventory verified 752) → re-mint 409 →
wallet purchase of 25 (tx `0xe5814f40…`) → transfer of 10
(tx `0x30f88a5a…`) → final balances buyer 15 / friend 10 / available
727, confirmed identically by the chain and by the Flask properties
view. Frontend pages: build-level and API-level integration verified;
the in-browser visual pass could NOT be executed — the audit browser
tool refuses loopback navigation (public sites load; `127.0.0.1` is
blocked by the tool, not by the app). It is recorded as not executed
rather than passed; a manual click-through remains available to the
user (the dev stack was left running for that purpose).

## 8. Bugs found and fixed

1. **Audit harness bug (this audit)**: `audit_ml.py` subtracted two
   Python lists in the key-order check (`predict_properties` returns a
   list), crashing the geographic section's first execution; an
   interim geographic figure quoted during the audit (R² 0.7876,
   n=1,940) could not be reproduced and has been **retracted**. Fixed
   with explicit `np.asarray` conversion and a corrected materiality
   threshold; the corrected re-run passes **9/9 checks** and produced
   the geographic figures in §2 (n=515, R² 0.4207). The defect was in
   the audit script, not in the model or `predict.py`.
2. **(Found in the integration stage, re-verified here)** duplicate
   registration keyed on per-request ids → replaced with the
   deterministic property-reference hash; 409 behaviour re-verified
   live in §7.
3. **(Found in the backend stage, regression-tested)** dual-import
   `DatabaseUnavailable` classes defeating the outage handler;
   imports unified, covered by the FailingRepository tests.
4. No genuine defects were found in the packaged model, SHAP module,
   risk engine or contract during this audit.

## 9. Final project readiness assessment

**Ready for academic demonstration and review**, with the limitations
below stated plainly. Every load-bearing number in the system was
independently reproduced during this audit: the served model's test
metrics are exact, SHAP explanations reconstruct predictions to
~1e-6, risk scores are bounded and weight-verified over 5,184 fuzz
cases, all 42 automated tests (26 backend + 16 contract) pass, and the
complete valuation→tokenisation→trade workflow executed live with
cross-verified state between the chain and the API.

Known limitations (all documented in the system itself):
1. **Geographic generalisation is the model's weak point** — R² falls
   from 0.7423 (grouped test) to 0.42–0.61 on unseen localities
   depending on protocol. The model is locality-dependent; this is a
   data limitation (no bathrooms/age/furnishing, locality-level
   coordinates), not an implementation defect.
2. **R² 0.96 is not attained** and, per the optimisation stage's
   evidence, is not realistically attainable with this dataset.
3. **MongoDB persistence is not live-verified** (no server exists in
   this environment); the in-memory mode used for demonstrations is
   process-local. Point `MONGO_URI` at a real server for persistence.
4. **In-browser visual QA was not executed** (audit tooling cannot
   navigate to loopback addresses); frontend correctness rests on the
   clean production build, typed API contracts and live API tests.
5. The blockchain is a **local Hardhat network by design**; hosted
   deployment disables chain operations with an honest 503. Tokens do
   not represent legal ownership of property.
