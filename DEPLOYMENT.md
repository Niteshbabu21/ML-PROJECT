# Deployment Guide

Two supported modes, by design:

- **Mode 1 — Local demo (primary, for the viva):** everything on one
  machine, including the Hardhat chain. Full register → mint → buy →
  transfer works. See README.md Quick start.
- **Mode 2 — Hosted showcase:** frontend on Vercel, backend on Render,
  data in MongoDB Atlas. Valuation, SHAP, risk, token *calculation*,
  models and history are fully live. **Blockchain writes are disabled**
  because a Hardhat local node is not publicly reachable: the chain
  endpoints report `connected: false` / 503 honestly, and the Explorer
  labels the chain as local-only. §5 describes what a public testnet
  deployment would additionally require.

> This guide prepares and verifies everything up to the platform
> dashboards. Creating the Vercel/Render/Atlas accounts and clicking
> "Deploy" is done by the project owner; no public URL exists until
> then (see DEPLOYMENT_TESTING.md for what has been verified).

## 1. MongoDB Atlas (database first — the backend needs its URI)

1. Create a free cluster at cloud.mongodb.com.
2. **Database Access:** create a user with a strong generated password
   and `readWrite` on this application's database only.
3. **Network Access:** allow the Render egress range — for a student
   deployment the pragmatic option is `0.0.0.0/0` *combined with* the
   strong unique password (document this trade-off; restrict it if
   your institution requires).
4. Connection string (SRV form) goes into Render as `MONGO_URI`:
   `mongodb+srv://<user>:<password>@<cluster>/<db>?retryWrites=true&w=majority`
5. Collections are created automatically on first write:
   `valuation_history` (prediction records) and `tokenisations`
   (chain registration/mint records). Suggested indexes:
   `valuation_history: {timestamp: -1}`, `tokenisations:
   {property_ref: 1} (unique)`, `{chain_property_id: 1}`.
6. Never commit the URI or password anywhere; Render/Vercel env vars
   only. (Verified by scan: this repo contains no credentials.)

## 2. Backend on Render

Option A (blueprint): push this repo, then Render → New → Blueprint →
select the repo; `render.yaml` at the repo root of `files/` defines
the service (rootDir `backend`, gunicorn start command, health check
`/api/health`).

Option B (manual): New Web Service → Python → root directory
`backend` → build `pip install -r requirements.txt` → start
`gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 180`.

Environment variables to set in the Render dashboard:

| Variable | Value |
|---|---|
| `FLASK_ENV` | `production` (startup refuses the dev SECRET_KEY in this mode) |
| `SECRET_KEY` | long random (Render can generate it; the blueprint does) |
| `MONGO_URI` | from §1 |
| `HISTORY_BACKEND` | `mongo` |
| `CORS_ORIGINS` | your exact Vercel URL, e.g. `https://<app>.vercel.app` (comma-separate several; no wildcard in production) |
| `ADMIN_API_KEY` | long random — required to call chain register/mint |
| `CHAIN_RPC_URL` | leave as local default for Mode 2 (chain reports unavailable); see §5 for testnet |

Operational notes: the model artifact ships inside the repo
(`backend/ml/model.pkl`, backend total ≈ 4.3 MB) and loads once at
worker startup (~10 s); keep **one worker** on memory-constrained
plans. First request after a free-tier spin-down is slow — that is
platform behaviour, not an app error. Logs: structured request logs
(method, path, status, request id) go to stdout → Render log stream.

## 3. Frontend on Vercel

1. Import the repo in Vercel; set the project root directory to
   `frontend/`. `frontend/vercel.json` already declares the Vite
   build, the SPA rewrite (all non-asset paths → `index.html`) and
   immutable caching for `/assets/*`.
2. Environment variable (Production): `VITE_API_BASE_URL` =
   `https://<your-render-service>.onrender.com` (no trailing slash).
   Vite bakes env vars at **build time** — set it *before* the first
   build, and redeploy after any change.
3. Deploy, then set the resulting URL as `CORS_ORIGINS` on Render and
   redeploy the backend.

## 4. Verify the deployment

Run the checklist in DEPLOYMENT_TESTING.md §4 against the real URLs
(health, prediction → history persistence, explain/risk pages, chain
disconnected honesty, admin 401, no CORS errors). Do not present the
deployment as verified until every line passes on the public URLs.

## 5. Blockchain: from local Hardhat to a public testnet

The initial deployment keeps the local Hardhat network — a local node
is reachable only from the machine running it, and **must never be
assumed publicly accessible**. To run the tokenisation layer on a
public Ethereum-compatible testnet (e.g. Sepolia) you additionally
need:

1. **An RPC endpoint** — a provider account (Infura/Alchemy/QuickNode)
   or a self-hosted node; set `CHAIN_RPC_URL` to its HTTPS endpoint on
   Render. Rate limits of free tiers apply to the bridge.
2. **A funded deployer/admin wallet** — test ETH from a Sepolia
   faucet; the private key goes ONLY into Render's `CHAIN_PRIVATE_KEY`
   env var (never into the repo, never into the frontend). Use a
   dedicated test wallet holding no real assets.
3. **Contract deployment to the testnet** —
   `npx hardhat run scripts/deploy.js --network sepolia` (add the
   network + key to `hardhat.config.js` via env vars), producing a new
   `deployments/sepolia.json`; point `CHAIN_DEPLOYMENT_FILE` at it.
4. **Frontend chain configuration** — MetaMask users must add/switch
   to Sepolia (chain id 11155111); set `VITE_CONTRACT_ADDRESS` to the
   testnet deployment and rebuild the frontend.
5. **Economics caveat** — the demo token price (0.001 test-ETH/token)
   and gas costs are testnet-only artefacts; re-price deliberately
   before any non-test use. Contract verification on Etherscan is
   recommended for reviewability (`hardhat-verify` + an Etherscan API
   key as an env var).
6. **Security posture** — role-based access (REGISTRAR/MINTER) already
   restricts writes on-chain; the backend additionally requires
   `ADMIN_API_KEY` for register/mint. For anything beyond a testnet
   demo, a contract audit and a multisig admin are prerequisites —
   and none of this changes the academic-prototype status: the tokens
   do not confer legal ownership of property.

## 6. Security summary (state after this deployment pass)

- No hardcoded credentials anywhere in source (scan-verified);
  `.gitignore` excludes `.env*`, keys and build outputs.
- All secrets via environment variables; production startup refuses
  the development `SECRET_KEY` and warns if `ADMIN_API_KEY` is unset.
- Administrative chain operations require the `X-Admin-Key` header
  (constant-time comparison) whenever the key is configured.
- Contract reverts surface as honest 409/502 API errors, never fake
  successes or raw 500s.
- API input validation is the model's own strict validator — the same
  code path in dev, tests and production.
- CORS is an explicit origin allow-list, not a wildcard, in production.
