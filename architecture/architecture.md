# System Architecture

**Project:** Machine Learning-Based Real Estate Asset Valuation and Risk-Aware Tokenisation Using Blockchain and Smart Contracts
**Team:** Kummetha Anand Reddy (Lead, ML/XAI/Risk) · M Jaswika (Data/Preprocessing/Docs) · Nitesh Babu (Backend/API, Blockchain Bridge, Smart Contracts) · Kanduri Hari Hara Deeraj (Frontend/Dashboard/Testing)
**Guide:** Dr. Jithendra Kumar Jaiswal, CSE (AI & ML), Dayananda Sagar University
**Status:** ARCHITECTURE FOR APPROVAL — no new implementation has been started from this document. Implementation begins stage-by-stage after approval.
**Source of scope:** Review-1 PPTX (10 slides, file SHA-256 prefix `f1ef8b34b58ceb01` — identical to the copy already archived in the project at `docs/reference/`).

> **Academic prototype notice (applies to every surface of this system):** Tokens are a digital/fractional representation for study and demonstration on a local Ethereum-compatible chain. They are **not** legal proof of property ownership and transfer no right, title or interest in any physical property. The risk score is a documented prototype methodology, **not** validated investment advice or a financial risk ground truth.

---

## 1. What the PPT actually requires (Task 1 — extracted, slide by slide)

| Slide | Requirement extracted |
|---|---|
| 1–2 | Title, team roles (above), and the canonical pipeline: **ML Valuation → SHAP Explanation → Prototype Risk Score → Token Supply → Smart Contract → Local Blockchain** |
| 3 | Supervised **regression** AVM; SHAP per-prediction explanations; documented prototype risk score; Solidity contracts on a **local** Ethereum-compatible network. Contribution claimed is the *reproducible integration*, not novelty of any single component. |
| 6 | Problem: connect ML valuation + transparent prototype risk + valuation-driven fractional-token workflow, executable and inspectable on-chain. Prototype disclaimer (above). |
| 7 (Objectives) | (1) Compare Linear Regression, Random Forest, Gradient Boosting, XGBoost. (2) Evaluate on held-out test with **MAE, RMSE, R², MAPE**; tune XGBoost with RandomizedSearchCV. (3) **SHAP** per-property explanations. (4) Transparent prototype risk scoring from **documented, measurable property-level signals**. (5) Convert predicted value → fractional tokens, **risk-aware**. (6) Solidity: **register, mint, purchase, transfer, ownership tracking** on local chain, tested. |
| 8 (Methodology) | Dataset: Kaggle House Price Prediction Challenge, **29,451 rows × 12 cols**, target `TARGET(PRICE_IN_LACS)`. Steps: inspection → preprocessing (drop 401 duplicates, drop corrupted coordinates, `SQUARE_FT ∈ [100, 20,000]`, extract CITY) → 80/20 split seed 42 → encoding/scaling → model selection → SHAP TreeExplainer + risk LOW/MEDIUM/HIGH → **tokens = value ÷ ₹10,000** → **Flask → Node.js → Solidity → local Hardhat**. |
| 9–10 | 10 verified references. No placeholder citations. |

**Exact dataset contract (verified from `data/raw/train.csv`, not from the slide):**
Raw columns (12): `POSTED_BY, UNDER_CONSTRUCTION, RERA, BHK_NO., BHK_OR_RK, SQUARE_FT, READY_TO_MOVE, RESALE, ADDRESS, LONGITUDE, LATITUDE, TARGET(PRICE_IN_LACS)`.
Two verified defects the architecture must handle forever: (a) the `LONGITUDE`/`LATITUDE` columns are **swapped** (0/29,451 rows plausible as labelled; 29,193 plausible after swap; 258 implausible either way); (b) `READY_TO_MOVE` is the exact complement of `UNDER_CONSTRUCTION` and is dropped.

**Exact system outputs (per property):** predicted price (₹ lakh + ₹ INR + ₹/sq ft), SHAP base value + per-feature contributions, risk score 0–100 + band + component breakdown, token supply (integer), and — on user action — on-chain `propertyId`, mint/buy/transfer transaction hashes and ownership balances.

### 1.1 PPT numbers are reference only — explicitly excluded
Slide 8's performance table (XGBoost R² 0.659, Tuned XGBoost R² 0.664, etc.) and its demo line (3 BHK / 1,500 sq ft / Bangalore → ₹98.21 lakh → risk 11.2 LOW → 982 tokens) are **Review-1 reference material**. Per your instruction and decision **D1**, they are never copied into code, UI, reports or this architecture as results. §3 lists the *measured* results of this codebase, which supersede them.

