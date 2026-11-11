# Deployment Testing Report

Date: 2026-11-01 · Scope: production-configuration verification of the
exact artifacts that will be deployed. **No public deployment has been
performed yet** — Vercel/Render/Atlas accounts and credentials belong
to the project owner, so public URLs do not exist at the time of
writing and nothing below claims otherwise. What was tested is the
production stack itself (gunicorn + production build + production
environment), run locally in the same configuration the platforms
will use. After following DEPLOYMENT.md, re-run the checklist in §4
against the real URLs.

## 1. Production backend (gunicorn, FLASK_ENV=production)

Started exactly as Render will: `gunicorn app:app --workers 1
--timeout 180`, with a real `SECRET_KEY`, `ADMIN_API_KEY` set,
`HISTORY_BACKEND=memory` (Atlas unavailable in this environment —
see §3), CORS restricted to the frontend origin.

| Check | Result |
|---|---|
| `GET /api/health` | 200, status ok, model_loaded true |
| `POST /api/valuation/predict` (canonical property) | 200, ₹75.2L, history_saved true |
| `POST /api/risk/assess` | 200, score 7.7 LOW |
| `POST /api/token/calculate` | 200, 752 tokens for ₹75.2L |
| `GET /api/dashboard/history` after predict | total 1 (persistence path works) |
| `GET /api/models/schema` | 200, 20 features |
| CORS | `Access-Control-Allow-Origin` echoes only the configured frontend origin |
| Invalid property | 400 VALIDATION_ERROR naming the missing features |
| Chain status (no node — hosted mode) | `connected: false`, reported honestly |
| Register without admin key | **401 ADMIN_UNAUTHORIZED** |
| Register with wrong key | 401 |
| Register with correct key, no node | 503 CHAIN_UNAVAILABLE (auth passed, chain absent — correct hosted behaviour) |
| Startup with production + default SECRET_KEY | **refused** (RuntimeError; also covered by pytest) |

## 2. Production frontend (Vite build + preview server)

Built with `VITE_API_BASE_URL` set (verified present in the emitted
bundle), served by `vite preview`:

| Check | Result |
|---|---|
| `/` | 200, correct page title |
| `/valuation` (deep link) | 200 via SPA fallback (same rule as `vercel.json` rewrites) |
| Build | `tsc -b && vite build` clean |

Note: preview is a static server, not Vercel itself; the Vercel SPA
rewrite and immutable asset caching are declared in
`frontend/vercel.json` and must be confirmed on the first real deploy
(§4 checklist).

## 3. What could NOT be tested here, and why

| Item | Status |
|---|---|
| MongoDB Atlas connectivity | No Atlas account/cluster exists yet. The Mongo repository is verified by interface + degradation tests (clean 503s when the DB is down); the memory backend exercised the same code paths in §1. First-deploy checklist (§4) includes a live Atlas check. |
| Public URLs (Vercel/Render) | Not deployed — requires the owner's platform accounts. |
| Public testnet chain | Out of scope for the initial deployment; requirements documented in DEPLOYMENT.md §5. |
| In-browser visual QA | The automated browser cannot navigate to loopback addresses (see AUDIT_REPORT.md §7); manual click-through remains available. |

## 4. Post-deployment verification checklist (run against real URLs)

1. `GET https://<render-url>/api/health` → status ok, model_loaded true.
2. Frontend loads at the Vercel URL; deep link `/valuation` refreshes without 404.
3. Submit the sample property → prediction returns; History page shows the record after refresh (proves Atlas persistence).
4. Explainability and Risk pages render live API data.
5. Blockchain Explorer shows chain **disconnected / local-only** messaging (hosted mode) — never a fake connected state.
6. `POST /api/chain/register` without the admin key → 401.
7. Browser console: no CORS errors (confirms `CORS_ORIGINS` matches the Vercel domain exactly).
