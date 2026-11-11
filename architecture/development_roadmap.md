# Development Roadmap

**Status:** FOR APPROVAL. Stages 1–3b are complete and verified (evidence linked); Stages 3c–7 are planned with entry/exit criteria. **No stage starts before the previous stage's exit criteria pass, and no stage starts at all until this architecture is approved.**

Ordering logic: SHAP (3c) precedes the API (4) because the API serves SHAP; the API precedes contracts (5) because tokenisation consumes stored predictions; contracts precede the full frontend (6) because the token UI needs real endpoints; deployment (7) is last because a local Hardhat chain constrains what "deployed" can honestly mean (architecture §9.3).

```
Stage 1 ✅ ─► Stage 2 ✅ ─► EDA ✅ ─► Preproc v2 ✅ ─► Stage 3 ✅ ─► Stage 3b ✅
                                                                    │
                                            ┌───────────────────────▼────────────────────────┐
                                            │  APPROVAL GATE — this document set             │
                                            └───────────────────────┬────────────────────────┘
                                                                    ▼
Stage 3c (SHAP) ─► Stage 4 (Flask + Risk + Token) ─► Stage 5 (Contracts + Bridge)
        ─► Stage 6 (React dashboard) ─► Stage 7 (Mongo + Deployment + E2E + Docs)
```

---

## Completed stages (verified — do not redo)

| Stage | Scope (modules) | Evidence |
|---|---|---|
| 1 — Inspection & skeleton | Architecture v1, repo layout, schema draft | `docs/dataset_inspection.md`, `scripts/verify_stage1.sh` ✅ |
| 2 — Data preparation | B: cleaning R1–R6, schema v1.0.0 frozen, 29,451 → 28,622 | `data/processed/data_quality_log.json`, `verify_stage2.sh` ✅ |
| EDA (inserted on evidence) | A: full EDA, proposals P1–P10 | `reports/eda_report.md`, 12 figures, `eda_stats.json` ✅ |
| Preprocessing v2 | B: split-before-fit, train-fitted transformers, schema **v1.1.0** | `reports/preprocessing_report.md`, 5 pytest tests, byte-identical re-run ✅ |
| 3 — Benchmark | C: 11 candidates × raw/log, CV + validation, test-once | `reports/benchmark/benchmark_report.md` ✅ |
| 3b — Optimisation | D+E: tuning, extended features, **final CatBoost → `ml/model.pkl`**, test R² **0.8253** / MAE ₹23.08 L / RMSE ₹63.40 L | `reports/optimization/optimization_report.md`, `final_evaluation.json` ✅ |

---

## Stage 3c — SHAP explainability (Module G) · *next, on approval*
**Owner:** Anand (XAI) with Nitesh (API contract for explanation payload).
**Entry:** architecture approved; `ml/model.pkl` frozen (SHA `921674e1…fd4e6`).
**Work:**
1. Implement `ml/src/explain.py`: `shap.TreeExplainer` over the pipeline's inner CatBoost; preprocessed-space SHAP for a fixed validation sample (seed 42).
2. Aggregation layer: sum one-hot SHAP back to source features; unit test — aggregated contributions + base value == model output in log space (tolerance 1e-6 relative).
3. Generate `ml/artifacts/shap_summary.json` (global mean-|SHAP| ranking) and `ml/artifacts/model_metadata.json` (from `final_evaluation.json` — copied programmatically, never retyped; includes model SHA-256 and library versions).
4. Decide and document the log-space presentation rule (architecture §6G) in `docs/decisions.md`.
**Exit criteria:** `ml/tests/test_explain.py` passes; both artefacts exist and validate against a JSON schema; a sample of 20 test rows shows aggregation identity holding; **no lakh-additive claim appears in any artefact or doc**.
**Run:** `.venv/bin/python -m ml.src.explain && .venv/bin/python -m pytest ml/tests/`

## Stage 4 — Flask API: prediction, SHAP, risk, token quote (Modules F, H, I, J)
**Owner:** Nitesh. **Depends on:** 3c (artefacts), approval decisions §11.1–11.2 (risk).
**Work:**
1. Backend environment build + lock (`backend/requirements.lock.txt` from the pinned deliverable `requirements.txt`); app factory; model singleton with SHA verification.
2. `risk_reference.json` generator (train-fitted city ₹/sq ft medians, SQUARE_FT_PER_BHK P5/P95, locality frequencies) + `risk_service.py` implementing **Risk Score v0.1** exactly as approved; calibration report — band distribution over the test partition — written to `reports/risk_calibration.md` and reviewed before proceeding.
3. Endpoints per `api_specification.md` v1: `/health`, `/api/v1/model-info`, `POST /api/v1/predict` (price + SHAP + risk + token quote), `GET /api/v1/predictions[/{id}]`; Pydantic validation; structured errors; Mongo `predictions` audit write (Mongo may be a local instance in this stage; Atlas wiring is Stage 7).
4. `token_service.py`: floor math + remainder + HIGH-risk acknowledgement gate (server-side enforcement, not UI-only).
**Exit criteria:** backend test suite passes (validation matrix, determinism vs offline pipeline on fixtures, risk band edges, token math, SHAP-null fallback); a live `POST /predict` for a fixture property returns values identical to the offline pipeline; `scripts/verify_stage4.sh` passes.
**Run:** `cd backend && flask --app run run` · `pytest backend/tests/`

