# API Integration Specification — v1

**Status:** FOR APPROVAL. On approval this supersedes the draft `shared/api_contract.md`.
**Base URL (local):** `http://127.0.0.1:5000` · **(hosted):** Render service URL. **Versioning:** all business endpoints under `/api/v1`. **Format:** JSON only. **Auth:** none (not in PPT scope). **CORS:** only the configured frontend origin.

**Global rules**
1. The API never trains, never invents values, and never accepts a client-supplied price, risk score or token supply for tokenisation — those are always re-read server-side from the stored prediction.
2. Every response carries `request_id` (UUID) and, where relevant, `model_version`, `schema_version` (`1.1.0`) and `risk_method_version` (`0.1` once approved).
3. Token-bearing responses always include the `notice` field verbatim: `"Academic prototype — tokens are not legal proof of property ownership."` and a `network` object for chain data.
4. Errors use one envelope everywhere:
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "SQUARE_FT must be between 100 and 20000", "field": "SQUARE_FT" }, "request_id": "…" }
```
Codes: `VALIDATION_ERROR` (422), `NOT_FOUND` (404), `CHAIN_UNAVAILABLE` (503), `CHAIN_REJECTED` (502), `ALREADY_TOKENISED` (409), `RISK_ACK_REQUIRED` (422), `MODEL_UNAVAILABLE` (503), `INTERNAL` (500).

---

## 1. `GET /health`
Liveness + readiness. Also used as Render health-check and demo wake-up.
```json
200 { "status": "ok", "model_loaded": true, "model_sha256": "921674e1…",
      "mongo_connected": true, "bridge_connected": false, "chain_mode": "local" }
```
`model_loaded: false` ⇒ the service is up but must not serve predictions (`/predict` → 503 `MODEL_UNAVAILABLE`).

## 2. `GET /api/v1/model-info`
Served **only** from `ml/artifacts/model_metadata.json`. If the artefact is missing, returns 503 `MODEL_UNAVAILABLE` — never placeholder metrics.
```json
200 {
  "model_name": "CatBoostRegressor", "model_version": "stage3b-final",
  "schema_version": "1.1.0", "preprocessing_version": "2.0.0",
  "target_transform": "log1p", "fitted_on": "train+validation (24,328 rows)",
  "features": ["POSTED_BY","UNDER_CONSTRUCTION","RERA","BHK_NO.","BHK_OR_RK","SQUARE_FT",
               "RESALE","CITY","LOCALITY","LATITUDE","LONGITUDE","SQUARE_FT_PER_BHK"],
  "test_metrics":  { "r2": 0.8253, "mae_lacs": 23.08, "rmse_lacs": 63.40, "mape_pct": 22.31, "rmsle": 0.30, "n": 4294 },
  "grouped_generalisation": { "r2": 0.7417, "note": "Locality-grouped split — unseen-locality estimate" },
  "global_shap": [ { "feature": "SQUARE_FT", "mean_abs_effect_log": 0.0 } ],
  "r_squared_target_note": "R² ≥ 0.95 was investigated and not attained; see optimisation report."
}
```
*(Metric values above are the measured Stage-3b values from `final_evaluation.json`, shown here rounded; the endpoint serves the artefact's full-precision values. `global_shap` values are produced in Stage 3c — until then the field is `null`, not zero-filled.)*

## 3. `POST /api/v1/predict` — valuation + SHAP + risk + token quote
**Request** — exactly the schema-v1.1.0 API input (ADDRESS is submitted; CITY/LOCALITY are derived by the pipeline, never sent):
```json
{
  "POSTED_BY": "Owner",            // enum: Owner | Dealer | Builder
  "UNDER_CONSTRUCTION": 0,         // 0 | 1
  "RERA": 1,                       // 0 | 1
  "BHK_NO.": 3,                    // int 1–20
  "BHK_OR_RK": "BHK",              // enum: BHK | RK
  "SQUARE_FT": 1500,               // number 100–20000
  "RESALE": 1,                     // 0 | 1
  "ADDRESS": "Whitefield,Bangalore", // string, "<locality>,<city>" expected; free localities accepted
  "LATITUDE": 12.9699,             // OPTIONAL — see coordinate rule below
  "LONGITUDE": 77.5979             // OPTIONAL
}
```
Coordinate rule (D11): both omitted ⇒ backend uses the CITY centroid **from the fitted pipeline** and sets `coordinate_source: "city_centroid"`. Exactly one supplied ⇒ 422. Supplied pair outside India-plausible bounds (lat 6–38, lon 67–98, *after* the API's documented lat/lon field meanings — the API uses correct meanings; the raw dataset's swap is a training-data defect already repaired inside the pipeline) ⇒ 422.

**Response** (values are runtime outputs of the real model — the shape below is the contract; no example price is part of it):
```json
200 {
  "prediction_id": "pred_…",               // persisted in Mongo; required for tokenisation
  "predicted_price_lacs": 0.00,
  "predicted_price_inr": 0,
  "price_per_sqft_inr": 0,
  "coordinate_source": "provided | city_centroid",
  "model_version": "stage3b-final", "schema_version": "1.1.0",
  "shap": {
    "space": "log1p_price_lacs",
    "base_value_log": 0.0,
    "contributions": [
      { "feature": "SQUARE_FT", "display_value": 1500, "effect_log": 0.0, "share_pct": 0.0 }
      // sorted by |share_pct| desc; aggregated to source features (≤15 rows);
      // sum(effect_log) + base_value_log == log1p(predicted_price_lacs)
    ]
  },
  "risk": {
    "score": 0, "band": "LOW | MEDIUM | HIGH", "method_version": "0.1",
    "breakdown": [
      { "component": "regulatory_rera", "points": 0, "max_points": 20, "signal": "RERA=1" }
      // one row per approved component; sum(points) == score
    ],
    "notice": "Prototype risk methodology — not validated investment advice."
  },
  "tokenisation": {
    "inr_per_token": 10000,
    "token_supply": 0,                      // floor(predicted_price_inr / 10000)
    "remainder_inr": 0,
    "requires_risk_acknowledgement": false, // true iff band == HIGH
    "notice": "Academic prototype — tokens are not legal proof of property ownership."
  },
  "request_id": "…"
}
```
**Validation:** unknown enum, out-of-range number, missing field, wrong type ⇒ 422 with `field`. A *novel* locality/city string is **not** an error (the fitted pipeline maps unseen/rare values safely). SHAP failure ⇒ 200 with `"shap": null, "explanation_unavailable": true` (prediction is never blocked by explanation).

## 4. `GET /api/v1/predictions` · `GET /api/v1/predictions/{prediction_id}`
History list (paginated, newest first, from Mongo audit log) and single-prediction retrieval (same body as §3 response). 404 `NOT_FOUND` for unknown ids.

## 5. `POST /api/v1/tokenise` — register + mint on the local chain
```json
Request  { "prediction_id": "pred_…", "owner_address": "0x…",
           "risk_acknowledged": true }        // required true iff stored risk band is HIGH
