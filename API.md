# API Documentation — Real Estate Valuation Backend

Base URL (local): `http://127.0.0.1:5000` · Hosted: your Render URL.

## Conventions

Every response uses one envelope:

```json
// success
{"success": true, "request_id": "…", "timestamp": "…Z", "data": { … }}
// error
{"success": false, "request_id": "…", "timestamp": "…Z",
 "error": {"code": "VALIDATION_ERROR", "message": "…"}}
```

Error codes: `INVALID_JSON` (400), `VALIDATION_ERROR` (400),
`NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405),
`ADMIN_UNAUTHORIZED` (401), `DUPLICATE_REGISTRATION` /
`ALREADY_MINTED` (409), `MODEL_UNAVAILABLE` (503),
`DATABASE_UNAVAILABLE` (503), `CHAIN_UNAVAILABLE` (503),
`CHAIN_TX_REVERTED` / `CHAIN_STATE_MISMATCH` (502),
`INTERNAL_ERROR` (500, details never leaked).

## Property input

Valuation endpoints accept `{"property": { … }}` with either the 20
model-ready features defined by `GET /api/models/schema`, or the raw
listing fields, from which the backend derives the engineered features
server-side (`derived_features` in the response lists what it added).
Validation is strict: missing features, non-positive `SQUARE_FT`,
non-integer or out-of-range `BHK_NO.`, coordinates outside India, and
invalid binary flags are rejected with the offending field named.

## Endpoints

### System
- `GET /api/health` — status (`ok`/`degraded`), model_loaded,
  database_connected, model identity. Render health check target.

### Valuation
- `POST /api/valuation/predict` — `{predicted_price_lacs,
  predicted_price_inr, model_id, model_name, uncertainty
  {lower_lacs, upper_lacs, method}, history_saved, derived_features}`.
- `POST /api/valuation/explain` — prediction + SHAP: base value,
  baseline price, all-20 ranked contributions (log-space SHAP and
  multiplicative `price_factor`), top positive/negative drivers,
  additivity check, human-readable narrative.

### Risk
- `POST /api/risk/assess` — `{risk_score (0–100), risk_category
  (LOW|MEDIUM|HIGH), domains, factors[7], warnings, recommended_actions,
  explanation, price_source}`. If `predicted_price_lacs` is omitted it
  is computed by the model first and the source is reported.

### Tokenisation (calculation)
- `POST /api/token/calculate` — accepts `valuation_lacs` or a
  `property`. Returns `token_supply = floor(valuation_inr / 10000)`,
  `rounding.remainder_inr` (left untokenised), denomination, and the
  fractional-ownership breakdown. Calculation only — no chain writes.

### Models
- `GET /api/models/metrics` — served model identity + measured
  validation/CV/test metrics.
- `GET /api/models/compare` — all measured candidate evaluations with
  the served model flagged `selected`.
- `GET /api/models/schema` — the 20-feature schema with fitted
  category levels (the frontend builds its form from this).
- `GET /api/models/shap-summary` — global SHAP ranking (documented
  2,000-row sample, seed 42).

### Dashboard
- `GET /api/dashboard/summary` — totals, average value, model summary
  from stored history.
- `GET /api/dashboard/history?page=&page_size=` — paginated valuation
  history (newest first).

### Blockchain bridge (local/testnet chain required)
- `GET /api/chain/status` — `{connected, chain_id, contract_address,
  deployment_block}`; `connected:false` when no node is reachable
  (the normal hosted-showcase state).
- `POST /api/chain/register` — **admin** (`X-Admin-Key` header when
  `ADMIN_API_KEY` is configured). Computes valuation + risk
  server-side, registers on-chain, verifies the on-chain supply
  against the backend calculation, stores the record. Duplicate
  property → 409.
- `POST /api/chain/mint` — **admin**. `{chain_property_id}`; mints the
  recorded supply to contract inventory and verifies it on-chain.
  Re-mint → 409.
- `GET /api/chain/properties` / `GET /api/chain/properties/<id>` —
  tokenisation records enriched with live on-chain availability.
