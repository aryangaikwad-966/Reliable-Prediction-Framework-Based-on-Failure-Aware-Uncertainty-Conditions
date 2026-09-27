# Architecture

```text
Browser
  ↓
React / Vite
  ↓ relative /api requests
Node.js / Express
  ├── PostgreSQL: market data, predictions, outcomes, failure memory
  └── FastAPI ML service
        ├── XGBoost artifact
        ├── feature distribution / novelty
        ├── uncertainty signals
        ├── drift signal
        └── selective decision
```

The browser never calls FastAPI directly. Node is the application API and owns validation, orchestration, and persistence. The core risk formulation is duplicated as small pure functions in TypeScript and Python so that the API can remain useful in demo mode while the ML service can be tested independently.

The domain layer is separated at the feature and ingestion boundary. `server/src/research.ts` and `ml-service/app/core.py` do not know that the source domain is agriculture. A future domain adapter can provide a different target and context vector without changing the failure-aware decision contract.

## Data lifecycle

1. A data operator ingests raw APMC rows in chunks.
2. Normalized time-series rows are stored in PostgreSQL.
3. Feature engineering creates shifted lags and rolling values.
4. A chronological training job stores a versioned XGBoost artifact.
5. Node retrieves the context and calls FastAPI for a base forecast and signals.
6. The reliability gate accepts or abstains.
7. A later observed outcome creates a failure-memory record.
8. Future requests can use contextual failure rates.

No future outcome is available to the prediction being evaluated. The current demo seed is explicitly separate from this lifecycle.