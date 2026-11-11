# Flask ↔ PropertyToken Integration Interface

How the Flask backend interacts with the deployed `PropertyToken`
contract. The blockchain module is deliberately decoupled: Flask never
embeds Solidity logic — it calls the contract through this interface
(web3.py in Python, or an ethers.js bridge service) using the exported
ABI and deployment metadata.

> Academic prototype on a local Hardhat network (chain 31337). Tokens
> issued by this contract do **not** legally represent ownership of
> physical property.

## Artefacts Flask consumes

| Artefact | Path | Contents |
|---|---|---|
| Deployment metadata | `deployments/localhost.json` | contract address, chain id, deployer, deploy tx hash, demo price, token denomination |
| ABI | `abi/PropertyToken.json` | full contract ABI (exported by the deploy script) |
| RPC endpoint | `http://127.0.0.1:8545` | local Hardhat node |

## Data mapping (backend → chain)

The backend's `POST /api/token/calculate` already computes everything
registration needs; the contract recomputes the supply on-chain and the
two must always agree:

| Flask value | Contract input / check |
|---|---|
| deterministic property reference: `prop-` + first 32 hex of SHA-256 over the canonical feature JSON (computed by the bridge in `chain_service.property_ref_for`) | `propertyRef` (unique — duplicates revert; the same property always derives the same reference, while the per-request valuation id is stored on the record as `valuation_request_id` for traceability) |
| `valuation_inr` (whole rupees, integer) | `valuationInr` |
| risk `risk_score` (0–100) | `riskScore` |
| risk `risk_category` (LOW/MEDIUM/HIGH) | `riskCategory` |
| `token_supply` = floor(`valuation_inr` / 10000) | must equal `getProperty(id).tokenSupply` and `computeSupply(valuationInr)` |
| `rounding.remainder_inr` | must equal `getProperty(id).residualInr` |

## Call sequence (bridge responsibilities)

1. `registerProperty(propertyRef, valuationInr, riskScore, riskCategory)`
   — bridge wallet must hold `REGISTRAR_ROLE`. Returns the new
   `propertyId` via the `PropertyRegistered` event.
2. `mintPropertyTokens(propertyId)` — bridge wallet must hold
   `MINTER_ROLE`. Mints the full supply to the contract's inventory.
3. Buyers call `buyTokens(propertyId, amount)` directly from their own
   wallets with `amount * tokenPriceWei` test ETH.
4. Holders transfer with the standard ERC-1155
   `safeTransferFrom(from, to, id, amount, data)`.

## Read interface (explorer / dashboard)

- `totalProperties()`, `getProperty(id)` — registry + metadata
  (valuation, supply, residual, sold, risk score/category).
- `availableSupply(id)` — unsold inventory.
- `balanceOf(account, id)`, `propertiesOf(account)` — ownership.
- Events for the explorer's transaction history: `PropertyRegistered`,
  `TokensMinted`, `TokensPurchased`, ERC-1155 `TransferSingle`.

## Roles & keys

- Deployer holds `DEFAULT_ADMIN_ROLE`, `REGISTRAR_ROLE`, `MINTER_ROLE`
  by default; grant `REGISTRAR_ROLE`/`MINTER_ROLE` to the bridge wallet
  for operations (`grantRole`).
- Hardhat's local accounts are public test accounts — never use them
  with real funds; no keys are stored in this repository.

## Hosted-mode behaviour

A local Hardhat chain cannot be hosted on Render/Vercel. In the hosted
showcase deployment the chain calls are disabled: the token endpoint
keeps returning the *calculation* (supply/remainder), and chain
operations report the designed `503 CHAIN_UNAVAILABLE`. The full flow
(register → mint → buy → transfer) is demonstrated locally.