---

## 2. Architectural principles

1. **One feature schema, three consumers.** `shared/feature_schema.json` (**v1.1.0, frozen**) is the single source of truth. ML trains on it, Flask validates against it, React renders its form from it. Any change = new schema version + decision-log entry + retraining. No component keeps a private copy of the feature list.
2. **Training ≠ inference.** `ml/` fits things; `backend/` never trains, refits or imports training code. All preprocessing (city/locality derivation, imputation, encoding, extended features) lives **inside** the saved pipeline `ml/model.pkl`, so the API cannot silently diverge from training (train/serve skew is the #1 integration risk in this design — see §10).
3. **The browser never touches the chain and never holds keys.** React → Flask → Node.js bridge → Hardhat. Signing keys exist only in the bridge's local `.env` (Hardhat well-known test accounts only).
4. **No fabricated state.** Every number in the UI traces to an artefact file (`final_evaluation.json`, `model_metadata.json`, SHAP artefacts) or a contract read. Constants typed into components are a defect.
5. **Determinism where the PPT demands auditability.** Same input → same price, same SHAP, same risk, same token supply. Token supply is a pure function: `floor(predicted_price_inr / 10_000)`.
6. **Chain is truth for ownership; MongoDB is an index, never the truth.** If Mongo and the chain disagree, the chain wins and Mongo is re-synced from events.
7. **Prototype labelling is a functional requirement**, enforced in API responses (`notice` field) and UI components, not a README footnote.

---

## 3. Reconciliation: PPT plan vs. verified state of this codebase

This is the most important section for your approval. Stages 1–3b of this project are **already built and verified** (2026-10-29). Where the verified evidence forced a deviation from the slide, the deviation is documented and, in my judgement as architect, must be kept:

| # | PPT (Slide 7/8) | Verified reality in this repo | Architectural ruling |
|---|---|---|---|
| R1 | Models: LR, RF, GB, XGBoost only | Benchmark ran **11 candidates × raw/log tracks** (incl. LightGBM, CatBoost, ExtraTrees, HistGB, Dummy). PPT's 4 remain a required subset of the comparison table. | Keep the 11-model benchmark; PPT models are the viva-facing subset. |
| R2 | Tune **XGBoost**; select by **lowest test RMSE** | Selecting on the test set is leakage. Verified protocol (D15/D16): 3-fold CV inside train + validation comparison; **test scored exactly once, after selection**. Also, `RandomizedSearchCV` is *empirically unusable* with CatBoost here (numpy-scalar params break cloning — found by smoke test); tuning used an explicit candidate loop with identical search intent. | **Adopt the verified protocol.** Slide wording should be corrected at the next review; do not re-introduce test-set selection. |
| R3 | Final model implied: Tuned XGBoost | **Final model: CatBoostRegressor, log1p target, extended features** (CV R² 0.7772 ± 0.0460; validation 0.8669), refit on train+validation (24,328 rows) → `ml/model.pkl` (1.4 MB, SHA-256 `921674e1…fd4e6`). One-time test: **R² 0.8253, MAE ₹23.08 lakh, RMSE ₹63.40 lakh, MAPE 22.31%, RMSLE 0.30**; locality-grouped generalisation R² 0.7417. | CatBoost is the production model. XGBoost (benchmark validation winner, test R² 0.7356) is retained at `ml/artifacts/benchmark_winner.pkl` as challenger. |
| R4 | "Remove target extremes" in preprocessing | Verified decision **D5/R6: target is NOT clipped or dropped** (cleaned range ₹0.25–₹9,000 lakh, skew 16.1). Clipping would erase the genuine luxury segment (160 plausible rows > ₹1,000 lakh, e.g. Worli ₹4,000 lakh @ ₹46,998/sq ft). Skew is handled by the log1p target track instead. | Keep D5. Slide wording to be corrected. |
| R5 | SHAP **TreeExplainer** | Correct family for all tree candidates, but the served model is a *pipeline* (preprocessing → CatBoost on log target). SHAP must run on the preprocessed matrix, aggregate one-hot columns back to source features, and handle log-space additivity honestly (§6, Module G). `ml/src/explain.py` is still a placeholder — **Stage 3c is the next ML stage**. | TreeExplainer on the inner CatBoost + aggregation layer; log-space disclosure in API/UI. |
| R6 | Risk score exists (demo: 11.2/100 LOW) | **No formula exists anywhere in the PPT** and decision **D8 is still open**. The demo value cannot be reproduced or reverse-engineered honestly. | A concrete formula is *proposed* in §6 Module H for your approval. Nothing is implemented until D8 is closed. |
| R7 | 96% / R² ≥ 0.95 ambition | Investigated in Stage 3b and **not attained**. Gap is attributed, with evidence, to contradictory duplicate labels (108 feature-identical groups with conflicting prices), missing price-driving attributes (no bathrooms/age/furnishing in the dataset), locality-level coordinates (4,116 distinct pairs for 29,451 rows) and residual field corruption. Larger searches are projected to add ≈ 0.01, not ≈ 0.12. | R² 0.95 stays in all documents as an *investigated target*, never as a result or guarantee (your constraint 3). |
| R8 | Stack: Flask → Node → Solidity/Hardhat local | Matches the built skeleton. Your new brief adds **MongoDB + Vercel/Render/Atlas deployment** and **Framer Motion**, neither in the original skeleton; the existing frontend scaffold is **TypeScript** (your brief says "React.js" without specifying). | Mongo/deployment designed in §8–§9 with a hard constraint (§9.3): a Hardhat local chain cannot be hosted like a web service. TS-vs-JS and Framer Motion are approval decisions (§11). |

**Current verified status by your module list:** A ✅ (EDA report + 12 figures + stats JSON) · B ✅ (preprocessing v2, schema v1.1.0, 29,451 → 28,622 rows) · C ✅ (benchmark) · D ✅ (Stage 3b tuning) · E ✅ (`ml/model.pkl` + `final_evaluation.json`) · F ⏳ designed, not built (Stage 4) · G ⏳ next (Stage 3c) · H ⏳ proposal below (D8 open) · I ⏳ formula frozen, service not built · J ⏳ skeleton only · K ⏳ skeleton only · L/M ⏳ config only · N ⏳ partial (ML tests pass; deployment not attempted).

---

## 4. System context & container architecture

```
                        ┌──────────────────────────────────────────────────┐
                        │   shared/feature_schema.json  (v1.1.0, frozen)   │
                        │   shared/api_contract  ·  shared/city_*.json     │
                        └──────┬────────────────┬──────────────────┬───────┘
                               │ trains on      │ validates on     │ renders from
                    ┌──────────▼───────┐ ┌──────▼───────────────┐ ┌▼───────────────────┐
   OFFLINE          │  ML PIPELINE     │ │  FLASK API (Render)  │ │  REACT SPA (Vercel)│
   (training-time)  │  Python 3.12     │ │  Python 3.12         │ │  Vite + Tailwind   │
                    │  A·B·C·D·E·G     │ │  F·G·H·I·J           │ │  K                 │
                    └──────────┬───────┘ └──┬────────┬───────┬──┘ └─────────▲──────────┘
                               │ artefacts  │ loads  │ reads/│ calls     │ HTTPS/JSON
                               │ model.pkl  │ model  │ writes│ (internal)│ only
                               │ metadata   │  .pkl  │       │           │
                               │ shap json  │        ▼       ▼           │
                               └───────────►│  ┌─────────┐ ┌──────────────┴─┐
                                            │  │ MongoDB │ │ NODE.JS BRIDGE │
                                            │  │ (Atlas) │ │ ethers.js v6   │
                                            │  └─────────┘ └──────┬─────────┘
                                            │   audit/index       │ JSON-RPC, signs
                                            │              ┌──────▼─────────┐
                                            │              │ HARDHAT CHAIN  │
                                            └──────────────│ Solidity 0.8.24│
                                                           │ chainId 31337  │
                                                           │ L·M            │
                                                           └────────────────┘
```

**Containers (deployable/runnable units):** (1) ML training environment — offline, never deployed; (2) Flask API — the only public backend; (3) React SPA — static; (4) Node.js bridge — internal-only service wrapping ethers.js; (5) Hardhat node — local chain process; (6) MongoDB Atlas — managed. Locally all six run on one machine for the viva; in the deployed topology §9 applies, with the chain caveat stated there.

---

## 5. Data flow (end-to-end)

**Training flow (offline, already built):**
`data/raw/train.csv` → Phase-A deterministic cleaning (`ml/src/cleaning.py`: dedupe −401, coordinate repair/drop −255, SQUARE_FT plausibility −173 → 28,622) → **split before any fitting** → train-fitted transformers (`CityLocalityDeriver` + `ColumnTransformer`, tree/linear variants) → benchmark (11 × 2 tracks, 70/15/15, seed 42) → tuning (explicit random-search loop; extended features) → final CatBoost refit on train+validation → `ml/model.pkl` + `reports/optimization/final_evaluation.json` → (Stage 3c) SHAP artefacts + `ml/artifacts/model_metadata.json`.

**Inference flow (one valuation — the demo path):**
React form → `POST /api/v1/predict` → Flask validates against schema v1.1.0 → builds the 10-field API frame (ADDRESS + 8 fields + optional coordinates; missing coordinates → city-centroid fallback, flagged) → `model.pkl` pipeline derives CITY/LOCALITY/`SQUARE_FT_PER_BHK` + extended features internally and predicts (log1p → `expm1` → ₹ lakh) → SHAP service explains that prediction → risk service scores it → token service computes supply → prediction persisted to Mongo (audit) → single JSON response (see API spec) → React renders price, SHAP waterfall/bar (Recharts), risk gauge + breakdown, token panel.

**Tokenisation flow (user action, separate from prediction):**
React "Tokenise" → `POST /api/v1/tokenise {prediction_id, owner_address, risk_acknowledged}` → Flask re-reads the stored prediction (never trusts client-supplied price/supply) → bridge `POST /internal/register` → contract `registerProperty(...)` returns `propertyId` → bridge `POST /internal/mint` → contract `mintTokens(propertyId, owner, supply)` → tx hashes + block numbers returned → Flask records the mirror in Mongo → React shows property card + explorer-style local tx view. Buy/transfer follow the same bridge path (§7).

---

## 6. Module design (A–N)

### A. Dataset management & EDA — ✅ built
Owner: Jaswika. `data/raw/` is immutable (SHA-256 pinned in schema). `ml/src/inspect_dataset.py`, `ml/src/eda.py` → `reports/eda_report.md`, 12 figures, `reports/eda_stats.json`. Exit rule for any future dataset change: new SHA, new inspection, decision-log entry.

### B. Data cleaning & feature engineering — ✅ built (preprocessing v2)
`ml/src/cleaning.py` (Phase A, deterministic, no fitting) + `ml/src/transformers.py` (Phase B, train-fitted only). Rules R1–R6/A1–A5 in `ml/preprocessing_config.json`. Model features (11 API-derived): `POSTED_BY, UNDER_CONSTRUCTION, RERA, BHK_NO., BHK_OR_RK, SQUARE_FT, RESALE, CITY, LOCALITY, LATITUDE, LONGITUDE` + in-pipeline `SQUARE_FT_PER_BHK`; final model adds in-pipeline extended features `LOG_SQUARE_FT, DIST_TO_CITY_CENTROID, CITY_FREQ, LOCALITY_FREQ`. **Prohibited:** any target-derived feature (price/sq ft, locality mean price) — leakage. Encoded width of final pipeline: 205 predictors.

### C. Model training & comparison — ✅ built
`ml/src/train.py` + `ml/src/metrics.py` (single metric definitions: MAE/RMSE/R²/adjusted R²/MAPE with coverage, RMSLE; predictions clipped at 0). Candidates: Dummy, Linear, Ridge, ElasticNet, RandomForest, ExtraTrees, GradientBoosting, HistGradientBoosting, XGBoost, LightGBM, CatBoost × {raw, log1p}. Full table: `reports/benchmark/benchmark_report.md`.

### D. Hyperparameter optimisation — ✅ built
`ml/src/tune.py`: explicit candidate-loop random search (see R2 for why not `RandomizedSearchCV`), Phase-1 benchmark features → Phase-2 extended features for top-2 → Phase-3 voting ensemble gated at +0.003 CV (voting 0.7697 < single best 0.7772, stacking correctly skipped).

### E. Evaluation & serialisation — ✅ built
`ml/src/finalize.py` → `ml/model.pkl` (the **entire fitted pipeline**, joblib) + `reports/optimization/final_evaluation.json`. **New artefact required by this architecture (Stage 3c):** `ml/artifacts/model_metadata.json` — `{model_name, model_version, schema_version, preprocessing_version, fitted_on, n_rows, test_metrics{...copied from final_evaluation.json}, grouped_metrics{...}, model_sha256, library_versions, created_at}`. The backend serves `/model-info` **only** from this file; if it is absent the endpoint says so. This is the artefact-sharing contract of §8.

### F. Property price prediction — Stage 4
`backend/app/services/prediction_service.py`. Loads `model.pkl` **once** at startup (module-level singleton; fail-fast if SHA ≠ metadata). Input = API schema (10 fields); output in ₹ lakh (float, 2 dp), ₹ INR (int), ₹/sq ft (derived display value). Coordinate fallback per D11, response flag `coordinate_source: "provided" | "city_centroid"`. Stateless per request; no caching of predictions (determinism makes caching unnecessary).

### G. SHAP explainability — Stage 3c (next ML stage)
`ml/src/explain.py` (offline global artefacts) + `backend/app/services/explain_service.py` (per-request).
- Explainer: `shap.TreeExplainer` over the pipeline's inner CatBoost regressor, applied to the **preprocessed** row (205 features).
- **Aggregation layer (critical):** one-hot columns are summed back to their source feature (`CITY`, `LOCALITY`, `POSTED_BY`, `BHK_OR_RK`, …) so the UI shows ≤ 15 human features, never 205 dummy columns.
- **Log-target honesty:** SHAP values are additive in **log1p(₹ lakh)** space, not in ₹ lakh. API therefore returns `base_value_log`, `contributions[].effect_log` and `contributions[].share_pct` (signed % of total absolute effect). The UI chart is labelled "relative contribution to the valuation" — it must never claim "this feature added ₹X lakh" as an exact additive lakh figure. (An approximate lakh effect may be shown only if labelled approximate; my recommendation: don't.)
- Global explanation: precomputed `ml/artifacts/shap_summary.json` (mean |SHAP| ranking on a fixed validation sample, seed 42) served via `/model-info`; per-request SHAP is computed live (benchmark the latency in Stage N; if > ~1 s, pre-warm/cache by input hash).
- Fallback: if SHAP fails for a row, prediction still returns with `shap: null` + `explanation_unavailable: true`. Explanation must never block valuation.

### H. Property-level risk scoring — Stage 4, **formula proposed here, approval required (closes D8)**
Constraints from the PPT: transparent, documented, **measurable property-level signals only**, bands LOW/MEDIUM/HIGH, score 0–100. The dataset has **no** market, legal-title, or borrower data — so every component below is computable from the prediction request + train-fitted statistics, and the score is labelled a prototype everywhere.

**Proposed Risk Score v0.1 (weights sum to 100; higher = riskier):**

| Component | Signal (all measurable at prediction time) | Points |
|---|---|---|
| Regulatory | `RERA = 0` (not RERA-registered) | 0 or **20** |
| Completion | `UNDER_CONSTRUCTION = 1` | 0 or **20** |
| Price-anomaly | \|property ₹/sq ft − train-fitted CITY median ₹/sq ft\| ÷ city median: ≤10% → 0; 10–35% → 10; 35–75% → 18; >75% → **25** | 0–25 |
| Locality evidence | LOCALITY unseen in training → 15; seen but rare (< 25 train rows, the pipeline's own threshold) → 8; established → 0 | 0–15 |
| Area plausibility | `SQUARE_FT_PER_BHK` outside train-fitted [P5, P95] band → 10; inside → 0 | 0–10 |
| Configuration rarity | `BHK_NO.` ≥ 8 or `= 1 with SQUARE_FT > 3,000` (rare in training, weakest model support) → 10; else 0 | 0–10 |

Bands (proposed): **LOW 0–29 · MEDIUM 30–59 · HIGH 60–100**. City medians and percentile bands are fitted on the training partition only and shipped as `ml/artifacts/risk_reference.json` (generated in Stage 4 design, versioned `risk_method_version: "0.1"`), so risk is reproducible and cannot drift from training data. The API returns the **full component breakdown** — transparency is the point of the module. Calibration check (Stage 4 exit criterion): score distribution over the test partition must be reported (no band may swallow > 90% of properties without a documented re-threshold decision).

### I. Fractional token calculation — Stage 4
`backend/app/services/token_service.py`. Pure function, no state:
`token_supply = floor(predicted_price_inr / 10_000)`, `inr_per_token = 10_000`, remainder ₹ disclosed in the response (`remainder_inr = predicted_price_inr − supply × 10_000`). **Risk-awareness (proposed, §11 decision):** the risk band does **not** alter supply (supply stays purely value-driven and auditable, exactly as the PPT formula states); instead the band is (a) stored on-chain at registration, (b) emitted in contract events, and (c) a **HIGH** band requires an explicit user acknowledgement in the UI before mint is enabled. Alternatives considered and rejected: scaling supply by risk (breaks the published formula, unauditable) and blocking HIGH outright (makes the demo fragile and over-claims the prototype score's authority).

### J. Flask REST API — Stage 4
App factory (`backend/app/__init__.py`), blueprints per resource, Pydantic v2 request/response schemas generated from schema v1.1.0, service layer (F/G/H/I + chain client + Mongo repository), structured error envelope, CORS locked to the frontend origin, `/api/v1` versioning. Full contract: **`api_specification.md`**. The API never imports `ml/src` training code — only `joblib.load(model.pkl)`, its fitted transformers travel inside the pickle.

### K. React dashboard — Stage 6
Vite + React + Tailwind + Recharts + Framer Motion + Lucide. Pages: **Valuation** (schema-driven form → price card, SHAP chart, risk gauge/breakdown, token panel), **Tokenise** (register/mint/buy/transfer actions, ownership table), **Properties** (Mongo-indexed list, chain-verified state), **Model** (metadata + measured metrics + global SHAP ranking — all from `/model-info`, nothing hard-coded). The frontend contains **no** price, risk or token logic of its own; it renders API responses. Prototype notice is a shared component rendered on every token surface.

### L. Solidity smart contracts — Stage 5
Solidity 0.8.24, Hardhat, OpenZeppelin. **Recommended design: ERC-1155** — one contract, one token-id per property, which natively gives fractional balances, `safeTransferFrom` transfers and `balanceOf` ownership for *many* properties without deploying a contract per property:
- `PropertyTokenisation.sol` (ERC1155 + Ownable): `registerProperty(owner, predictedValueInr, riskScore, riskBand, tokenSupply, metadataHash) → propertyId` (stores the valuation record on-chain, mints nothing yet); `mintTokens(propertyId)` (mints the recorded supply to the owner, once only); `buyTokens(propertyId, amount)` payable at the demo sale price (below); `transfer` = inherited ERC-1155 transfer, surfaced through the bridge; views: `getProperty(propertyId)`, `balanceOf`, `totalMinted`, `ownersOf` via events/indexing.
- **Demo sale price caveat (must be explicit in the viva):** ₹10,000/token is the *valuation denomination*. A local chain has no real ₹/ETH rate, so `buyTokens` uses a **local-demo constant** `DEMO_TOKEN_PRICE_WEI` set at deployment (e.g. 0.001 ETH/token from Hardhat test accounts). It is a mechanics demo, not an FX rate, and is named as such in code and UI.
- Events for every state change (`PropertyRegistered`, `TokensMinted`, `TokensPurchased`, `TransferSingle` inherited) — Mongo indexing and the UI both consume events, not guesses.
- Fallback if the team prefers to avoid OpenZeppelin: a custom single-contract ledger implementing the same function surface. ERC-1155 is recommended (standard, testable, less custom code to defend), but this is listed as an approval decision in §11.

### M. Blockchain integration — Stage 5
`blockchain/bridge/` — a small Node.js (ethers.js v6) HTTP service, **internal only** (no public port in deployment; Flask is its only caller). Responsibilities: hold the deployer key (local test account), translate Flask calls → contract calls, wait for 1 confirmation, return `{tx_hash, block_number, property_id, gas_used}`; expose `/internal/health` reporting RPC reachability + deployed contract address (from `blockchain/deployments/localhost.json`, written by the deploy script — the bridge and Flask never hard-code an address). Idempotency: Flask passes `prediction_id`; the bridge refuses a second register for the same prediction unless `force` is set (prevents duplicate on-chain properties from double-clicks/retries). Failure mode: chain down → tokenise endpoints return `503 CHAIN_UNAVAILABLE`; prediction endpoints are unaffected (valuation must demo even if the chain is stopped).

### N. Testing & deployment — Stage 7 (continuous from Stage 4)
Tests: ML `pytest` (existing preprocessing/metrics suites + new SHAP/risk tests), backend `pytest` (validation, determinism vs `model.pkl`, risk breakdown sums, token floor math, chain-down 503), contracts `hardhat test` (register/mint/buy/transfer/ownership + negative cases: double-mint, over-supply buy, non-owner mint), bridge integration test against a throwaway Hardhat node, frontend Vitest + one Playwright end-to-end run of the exact demo flow. Deployment: §9.

---

## 7. Blockchain interaction sequence (normative)

```
Deploy (once, local):  hardhat node → deploy.ts → PropertyTokenisation deployed
                       → deployments/localhost.json {address, chainId 31337, deployer}
Register:  UI → Flask POST /tokenise → Mongo: prediction lookup (price/supply/risk server-side)
           → Bridge → registerProperty(owner, valueInr, riskScore, band, supply, sha256(input))
           → event PropertyRegistered(propertyId) → Flask mirrors to Mongo → UI shows propertyId + tx
Mint:      Bridge → mintTokens(propertyId)  [guard: not previously minted; supply == recorded supply]
           → TokensMinted → Mongo mirror updated
Buy:       UI (buyer = second Hardhat account) → Flask → Bridge → buyTokens(propertyId, n) payable
           [guards: minted, n ≤ available, value == n × DEMO_TOKEN_PRICE_WEI]
Transfer:  Bridge → safeTransferFrom(from, to, propertyId, n, 0x) → balanceOf reflects new ownership
Verify:    UI ownership view = contract reads via Bridge/Flask (Mongo shown only as cached index,
           labelled with last-synced block)
```
Rules: Flask never signs; bridge never values; contract never computes price/risk/SHAP (off-chain facts are *recorded*, with their metadata hash, not re-derived on-chain); every tx response carries `network: "hardhat-local", chain_id: 31337`.

---

## 8. Artefact & metadata sharing contract

| Artefact | Producer | Consumer(s) | Rule |
|---|---|---|---|
| `shared/feature_schema.json` v1.1.0 | Stage 2 (frozen) | ML, Flask, React | Change ⇒ version bump + retrain |
| `ml/model.pkl` (1.4 MB, SHA-256 `921674e1…fd4e6`) | `ml/src/finalize.py` | Flask (load once) | Backend verifies SHA vs metadata at startup |
| `ml/artifacts/model_metadata.json` | Stage 3c (new) | Flask `/model-info`, React Model page | Sole source of displayed metrics |
| `reports/optimization/final_evaluation.json` | Stage 3b ✅ | Metadata generator | Test metrics copied, never retyped |
| `ml/artifacts/shap_summary.json` | Stage 3c | Flask, React | Fixed sample + seed recorded inside |
| `ml/artifacts/risk_reference.json` | Stage 4 | Flask risk service | Train-fitted city medians/percentiles + `risk_method_version` |
| `shared/city_centroids.json`, `city_grouping.json` | Stage 2 | Coordinate fallback (via the pipeline's fitted deriver — see note) | Backend reads fitted values **from the loaded pipeline** where possible, so fallback can never diverge from training |
| `blockchain/deployments/localhost.json` | Deploy script | Bridge, Flask | Contract address never hard-coded |
| Mongo `predictions` / `properties` / `token_events` | Flask / event indexer | React (via Flask) | Index only; chain is truth (§2.6) |

---

## 9. Deployment topology (Vercel / Render / Atlas) — and its one hard constraint

### 9.1 Topology
- **Vercel:** React SPA (static build). Env: `VITE_API_BASE_URL` → Render backend. No server code, no keys.
- **Render (web service):** Flask via gunicorn (`backend/requirements.txt` — inference deps incl. the ML libs needed to *load* the pipeline). Startup: load + SHA-verify `model.pkl`. Env: `MONGO_URI`, `BRIDGE_BASE_URL`, `CORS_ORIGIN`, `MODEL_PATH`.
- **MongoDB Atlas:** `predictions`, `properties`, `token_events`, `chain_sync` collections; least-privilege DB user; IP allowlist includes Render egress.
- **Bridge:** in *local mode* it runs on the demo machine next to the Hardhat node. In *deployed mode* see 9.3.

### 9.2 MongoDB's job (and only that job)
Prediction audit log (input, output, model/risk versions, timestamps — powers History + reproducibility), property/token mirror indexed from contract events (fast list views), and demo portfolio cache. **No** user accounts/auth in scope (not in the PPT); **no** valuation state lives only in Mongo.

### 9.3 ⚠️ The constraint you must approve knowingly
**A Hardhat local chain is a process on one machine — it cannot be "deployed" to Vercel/Render as a persistent public blockchain, and its state vanishes when the process stops.** Therefore the architecture supports two honest modes:
- **Mode 1 — Local demo (primary, matches the PPT exactly):** all containers on one machine; chainId 31337; full register→mint→buy→transfer works. This is the viva configuration.
- **Mode 2 — Hosted showcase:** Vercel + Render + Atlas live; valuation/SHAP/risk/history fully work; tokenise endpoints return `503 CHAIN_UNAVAILABLE` with a clear UI explanation **unless** a reachable RPC is configured. Pointing the bridge at a public testnet (e.g. Sepolia) is a possible *stretch* stage — it changes the PPT's "local blockchain" claim, needs a faucet-funded test wallet, and is **not** in this architecture's committed scope.

Any demo script that shows hosted tokenisation without one of the above would be fabrication, so the UI must display the active mode (`network` field in every token response).

---

## 10. Integration risks & mitigations

| # | Risk | Severity | Mitigation in this design |
|---|---|---|---|
| 1 | Train/serve skew (backend preprocessing diverges from training) | **High** | All preprocessing inside `model.pkl`; backend imports no training code; determinism test: backend prediction == offline pipeline prediction on fixed fixtures |
| 2 | Pickle portability (library versions) | High | Backend pins the *exact* verified versions (lock file) — CatBoost 1.2.10 / sklearn 1.6.1 / numpy 2.0.2 / pandas 2.3.3 / Python 3.12; SHA check at startup; model re-export is a retraining event, not a config change |
| 3 | SHAP log-space misreading (UI claims ₹-additive effects) | Medium | API returns log effects + share % only; UI copy reviewed against §6G wording |
| 4 | SHAP latency on 205 features per request | Medium | Benchmark in Stage N; fallback `shap: null`; optional input-hash cache |
| 5 | Risk formula challenged as arbitrary in viva | Medium | Every component is a documented measurable signal; breakdown returned; D8 records approval; calibration distribution reported |
| 6 | Local chain state loss / address drift between runs | Medium | Deploy artefact file; bridge reads address from it; demo run-book starts with a fresh deploy step |
| 7 | Duplicate on-chain registration on retry/double-click | Medium | `prediction_id` idempotency in bridge + Mongo unique index |
| 8 | Render cold start + model load time / free-tier spin-down | Low–Med | Load once at boot, `/health` warms it; demo run-book includes a wake-up call; model is only 1.4 MB |
| 9 | Mongo ↔ chain divergence | Low | Event-based re-sync; ownership views labelled with last-synced block; chain read is the tiebreak |
| 10 | Unseen CITY/LOCALITY at inference (625 test localities were unseen in training) | Low | Handled inside the fitted pipeline (`handle_unknown='ignore'`, rare→`Other`); API validation accepts any ADDRESS string and lets the pipeline cope — validation rejects *malformed* input, not *novel* input |
| 11 | Framer Motion / React 19 upgrade churn | Low | Pin React 18.3 (Recharts-compatible, matches existing scaffold); add `framer-motion` only |
| 12 | Secrets leakage (keys/URI in repo or frontend) | High if mishandled | Keys only in bridge `.env`; frontend bundle contains zero secrets by construction (it never calls the chain); `.env.example` documents names only |

---

## 11. Decisions required from you before implementation

These are the only open choices. My recommendation is marked; implementation of the affected stage waits for your word (per your "wait for my approval" instruction — everything else in this document follows your brief + verified project decisions D1–D16).

1. **Risk formula (§6H)** — approve Risk Score v0.1 weights/bands as proposed, or adjust. *(Recommendation: approve; calibration report will validate the bands on the test partition.)*
2. **Risk-aware tokenisation (§6I)** — risk recorded on-chain + HIGH requires UI acknowledgement; supply unchanged. *(Recommendation: approve.)*
3. **Contract standard (§6L)** — ERC-1155 + OpenZeppelin vs. custom ledger contract. *(Recommendation: ERC-1155.)*
4. **Demo ETH price (§6L)** — `DEMO_TOKEN_PRICE_WEI = 0.001 ETH/token` as a named local-demo constant. *(Recommendation: approve, with the viva caveat documented.)*
5. **Frontend language** — keep the existing **TypeScript** scaffold (type-safe API contract, already built) vs. rewrite to plain JavaScript per a literal reading of "React.js". *(Recommendation: keep TypeScript; add Framer Motion.)*
6. **Deployment mode (§9.3)** — Mode 1 local as the committed demo; Mode 2 hosted for valuation-only showcase; Sepolia as an optional stretch, out of committed scope. *(Recommendation: approve as stated.)*

---

## 12. What happens on approval

Approval of this architecture (with any changes to §11) triggers **Stage 3c (SHAP)** first — it is the next stage on the verified roadmap and the Flask stage depends on its artefacts — followed by Stage 4 (Flask + risk + token services). No stage starts early, and each stage ends with the verification evidence listed in `development_roadmap.md`.
