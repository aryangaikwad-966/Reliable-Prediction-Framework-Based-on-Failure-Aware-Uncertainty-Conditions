# Reliable Prediction Framework

> **Failure-aware selective forecasting for non-stationary agricultural markets.**

The system forecasts APMC modal price seven calendar days ahead and, just as importantly, decides when the evidence is insufficient to safely return a forecast. It combines a React dashboard, Express API, FastAPI inference service, PostgreSQL audit store, and reproducible research artifacts.

## Contents

- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Complete setup](#complete-setup)
- [Commands](#commands)
- [Data and research workflows](#data-and-research-workflows)
- [Verification](#verification)
- [API examples](#api-examples)
- [Troubleshooting](#troubleshooting)
- [Research integrity](#research-integrity)

## Decision contract

| Decision | Meaning | `prediction` |
|---|---|---|
| `ACCEPTED` | The configured reliability policy permits the forecast. | Numeric Rs/Quintal value |
| `ABSTAINED` | A value may be computable, but the policy withholds it. | `null` |
| `OUT_OF_SCOPE` | The context is unsupported or has insufficient evidence. | `null` |

The browser never calculates a forecast, risk score, or decision locally.

## Architecture

```text
React + Vite (5173)
        │ /api
        ▼
Express application API (3001)
        │                  │
        ▼                  └── PostgreSQL
FastAPI inference (8000)        market data, decisions, outcomes, audit memory
        │
        └── features → model artifact → uncertainty / novelty / decision signals
```

Express validates and orchestrates application requests. FastAPI owns feature generation and model inference. PostgreSQL provides durable history and outcome auditability.

## Quick start

Use this path when PostgreSQL, the schema, market data, and `ml-service/models/latest.joblib` are already available.

```bash
# Terminal 1 — FastAPI ML service
npm install
python3 -m pip install -r ml-service/requirements.txt
npm run dev:ml
```

```bash
# Terminal 2 — Express API + React/Vite UI
npm run dev
```

Open <http://localhost:5173>.

| Service | URL |
|---|---|
| Dashboard | <http://localhost:5173> |
| Express health | <http://localhost:3001/api/health> |
| FastAPI health | <http://localhost:8000/health> |

Stop a service with `Ctrl+C` in its terminal. Docker is not required.

## Complete setup

### Prerequisites

| Requirement | Version | Verify |
|---|---:|---|
| Node.js | 18+ | `node --version` |
| npm | bundled with Node | `npm --version` |
| Python | 3.9+ | `python3 --version` |
| PostgreSQL | 16+ recommended | `psql --version` |

### Install dependencies

```bash
git clone <your-repository-url>
cd Reliable-Prediction-Framework-Based-on-Failure-Aware-Uncertainty-Conditions-main

npm install
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r ml-service/requirements.txt
```

### Configure environment

```bash
cp .env.example .env
```

Edit `.env` with local, non-committed settings:

```dotenv
NODE_ENV=development
PORT=3001
DEMO_MODE=false
DATABASE_URL=postgresql://YOUR_POSTGRES_USER@localhost:5432/reliable_prediction
ML_SERVICE_URL=http://localhost:8000
VITE_API_BASE_URL=/api
MODEL_DIR=./ml-service/models
RELIABILITY_THRESHOLD=0.70
FAILURE_THRESHOLD=0.25
```

Never commit `.env` or expose database credentials in screenshots, issues, or browser code.

### Create PostgreSQL schema

```bash
createdb reliable_prediction
export DATABASE_URL='postgresql://YOUR_POSTGRES_USER@localhost:5432/reliable_prediction'
npm run db:setup

# Equivalent direct command
psql "$DATABASE_URL" -f db/schema.sql
```

Verify the connection:

```bash
pg_isready
psql "$DATABASE_URL" -c 'select 1;'
```

### Confirm data and model availability

```bash
test -f ml-service/models/latest.joblib && echo 'Model artifact found'
psql "$DATABASE_URL" -c 'select count(*) as market_rows from market_data;'
```

The form only lists commodity/market/variety combinations with at least 30 observations. A newly created schema has no market data; it must be populated before live form options appear.

## Commands

Run commands from the repository root unless stated otherwise.

| Command | Purpose |
|---|---|
| `npm run dev` | Starts Express on `3001` and Vite on `5173`. |
| `npm run dev:server` | Starts Express with watch mode. |
| `npm run dev:client` | Starts Vite only. |
| `npm run dev:ml` | Starts FastAPI on `8000`. |
| `npm run build` | Type-checks and creates the frontend bundle in `dist/`. |
| `npm run start` | Starts Express without watch mode; run `npm run build` first. |
| `npm run typecheck` | Runs TypeScript checking without emitting files. |
| `npm run test` | Runs the complete Vitest suite. |
| `npm run test:integration` | Runs Node decision-pipeline integration tests. |
| `npm run test:all` | Runs Node tests and FastAPI core tests. |
| `npm run db:setup` | Applies `db/schema.sql` using `DATABASE_URL`. |

### Model training and Python tests

```bash
# FastAPI core tests
cd ml-service
python3 -m pytest app/test_core.py -q
cd ..

# Train a versioned model and update latest.joblib.
# Run as a package from ml-service so training.* imports resolve.
cd ml-service
python3 -m training.train \
  --data ../data/apmc-arrivals-and-prices-old-data.csv \
  --commodity Tomato \
  --horizon 7 \
  --model-dir models
cd ..
```

## Data and research workflows

These jobs can be resource intensive. Run them only when you need to regenerate research artifacts.

```bash
# 1. Build the enriched dataset and exact-7-day target.
python3 apmc_failure_aware_output/enrich_apmc.py

# 2. Run chronological selective-prediction evaluation.
python3 apmc_failure_aware_output/experiment_pipeline.py

# 3. Reproduce the ablation comparison.
python3 apmc_failure_aware_output/ablation_study.py

# 4. Import generated evaluation decisions/outcomes into PostgreSQL.
python3 populate_db.py
```

> `populate_db.py` clears and replaces the prediction, outcome, uncertainty, and failure-memory tables before importing evaluation data. It is a research-audit importer, not a routine production ingestion command.

| Artifact | Purpose |
|---|---|
| `apmc_failure_aware_output/apmc_failure_aware_enriched.csv` | Enriched dataset; never load it into the browser. |
| `apmc_failure_aware_output/evaluation_results.json` | Selective evaluation output. |
| `apmc_failure_aware_output/ablation_results.json` | Offline ablation data shown by the Evaluation UI. |
| `apmc_failure_aware_output/failure_memory_schema.csv` | Generated evaluation prediction/outcome records. |
| `apmc_failure_aware_output/DATA_DICTIONARY.md` | Data and feature definitions. |

## Verification

Start all services, then run:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:3001/api/health
curl http://127.0.0.1:3001/api/metadata
curl http://127.0.0.1:3001/api/research-results
```

Run the full local quality gate:

```bash
npm run typecheck
npm test
npm run build
cd ml-service && python3 -m pytest app/test_core.py -q && cd ..
```

Healthy services should report:

- Express can reach PostgreSQL.
- FastAPI reports `model_available: true` when `latest.joblib` exists.
- The API returns an explicit `ACCEPTED`, `ABSTAINED`, or `OUT_OF_SCOPE` decision—never a fabricated fallback forecast.

## API examples

```bash
# Service readiness
curl http://127.0.0.1:3001/api/health

# Valid form combinations
curl http://127.0.0.1:3001/api/metadata

# Live request: Express → FastAPI → PostgreSQL
curl -X POST http://127.0.0.1:3001/api/predictions \
  -H 'Content-Type: application/json' \
  -d '{"commodity":"Tomato","market":"Abohar","variety":"Tomato","horizon":7}'

# Paged and filtered audit history
curl 'http://127.0.0.1:3001/api/predictions?limit=25&offset=0&decision=ACCEPTED'

# Offline experiment artifact; not current live performance
curl http://127.0.0.1:3001/api/research-results
```

| HTTP status | Meaning |
|---:|---|
| `201` | A decision was created and persisted. |
| `400` | Invalid request body. |
| `409` | An outcome is already recorded for this prediction. |
| `422` | Expected `OUT_OF_SCOPE` business result; prediction remains `null`. |
| `503` | ML service unavailable/not ready; no substitute forecast is returned. |

## Troubleshooting

### A port is already in use

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:3001 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Stop only the process you own. If `curl http://127.0.0.1:8000/health` responds, do not start another FastAPI instance.

### No selectable markets in the UI

```bash
psql "$DATABASE_URL" -c 'select count(*) from market_data;'
curl http://127.0.0.1:3001/api/metadata
```

The UI intentionally hides combinations with fewer than 30 observations.

### `OUT_OF_SCOPE` / browser Network 422

This is expected validation, not a React crash. The selected context is unsupported by available history or by the loaded model. The UI must display a null forecast and the server explanation.

### ML service unavailable

```bash
curl http://127.0.0.1:8000/health
npm run dev:ml
test -f ml-service/models/latest.joblib
```

### PostgreSQL connection fails

```bash
pg_isready
psql "$DATABASE_URL" -c 'select 1;'
```

## Research integrity

- The verified target is `target_modal_price_h7d`: modal price exactly seven calendar days ahead, in Rs/Quintal where supported.
- Offline ablation metrics and operational database metrics are intentionally displayed separately.
- The checked-in ablation report shows persistence outperforms the proposed XGBoost model on the stated test set; that baseline is retained rather than hidden.
- Current model scope comes from the loaded artifact; the supplied model is Tomato-specific.
- Weather, crop-damage, and policy-event data are not integrated.
- Failure memory must not use an outcome before it was available to the original prediction.

## Further documentation

- [UI-to-backend integration matrix](UI_BACKEND_INTEGRATION_MATRIX.md)
- [UI implementation report](UI_IMPLEMENTATION_REPORT.md)
- [End-to-end verification report](END_TO_END_VERIFICATION_REPORT.md)
- [Demo readiness report](DEMO_READINESS_REPORT.md)
- [Evaluation audit](EVALUATION_AUDIT_REPORT.md)
- [Final reproducibility report](FINAL_REPRODUCIBILITY_REPORT.md)
