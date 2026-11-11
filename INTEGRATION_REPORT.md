# Integration Report — AI Real Estate Valuation & Risk-Aware Tokenisation

Date: 2026-11-01 · Stack run locally end-to-end: Hardhat node (chain
31337) + Flask backend + React frontend build.

## Module status

| Module | Status | Evidence |
|---|---|---|
| ML model + preprocessing (packaged E01 XGBoost) | ✅ Integrated, unchanged | Loaded once by Flask at startup; test R² 0.7423 served via `/api/models/metrics` |
| Prediction function (`predict_property`) | ✅ | `POST /api/valuation/predict` → ₹75.2L for the sample Bengaluru property |
| SHAP explainability | ✅ | `POST /api/valuation/explain` → 20 contributions, additivity verified |
| Risk engine (methodology 1.0.0-prototype) | ✅ | `POST /api/risk/assess` → 7.7 LOW for the sample property |
| Token calculation (₹10,000 denomination) | ✅ | 752 tokens for ₹75,20,000, remainder ₹0 — matches the on-chain computation exactly |
| Flask API (consistent envelopes) | ✅ | 14 endpoints (9 original + 5 chain); pytest **25/25** |
| MongoDB configuration | ⚠️ Configured, degraded in this environment | Repository pattern (Mongo + in-memory) for both valuation history and tokenisation records; no MongoDB server exists in this VM, so the live run used the in-memory backend with honest `record_saved` reporting. Mongo paths are interface-tested (incl. outage fixtures) but not verified against a live server |
| Solidity contract (PropertyToken, ERC-1155) | ✅ | Hardhat tests **16/16** |
| Hardhat deployment | ✅ | `deployments/localhost.json`, contract `0x5FbDB2315678afecb367f032d93F642f64180aa3` |
| Ethers.js integration | ✅ | Frontend wallet layer (buy/transfer via injected wallet, receipt-confirmed) + Hardhat scripts; Flask bridge uses web3.py per `blockchain/INTEGRATION.md` |
| React frontend | ✅ | `npm run build` clean; Tokenisation page gained register/mint; Explorer reads live chain data via the bridge and trades via wallet |

## End-to-end workflow verification (live run, 2026-11-01)

Property: Koramangala, Bangalore sample listing (the backend test fixture).

1. **Input** — React form (20 model features, schema-driven selects) →
   Flask validation against the packaged feature schema. ✅
2. **Valuation** — `POST /api/valuation/predict` → **₹75.2 lakh**
   (model `xgboost-e01`), saved to history. ✅
3. **SHAP** — `POST /api/valuation/explain` → price ₹75.2L, 20
   contributions, additivity verified. ✅
4. **Risk** — risk engine → **7.7 / LOW** (recorded on-chain in step 6). ✅
5. **Token calculation** — `POST /api/token/calculate` → **752 tokens**,
   valuation ₹75,20,000, remainder ₹0. ✅
6. **Blockchain registration** — `POST /api/chain/register` → chain
   property **#1**, register tx
   `0x8264cff0da1f1ca949e9854527ce9c68e509fb107d356ff08b61e86170d63dad`
   (block 2, confirmed before responding), on-chain supply **752** and
   residual **₹0** — verified equal to step 5. Property reference
   `prop-7e443ebd583c625a3b6fc519ecb7552f` (deterministic hash of the
   feature set). ✅
7. **Minting** — `POST /api/chain/mint` → tx
   `0xdd9c8ea6c3c6880e8dba9e7cbcf62b442225e04182e68a1828d39cd5621a9786`;
   contract inventory verified on-chain = 752 before success was
   reported. ✅
8. **Purchase & transfer** — against the Flask-registered property:
   buy 25 (tx `0xe5814f40…`), transfer 10 (tx `0x30f88a5a…`); final
   balances buyer 15 / friend 10 / available 727, and the Flask API's
   own property view agreed (727 of 752). Recorded in
   `blockchain/deployments/integration_verification.json`. ✅
9. **Frontend results** — valuation, SHAP, risk, supply, registration
   status and transaction hashes are all rendered from API/chain
   responses (Tokenisation + Blockchain Explorer pages). ✅ (Build
   verified; in-browser click-through not performed in this
   environment.)

## Integration issues found and fixed during this stage

1. **Duplicate-registration key flaw** — the first bridge design keyed
   duplicate prevention on the valuation *request id*, which changes on
   every call and would never have caught a duplicate. Fixed: the
   on-chain `propertyRef` is now a deterministic hash of the property's
   feature set; re-registering the same property returns
   **409 DUPLICATE_REGISTRATION** (verified live), with the contract's
   own guard as a second layer. Re-minting returns **409 ALREADY_MINTED**.
2. **Risk-result key mismatch** — the bridge consumed the risk
   *service* result (`overall_score`/`category`) using the *route's*
   mapped key names (`risk_score`/`risk_category`) → 500. Fixed and
   covered by the live run.
3. **Transaction hash format** — web3's `HexBytes.hex()` drops the
   `0x` prefix; hashes are now normalised before storage/return.

## Guarantees implemented

- Success is shown only after receipt confirmation (`status == 1`);
  reverts → 502 `CHAIN_TX_FAILED`, timeouts → 504 with the hash,
  unreachable chain → 503 `CHAIN_UNAVAILABLE`. Nothing is simulated.
- IDs are consistent: valuation request id ↔ tokenisation record
  (`valuation_request_id`) ↔ deterministic `property_ref` ↔ on-chain
  token id (`chain_property_id`).
- Secrets: the bridge key comes only from `CHAIN_PRIVATE_KEY` env
  (unset locally → the Hardhat node's unlocked test account); nothing
  secret is in source.
- Disconnected wallets surface an explicit state in the Explorer; the
  UI never fabricates balances or transactions.

## Remaining known limitations

- No live MongoDB in this environment (see module table) — run with a
  real MongoDB/Atlas URI for persistent history and tokenisation
  records; no code change needed.
- The chain is a local Hardhat network; per the architecture, hosted
  deployment serves valuation/SHAP/risk live and reports chain
  operations as 503 by design.
- Tokens are an academic prototype and do not legally represent
  ownership of physical property.