## Stage 5 — Smart contracts & bridge (Modules L, M)
**Owner:** Nitesh (contracts/bridge), Deeraj (test support). **Depends on:** Stage 4 (tokenise endpoints stubbed against a bridge interface).
**Work:**
1. `PropertyTokenisation.sol` (ERC-1155 per approval §11.3): `registerProperty / mintTokens / buyTokens / getProperty`, events, guards (single mint, supply cap, availability, exact demo-price payment).
2. Hardhat test suite: happy path register→mint→buy→transfer→ownership + negative cases (double mint, over-supply buy, wrong payment, non-owner mint attempt).
3. `deploy.ts` → `deployments/localhost.json`; bridge service (`blockchain/bridge/`) with `prediction_id` idempotency and `/internal/health`.
4. Wire Flask `chain_client.py` → bridge; tokenise/buy/transfer endpoints live; chain-down behaviour verified (503 + prediction unaffected).
**Exit criteria:** `npx hardhat test` all green; one full on-chain flow executed against a fresh local node with tx hashes recorded in `reports/blockchain_demo.md` (labelled local, chainId 31337); double-submit of the same `prediction_id` provably creates exactly one on-chain property.
**Run:** `cd blockchain && npx hardhat node` · `npx hardhat test` · `npx hardhat run scripts/deploy.ts --network localhost`

## Stage 6 — React dashboard (Module K)
**Owner:** Deeraj. **Depends on:** Stage 4 API frozen; Stage 5 for the token pages' live data (pages may be built against Stage 4 first).
**Work:**
1. Apply `frontend_package_specification.md` (add `framer-motion`, `vitest`); typed API client (`lib/api.ts`) as the only network code.
2. Valuation page: schema-driven form → PriceCard, ShapChart (share %, log-space labelling), RiskGauge + breakdown, TokenPanel (supply/remainder/HIGH-ack gate), PrototypeNotice.
3. Tokenise + Properties + Model pages against real endpoints; ownership view shows chain state + last-synced block.
4. Vitest component tests (formatting, gate behaviour, notice presence) + responsive/accessibility pass.
**Exit criteria:** end-to-end manual flow in local mode matches the API responses exactly (spot-checked against `curl`); no price/risk/token constant exists anywhere in `frontend/src` (grep-verified); build passes (`npm run build`).
**Run:** `cd frontend && npm install && npm run dev`

## Stage 7 — Persistence hardening, deployment, E2E, documentation (Module N)
**Owner:** All (Nitesh: backend/chain, Deeraj: frontend/E2E, Jaswika: docs, Anand: integration).
**Depends on:** Stages 4–6 exit criteria all green.
**Work:**
1. MongoDB Atlas provisioning; `MONGO_URI` via env; event indexer syncing `properties`/`token_events` from contract events with re-sync on divergence.
2. Deployment per architecture §9: Vercel (frontend), Render (backend, `infra/render.yaml`), **Mode-1 local demo as the committed configuration**; Mode-2 hosted showcase verified for valuation/SHAP/risk/history with tokenise correctly returning 503 + UI explanation.
3. Playwright E2E (`tests/e2e/demo_flow.spec.ts`) running the exact viva flow in local mode.
4. Documentation close-out: README run-book (fresh-clone → working demo), viva demo script with the §6L demo-price caveat and §9.3 mode explanation, correction notes for the next review deck (R2/R4 slide wording; PPT reference table replaced by measured results), final results report generated from artefacts only.
**Exit criteria:** fresh-clone run-book test passes by a team member who did not write it; E2E green; every number in the final report traces to an artefact file; `scripts/verify_stage7.sh` passes.

---

## Milestone summary

| Milestone | After stage | Demonstrable capability |
|---|---|---|
| M1 ✅ | 3b | Trained, evaluated, serialised valuation model with honest metrics |
| M2 | 3c | Per-property + global SHAP explanations as artefacts |
| M3 | 4 | Live API: valuation + explanation + risk + token quote for any valid property |
| M4 | 5 | Full on-chain register → mint → buy → transfer on the local chain via the API |
| M5 | 6 | Complete dashboard demo (the Review-2+ demo configuration) |
| M6 | 7 | Hosted showcase + reproducible run-book + E2E-verified demo |

## Standing rules for every remaining stage
- PPT metrics/demo values are never used as results (D1). R² 0.95 is reported only as an investigated, unattained target, with its evidence-based reasons.
- Test partition discipline: it has been scored once for the final model; any future model change re-opens the full benchmark protocol, not a casual re-score.
- Every stage ends with: tests green → verification script → decision-log update → user sign-off before the next stage starts.
