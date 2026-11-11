# Frontend Package Specification

**Status:** FOR APPROVAL. Target: update the existing `frontend/package.json` (Stage-1 scaffold) to the spec below at Stage 6 entry. Runtime: **Node 24.22 / npm 10.9** (verified on this machine). The full proposed file is delivered alongside as `frontend_package.json`.

## Decisions embedded in this spec
1. **Keep TypeScript** (existing scaffold, `tsc -b && vite build`). The API contract is typed end-to-end (`src/types/property.ts` ↔ Pydantic schemas ↔ feature schema v1.1.0); dropping TS would delete a working safety net for zero functional gain. → Approval decision §11.5 in `architecture.md`.
2. **React 18.3, not 19** — matches the scaffold and Recharts 2.x compatibility; no feature in this project needs React 19.
3. **Add `framer-motion`** (your brief) for page/panel transitions only — never for data, and never animating numbers into existence before the API responds.
4. **No state-management or HTTP library beyond a typed `fetch` wrapper** (`lib/api.ts`). The app has one form flow and four pages; Redux/Zustand/Axios would be unjustified weight. Revisit only if Stage 6 finds cross-page state pain.
5. **No blockchain library in the frontend** — by architecture, the browser never talks to the chain. No `ethers`, no wallet connectors. This is a security boundary, not an omission.

## Dependencies (production)
| Package | Version | Purpose in this project |
|---|---|---|
| `react`, `react-dom` | ^18.3.1 | UI runtime |
| `recharts` | ^2.13.3 | SHAP contribution chart, risk/price visualisations (your brief) |
| `framer-motion` | ^11.11.17 | Panel/page transitions (your brief — **new**) |
| `lucide-react` | ^0.460.0 | Icons (your brief) |
| `@radix-ui/react-label`, `@radix-ui/react-slot` | ^2.1.0 / ^1.1.0 | shadcn/ui primitives already in scaffold |
| `class-variance-authority`, `clsx`, `tailwind-merge`, `tailwindcss-animate` | scaffold versions | shadcn/ui styling utilities |

## Dev dependencies
| Package | Version | Purpose |
|---|---|---|
| `vite`, `@vitejs/plugin-react` | ^5.4.11 / ^4.3.4 | Build/dev server (your brief) |
| `typescript` | ^5.6.3 | Type safety against the API contract |
| `tailwindcss`, `postcss`, `autoprefixer` | ^3.4.15 / ^8.4.49 / ^10.4.20 | Tailwind CSS (your brief) |
| `@types/react`, `@types/react-dom` | ^18.3.x | Types |
| `eslint` | ^9.15.0 | Lint (`npm run lint`) |
| `vitest`, `@testing-library/react`, `jsdom` | ^2.1.x / ^16.x / ^25.x | Component tests — **new** (Module N): formatting, HIGH-risk gate, prototype-notice presence |

## Scripts
`dev` (vite) · `build` (`tsc -b && vite build` — the Vercel build command) · `preview` · `lint` · `test` (`vitest run` — **new**)

## Environment (build-time, public by design — no secrets exist in this tier)
| Variable | Local | Hosted (Vercel) |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:5000` | Render backend URL |

## Blockchain package (for completeness — Module L/M, lives in `blockchain/`)
Existing `blockchain/package.json` stands, with one addition on approval: **`@openzeppelin/contracts ^5.0.2`** (ERC-1155). Bridge (`blockchain/bridge/package.json`, new at Stage 5): `express ^4.21`, `ethers ^6.13.4`, `dotenv ^16.4.5`; dev: `typescript ^5.6.3`, `ts-node ^10.9.2`. Hardhat stays **2.22.x** with `@nomicfoundation/hardhat-toolbox ^5.0.0` and `ethers ^6.13.4` — the exact, already-scaffolded combination; Hardhat 3 is a different toolchain and is out of scope.
