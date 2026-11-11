# Folder Structure

**Status:** FOR APPROVAL. This is the *target* structure for the existing repository at `~/workspace/real-estate-valuation-tokenisation/`. It deliberately **evolves the verified Stage 1–3b layout** instead of replacing it — everything marked ✅ already exists; ⏳ is to be created in its roadmap stage; 🔒 is frozen/immutable by rule.

Design rules: (1) training code, inference code, chain code and UI code never share a directory; (2) every cross-component contract lives in `shared/` or `ml/artifacts/` as data, not code; (3) generated files are reproducible from a script in the same tree; (4) no secrets, no `.env`, no chain keys are ever committed (`.env.example` documents names only).

```
real-estate-valuation-tokenisation/
│
├── README.md                          ✅ Run-book: modes, quick-start per stage, prototype notice
├── ARCHITECTURE.md                    ⏳ Replaced by the approved architecture.md (Stage 4 entry)
├── ROADMAP.md                         ⏳ Updated from development_roadmap.md on approval
├── .env.example                       ✅ Variable names only (Flask, Mongo, bridge, frontend, chain)
├── .gitignore                         ✅ .venv, node_modules, .env, artifacts/cache, deployments (except .gitkeep)
│
├── data/
│   ├── raw/
│   │   └── train.csv                  🔒 Immutable. 29,451 × 12. SHA-256 b9603886… (pinned in schema)
│   └── processed/
│       ├── v2/                        ✅ phase_a_cleaned.csv, train.csv, test.csv,
│       │                                 grouped_train.csv, grouped_test.csv, data_quality_log.json
│       └── (v1 artefacts)             ✅ Retained for traceability only — superseded (D13)
│
├── ml/                                        # MODULES A–E, G (offline / training-time only)
│   ├── requirements.txt               ✅ Ranges (see requirements.txt deliverable for pinned set)
│   ├── requirements.lock.txt          ✅ pip freeze of the verified environment (Python 3.12.3)
│   ├── preprocessing_config.json      ✅ Preprocessing v2.0.0 config (rules, fitted-component spec)
│   ├── model.pkl                      ✅🔒 FINAL fitted pipeline — CatBoost/log/extended.
│   │                                     1.4 MB · SHA-256 921674e1…fd4e6 · written ONLY by finalize.py
│   ├── artifacts/
│   │   ├── benchmark_winner.pkl       ✅ Challenger model (XGBoost raw) — never served
│   │   ├── winner_info.json           ✅
│   │   ├── city_state_v2.json         ✅ Train-fitted city state
│   │   ├── tuned/                     ✅ Phase-1/2/3 tuned pipelines (experiment record)
│   │   ├── model_metadata.json        ⏳ Stage 3c — THE artefact the API serves (see architecture §8)
│   │   ├── shap_summary.json          ⏳ Stage 3c — global SHAP ranking (fixed sample, seed 42)
│   │   └── risk_reference.json        ⏳ Stage 4 — train-fitted city medians / percentile bands + risk_method_version
│   ├── src/
│   │   ├── inspect_dataset.py         ✅ A — dataset inspection → docs/dataset_inspection.*
│   │   ├── eda.py                     ✅ A — EDA → reports/eda_report.md + figures + stats
│   │   ├── cleaning.py                ✅ B — Phase-A deterministic cleaning (R1–R6)
│   │   ├── transformers.py            ✅ B — CityLocalityDeriver + ColumnTransformer factory (train-fitted)
│   │   ├── schema.py                  ✅ B — target/feature constants bound to shared schema
│   │   ├── metrics.py                 ✅ C — single metric definitions (MAE/RMSE/R²/adj-R²/MAPE/RMSLE)
│   │   ├── train.py                   ✅ C — benchmark: 11 candidates × raw/log tracks
│   │   ├── tune.py                    ✅ D — explicit-loop random search + extended features + ensemble gate
│   │   ├── finalize.py                ✅ E — selection, refit on train+valid, save model.pkl, test ONCE
│   │   ├── evaluate.py                ✅ E — winner evaluation + grouped generalisation + plots
│   │   ├── explain.py                 ⏳ G — Stage 3c: SHAP artefacts + aggregation layer (currently placeholder)
│   │   └── archive_preprocess_v1.py   ✅ Superseded v1 script, kept for traceability (D13)
│   ├── tests/
│   │   ├── test_preprocessing.py      ✅ 5 tests
│   │   ├── test_metrics.py            ✅ 4 tests
│   │   └── test_explain.py            ⏳ G — aggregation sums back to model output (log space), fixture rows
│   └── notebooks/                     ✅ Empty by discipline — experiments live in src/, not notebooks
│
├── backend/                                   # MODULES F–J (inference only — never trains)
│   ├── requirements.txt               ✅ Inference pins (Flask + ML libs to LOAD the pipeline) — see deliverable
│   ├── run.py                         ✅ Entry: `flask --app run run` / gunicorn `run:app`
│   ├── app/
│   │   ├── __init__.py                ⏳ App factory: config, CORS, blueprint + error-handler registration,
│   │   │                                 model singleton load + SHA verification (fail-fast)
│   │   ├── config.py                  ⏳ Env-driven config (MODEL_PATH, MONGO_URI, BRIDGE_BASE_URL, CORS_ORIGIN)
│   │   ├── routes/
│   │   │   ├── health.py              ⏳ GET /health
│   │   │   ├── model_info.py          ⏳ GET /api/v1/model-info
│   │   │   ├── predict.py             ⏳ POST /api/v1/predict · GET /api/v1/predictions[/{id}]
│   │   │   ├── tokenise.py            ⏳ POST /api/v1/tokenise · /tokenise/buy · /tokenise/transfer
│   │   │   └── properties.py          ⏳ GET /api/v1/properties[/{id}] · /properties/{id}/ownership
│   │   │                                 · GET /api/v1/owners/{address}/portfolio
│   │   ├── schemas/
│   │   │   ├── property.py            ⏳ Pydantic v2 models generated from feature_schema v1.1.0
│   │   │   └── responses.py           ⏳ Prediction/Token/Property response models + error envelope
│   │   ├── services/
│   │   │   ├── model_service.py       ⏳ Loads model.pkl once; predict() — the ONLY joblib consumer
│   │   │   ├── prediction_service.py  ⏳ F — frame building, centroid fallback flag, unit conversions
│   │   │   ├── explain_service.py     ⏳ G — per-request SHAP + one-hot aggregation (never blocks prediction)
│   │   │   ├── risk_service.py        ⏳ H — Risk Score v0.1 from risk_reference.json; returns full breakdown
│   │   │   ├── token_service.py       ⏳ I — floor(value_inr / 10_000); remainder; risk-ack gate for HIGH
│   │   │   └── chain_client.py        ⏳ M — HTTP client for the bridge; maps failures → 503 CHAIN_UNAVAILABLE
│   │   └── repositories/
│   │       └── mongo_repo.py          ⏳ N — predictions / properties / token_events access (pymongo);
│   │                                     unique index on predictions.prediction_id; chain is truth, this is index
│   └── tests/
│       ├── test_validation.py         ⏳ 422 matrix: unknown category, out-of-range, missing field, novel locality OK
│       ├── test_prediction_determinism.py ⏳ API prediction == offline pipeline prediction on fixtures
│       ├── test_risk.py               ⏳ Component points, band edges (29/30, 59/60), breakdown sums to score
│       ├── test_token_math.py         ⏳ floor + remainder edge cases (incl. exact multiples of ₹10,000)
│       └── test_chain_down.py         ⏳ Bridge stopped → tokenise 503, predict still 200
│
├── frontend/                                  # MODULE K (renders API data — owns NO domain logic)
│   ├── package.json                   ⏳ Updated per frontend_package_specification.md (adds framer-motion, vitest)
│   ├── vite.config.ts                 ✅
│   ├── tailwind.config.js             ✅ Tailwind 3.4
│   ├── index.html                     ✅
│   └── src/
│       ├── main.tsx                   ✅
│       ├── types/property.ts          ✅ PropertyInput / PredictionResponse — bound to schema v1.1.0
│       │                                 ⏳ extend: TokeniseResponse, PropertyRecord, RiskBreakdown
│       ├── lib/
│       │   ├── api.ts                 ⏳ Typed fetch client (base URL from VITE_API_BASE_URL); ONLY network code
│       │   └── format.ts              ⏳ ₹ formatting (lakh/crore), number display — presentation only
│       ├── components/
│       │   ├── ui/                    ✅ shadcn/ui primitives (existing scaffold)
│       │   ├── PrototypeNotice.tsx    ⏳ Mandatory on every token surface (architecture §2.7)
│       │   ├── PropertyForm.tsx       ⏳ Schema-driven fields; client validation mirrors API (API is authority)
│       │   ├── PriceCard.tsx          ⏳ ₹ lakh / ₹ INR / ₹ per sq ft + coordinate_source flag display
│       │   ├── ShapChart.tsx          ⏳ Recharts horizontal bar — signed share %, log-space label (architecture §6G)
│       │   ├── RiskGauge.tsx          ⏳ Score + band + expandable component breakdown table
│       │   ├── TokenPanel.tsx         ⏳ Supply, ₹/token, remainder, HIGH-risk acknowledgement checkbox → mint gate
│       │   └── OwnershipTable.tsx     ⏳ Balances from API (chain-verified), last-synced block shown
│       ├── pages/
│       │   ├── ValuationPage.tsx      ⏳ Form → PriceCard + ShapChart + RiskGauge + TokenPanel
│       │   ├── TokenisePage.tsx       ⏳ Register/mint/buy/transfer actions + tx results (network labelled)
│       │   ├── PropertiesPage.tsx     ⏳ Mongo-indexed list → detail with on-chain state
│       │   └── ModelPage.tsx          ⏳ model_metadata.json rendered: metrics, global SHAP, versions, SHA
│       └── hooks/
│           └── usePrediction.ts       ⏳ Request state for the valuation flow
│
├── blockchain/                                # MODULES L–M (local chain only)
│   ├── package.json                   ✅ Hardhat 2.22 / ethers v6 (see architecture §6L for @openzeppelin/contracts add)
│   ├── hardhat.config.ts              ✅ Solidity 0.8.24, optimizer 200 runs, chainId 31337, localhost network
│   ├── contracts/
│   │   └── PropertyTokenisation.sol   ⏳ L — ERC-1155: registerProperty / mintTokens / buyTokens /
│   │                                     getProperty + events (replaces the current README placeholder)
│   ├── scripts/
│   │   └── deploy.ts                  ⏳ Deploys + writes deployments/localhost.json {address, chainId, deployer}
│   ├── deployments/
│   │   └── localhost.json             ⏳ GENERATED by deploy.ts — the only source of the contract address
│   ├── bridge/                                # M — Node.js/ethers.js internal service (Flask's only chain path)
│   │   ├── package.json               ⏳ express + ethers v6 (internal service, no public exposure)
│   │   ├── src/index.ts               ⏳ POST /internal/register|mint|buy|transfer · GET /internal/health
│   │   └── src/contract.ts            ⏳ ABI/address loading from deployments file; prediction_id idempotency
│   └── test/
│       └── PropertyTokenisation.test.ts ⏳ L — register/mint/buy/transfer/ownership + negative cases
│
├── shared/                                    # Contracts between components — DATA, never code
│   ├── feature_schema.json            ✅🔒 v1.1.0 frozen (11 model features + SQUARE_FT_PER_BHK derived)
│   ├── api_contract.md                ⏳ Superseded by api_specification.md (v1) on approval
│   ├── city_centroids.json            ✅ Stage-2 artefacts (fallback reads via fitted pipeline — architecture §8)
│   └── city_grouping.json             ✅
│
├── tests/                                     # MODULE N — cross-component
│   └── e2e/
│       └── demo_flow.spec.ts          ⏳ Playwright: the exact viva flow form → valuation → SHAP → risk
│                                          → register → mint → buy → transfer → ownership (local mode)
│
├── infra/                                     # MODULE N — deployment
│   ├── render.yaml                    ⏳ Backend web service: gunicorn, env list, health-check path /health
│   └── vercel.json                    ⏳ SPA rewrites for the Vite build (frontend stays a static deploy)
│
├── docs/
│   ├── decisions.md                   ✅ D1–D16 — D8 (risk) and D9 (token denomination) close on this approval
│   ├── dataset_inspection.md/.json    ✅ Stage-1 verified dataset facts
│   └── reference/
│       └── Real_Estate_..._Review1.pptx ✅🔒 The Review-1 deck (scope source; metrics are NOT results — D1)
│
├── reports/
│   ├── eda_report.md + figures/ (12)  ✅ A
│   ├── preprocessing_report.md        ✅ B
│   ├── benchmark/                     ✅ C — benchmark_report.md, metrics.json, model_comparison.csv, 8 figures
│   └── optimization/                  ✅ D/E — optimization_report.md, final_evaluation.json, selection.json,
│                                          residual_analysis.csv, tuned_comparison.csv
│
└── scripts/
    ├── verify_stage1.sh               ✅
    ├── verify_stage2.sh               ✅
    ├── verify_preprocessing.sh        ✅
    ├── verify_stage3.sh               ✅
    └── verify_stage4.sh …             ⏳ One verification script per future stage, same pattern
```

## Notes on deliberate choices

- **`bridge/` lives inside `blockchain/`, not `backend/`** — it is chain tooling (Node/ethers/keys). The backend depends on its HTTP interface only, so the bridge can be restarted/redeployed without touching Flask.
- **No `users/` or `auth/` anywhere** — authentication is not in the PPT scope. Adding it later is additive (a new blueprint + collection), not a refactor.
- **`ml/notebooks/` stays empty by discipline** — every experiment is a reproducible script under `ml/src/`; this is what makes the results defensible in review.
- **One verification script per stage** in `scripts/` — the pattern that Stages 1–3 already proved; a stage is "done" when its script passes, not when its code merely exists.
