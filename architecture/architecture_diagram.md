# Architecture Diagrams

**Status:** FOR APPROVAL (companion to `architecture.md`). All diagrams are Mermaid — they render in GitHub, VS Code and the project docs, and are version-controlled as text so any change is reviewable in a diff.

## 1. System architecture (containers & artefacts)

```mermaid
flowchart TB
    subgraph OFFLINE["OFFLINE — ML environment (Python 3.12, never deployed)"]
        RAW[("data/raw/train.csv<br/>29,451 × 12 · immutable")]
        CLEAN["B · cleaning.py + transformers.py<br/>preprocessing v2 · schema v1.1.0"]
        TRAIN["C/D · train.py + tune.py<br/>11 models × raw/log → tuning"]
        FINAL["E · finalize.py"]
        MODEL[("ml/model.pkl<br/>CatBoost · log1p · extended features")]
        META[("ml/artifacts/model_metadata.json<br/>shap_summary.json · risk_reference.json")]
        RAW --> CLEAN --> TRAIN --> FINAL --> MODEL
        FINAL --> META
    end

    SCHEMA{{"shared/feature_schema.json<br/>v1.1.0 — single source of truth"}}
    SCHEMA -. "trains on" .-> CLEAN
    SCHEMA -. "validates on" .-> API
    SCHEMA -. "renders from" .-> UI

    subgraph SERVE["SERVING — Flask API (Render or local)"]
        API["J · Flask REST API /api/v1"]
        PRED["F · prediction_service"]
        SHAP["G · explain_service<br/>TreeExplainer + aggregation"]
        RISK["H · risk_service<br/>Risk Score v0.1 (proposed)"]
        TOK["I · token_service<br/>floor(value / 10,000)"]
        CHAINC["M · chain_client"]
        API --> PRED --> SHAP --> RISK --> TOK
        API --> CHAINC
    end

    MODEL ==>|"joblib.load once<br/>SHA-256 verified"| PRED
    META ==>|"/model-info"| API

    MONGO[("MongoDB Atlas<br/>predictions · properties · token_events<br/>INDEX ONLY — chain is truth")]
    API <-->|"audit + index"| MONGO

    subgraph CHAIN["BLOCKCHAIN — local machine"]
        BRIDGE["M · Node.js bridge<br/>ethers.js v6 · internal only · holds keys"]
        HARDHAT["L · Hardhat node — chainId 31337"]
        CONTRACT["PropertyTokenisation.sol<br/>ERC-1155 · Solidity 0.8.24"]
        HARDHAT --- CONTRACT
        BRIDGE -->|"JSON-RPC · signed txs"| HARDHAT
    end
    CHAINC -->|"HTTP /internal/*"| BRIDGE

    subgraph CLIENT["CLIENT — React SPA (Vercel or local)"]
        UI["K · Vite + React + Tailwind<br/>Recharts · Framer Motion · Lucide"]
    end
    UI -->|"HTTPS/JSON only<br/>never touches chain"| API
```

## 2. Sequence — one valuation (the demo path)

```mermaid
sequenceDiagram
    actor User
    participant UI as React SPA
    participant API as Flask API
    participant ML as model.pkl pipeline
    participant SHAP as SHAP service
    participant RISK as Risk + Token services
    participant DB as MongoDB
    User->>UI: Property form (ADDRESS + 8 fields, coords optional)
    UI->>API: POST /api/v1/predict
    API->>API: Validate vs schema v1.1.0 (422 on failure)
    Note over API: coords omitted → city centroid<br/>(from fitted pipeline, flagged)
    API->>ML: predict(frame) — pipeline derives CITY, LOCALITY,<br/>SQFT_PER_BHK + extended features internally
    ML-->>API: log1p price → expm1 → ₹ lakh / ₹ INR
    API->>SHAP: explain(preprocessed row)
    SHAP-->>API: base_value_log + aggregated contributions (share %)
    API->>RISK: score(input, city reference stats)
    RISK-->>API: score 0–100, band, full breakdown · token supply (floor)
    API->>DB: persist prediction (audit) → prediction_id
    API-->>UI: price + SHAP + risk + token quote + notice
    UI->>User: PriceCard · ShapChart · RiskGauge · TokenPanel
```

## 3. Sequence — tokenisation (register → mint → buy → transfer)

```mermaid
sequenceDiagram
    actor User
    participant UI as React SPA
    participant API as Flask API
    participant DB as MongoDB
    participant BR as Node bridge
    participant SC as PropertyTokenisation (ERC-1155)
    User->>UI: Tokenise (owner address; HIGH-risk ack if required)
    UI->>API: POST /api/v1/tokenise {prediction_id, owner_address}
    API->>DB: re-read stored prediction (price/supply/risk — server-side)
    API->>BR: POST /internal/register (idempotent on prediction_id)
    BR->>SC: registerProperty(owner, valueInr, riskScore, band, supply, metadataHash)
    SC-->>BR: PropertyRegistered(propertyId) + tx hash
    BR-->>API: property_id, register_tx_hash
    API->>BR: POST /internal/mint {property_id}
    BR->>SC: mintTokens(propertyId)
    SC-->>BR: TokensMinted + tx hash
    API->>DB: mirror property + events (index)
    API-->>UI: 201 — property_id, both tx hashes, network: hardhat-local 31337
    Note over User,SC: Later: buyTokens (payable, demo price) and<br/>safeTransferFrom via /tokenise/buy and /tokenise/transfer —<br/>same API → bridge → contract path; ownership always read from chain.
```

## 4. Deployment topology (with the chain constraint)

```mermaid
flowchart LR
    subgraph VERCEL["Vercel"]
        FE["React SPA (static)<br/>VITE_API_BASE_URL"]
    end
    subgraph RENDER["Render"]
        BE["Flask + gunicorn<br/>model.pkl loaded at boot"]
    end
    subgraph ATLAS["MongoDB Atlas"]
        MDB[("predictions / properties<br/>token_events / chain_sync")]
    end
    subgraph LOCAL["Demo machine (Mode 1 — committed)"]
        BR2["Node bridge"]
        HH2["Hardhat node :8545<br/>chainId 31337"]
        BR2 --> HH2
    end
    FE -->|"HTTPS"| BE
    BE <--> MDB
    BE -.->|"Mode 1: bridge reachable<br/>Mode 2 hosted: 503 CHAIN_UNAVAILABLE<br/>unless an external RPC is configured"| BR2
```

## 5. Data model — MongoDB index (chain remains the ownership truth)

```mermaid
erDiagram
    PREDICTIONS ||--o| PROPERTIES : "tokenised as"
    PROPERTIES ||--o{ TOKEN_EVENTS : "indexed from events"
    PREDICTIONS {
        string prediction_id PK
        json input
        float predicted_price_lacs
        json shap_summary
        json risk_breakdown
        int token_supply
        string model_version
        string risk_method_version
        datetime created_at
    }
    PROPERTIES {
        int property_id PK "on-chain id"
        string prediction_id FK
        string owner_address
        int token_supply
        string register_tx_hash
        string mint_tx_hash
        int last_synced_block
    }
    TOKEN_EVENTS {
        string tx_hash
        int property_id FK
        string event_type "Registered|Minted|Purchased|Transfer"
        string from_address
        string to_address
        int amount
        int block_number
    }
```