Response 201 {
  "property_id": 1, "prediction_id": "pred_…",
  "register_tx_hash": "0x…", "mint_tx_hash": "0x…",
  "token_supply": 0, "owner_address": "0x…",
  "network": { "name": "hardhat-local", "chain_id": 31337,
               "contract_address": "0x…", "mode": "local" },
  "notice": "Academic prototype — tokens are not legal proof of property ownership."
}
```
Server re-reads price/supply/risk from the stored prediction (client values ignored). Same `prediction_id` twice ⇒ 409 `ALREADY_TOKENISED` (bridge idempotency is the second line of defence). Bridge/chain down ⇒ 503 `CHAIN_UNAVAILABLE`. In hosted mode without a configured RPC ⇒ 503 with `mode: "hosted_no_chain"` (architecture §9.3).

## 6. `POST /api/v1/tokenise/buy`
```json
Request  { "property_id": 1, "buyer_address": "0x…", "token_amount": 10 }
Response 200 { "tx_hash": "0x…", "property_id": 1, "buyer_address": "0x…",
               "token_amount": 10, "price_per_token_wei": "1000000000000000",
               "total_paid_wei": "…", "network": { … }, "notice": "…" }
```
Guards enforced on-chain and pre-checked by the API: property minted, amount ≤ available supply, payment == `amount × DEMO_TOKEN_PRICE_WEI` (bridge pays from the buyer's local test account — local mode only).

## 7. `POST /api/v1/tokenise/transfer`
```json
Request  { "property_id": 1, "from_address": "0x…", "to_address": "0x…", "token_amount": 5 }
Response 200 { "tx_hash": "0x…", "property_id": 1, "from_address": "0x…",
               "to_address": "0x…", "token_amount": 5, "network": { … }, "notice": "…" }
```
Insufficient balance / unknown property ⇒ 422/404 with the contract's revert reason surfaced as `CHAIN_REJECTED` (502) where applicable.

## 8. `GET /api/v1/properties` · `GET /api/v1/properties/{property_id}` · `GET /api/v1/properties/{property_id}/ownership` · `GET /api/v1/owners/{address}/portfolio`
List/detail read the Mongo index, then **verify against the chain** when the bridge is reachable; every response states its source:
```json
{ "property_id": 1, "predicted_price_inr": 0, "risk_band": "LOW", "token_supply": 0,
  "total_minted": 0, "owner_address": "0x…",
  "state_source": "chain | mongo_cache", "last_synced_block": 0,
  "ownership": [ { "address": "0x…", "balance": 0 } ],
  "network": { … }, "notice": "…" }
```

## 9. Bridge internal API (Flask → bridge only; never exposed to the frontend)
| Endpoint | Body → Result |
|---|---|
| `GET /internal/health` | → `{ rpc_connected, chain_id, contract_address, deployer }` |
| `POST /internal/register` | `{ prediction_id, owner_address, predicted_price_inr, risk_score, risk_band, token_supply, metadata_hash }` → `{ property_id, tx_hash, block_number }` (idempotent on `prediction_id`) |
| `POST /internal/mint` | `{ property_id }` → `{ tx_hash, block_number }` |
| `POST /internal/buy` | `{ property_id, buyer_address, token_amount }` → `{ tx_hash, block_number, total_paid_wei }` |
| `POST /internal/transfer` | `{ property_id, from_address, to_address, token_amount }` → `{ tx_hash, block_number }` |
| `GET /internal/property/{id}` | → on-chain record + balances (chain-truth reads) |

## 10. Frontend ↔ API integration rules
- The frontend calls **only** endpoints §1–§8, via `lib/api.ts`; it never calls the bridge or the chain.
- It renders `notice`, `network` and `state_source` wherever token data appears; it disables Mint until `risk_acknowledged` is checked when `requires_risk_acknowledgement` is true (the API enforces this server-side regardless).
- It treats 503 `CHAIN_UNAVAILABLE` as a presentable state ("local blockchain not running — valuation still works"), not as a crash.
- All enums/ranges in forms come from the schema-derived types (`frontend/src/types/property.ts`); the API remains the validation authority.
