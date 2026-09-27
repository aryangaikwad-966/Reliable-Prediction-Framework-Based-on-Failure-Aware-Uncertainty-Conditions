# Reliable Prediction Framework Based on Failure-Aware Uncertainty Conditions

Technical title: *Reliable Prediction Framework Based on Failure-Aware Uncertainty Conditions for Selective Prediction in Non-Stationary Environments*

This repository implements a domain-agnostic failure-aware selective prediction framework, validated with agricultural crop-price forecasting. The first experiment targets **Tomato**, at market level, for a **7-day** horizon and `modal_price` in `Rs/Quintal`.

The research contribution is not ordinary price prediction:

```text
past context → base forecast → uncertainty + failure memory + novelty/OOD + drift
→ failure risk → ACCEPTED forecast or ABSTAINED decision
→ observed outcome → error analysis → adaptive contextual failure memory
```

The platform never displays a forecast for an abstained decision. Unmeasured research results are shown as `NOT RUN` or `Not available`, and unavailable external events are shown as `NOT AVAILABLE`.

## Current implementation

- React + TypeScript + Vite research dashboard
- Express + TypeScript API with validation and structured JSON responses
- PostgreSQL schema for market data, predictions, outcomes, memory, uncertainty, drift, models, experiments, and metrics
- FastAPI service with XGBoost training/inference boundaries
- **Real-time feature serving** from database for predictions
- **Evaluation metrics** calculation (MAE, RMSE, MAPE, R², coverage, selective risk, AURC)
- **Drift detection** using rolling error comparison
- **Historical failure memory retrieval** for contextual risk assessment
- **Risk-coverage curve** generation from actual predictions
- **Ablation study framework** for comparing configurations A-E
- Chunked CSV normalization and ingestion with documented duplicate-key aggregation
- Time-series feature engineering with leakage-safe shifts
- Transparent weighted reliability gate with selective prediction
- Contextual failure memory updates after observed outcomes
- Practical novelty/OOD distance and rolling drift helpers
- Docker Compose for frontend, backend, ML service, and PostgreSQL
- Unit and integration tests for decision logic and reliability calculations

## Quick Start

For a complete setup guide, see [SETUP_GUIDE.md](SETUP_GUIDE.md).

### Prerequisites

- PostgreSQL 16+
- Node.js 22+ with npm
- Python 3.12+ with uv or pip
- Docker (optional)

### Setup Steps

1. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your database URL and configuration
```

2. **Install dependencies**
```bash
npm install
cd ml-service && pip install -r requirements.txt && cd ..
```

3. **Setup database**
```bash
createdb reliable_prediction
psql reliable_prediction -f db/schema.sql
```

4. **Ingest data**
```bash
PYTHONPATH=./ml-service python -m training.ingest \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --database-url "$DATABASE_URL"
```

5. **Train model**
```bash
PYTHONPATH=./ml-service python -m training.train \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --commodity Tomato \
  --horizon 7 \
  --model-dir ./ml-service/models
```

6. **Start services**
```bash
# Terminal 1: Backend + Frontend
npm run dev

# Terminal 2: ML Service
npm run dev:ml
```

7. **Access the application**
- Web UI: http://localhost:5000
- Backend API: http://localhost:3001
- ML Service: http://localhost:8000

## Run in Replit

The default Replit workflow is:

```bash
npm install
npm run dev
```

It serves the Vite UI on port `5000` and the Express API on port `3001`. Without a database or trained model, the UI runs in clearly marked **DEMO DATA** mode. This is not a claim about model performance.

Copy `.env.example` to `.env` for local configuration. `SESSION_SECRET` is not required by the current unauthenticated research MVP and should remain in Replit Secrets if authentication is added later.

## Run Locally

### Prerequisites
- PostgreSQL 16+ installed and running
- Node.js 22+ with npm
- Python 3.9+ with pip

### Setup Steps

1. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your database URL
```

2. **Install dependencies**
```bash
npm install
cd ml-service && pip install -r requirements.txt && cd ..
```

3. **Setup database**
```bash
createdb reliable_prediction
psql reliable_prediction -f db/schema.sql
```

4. **Start services**
```bash
# Terminal 1: Backend + Frontend
npm run dev

# Terminal 2: ML Service
npm run dev:ml
```

The web UI is at `http://localhost:5000`, the API health check is at `http://localhost:3001/api/health`, and FastAPI is at `http://localhost:8000/health`.

## Dataset setup

The repository does not contain the 5.4 million-row APMC CSV. Put the provided files under `data/`:

- `data/apmc-arrivals-and-prices-old-data.csv`
- optional codebook: `data/APMC_Arrivals_And_Prices__Old_Data_codebook.xlsx`

The CSV is read in chunks. `ml-service/training/ingest.py`:

1. parses dates and numeric fields;
2. drops unusable rows and the fully missing `origin` field;
3. normalizes identifiers and units;
4. resolves repeated `(report_date, market, commodity, variety)` keys by averaging numeric price/arrival values rather than blindly deleting rows;
5. inserts normalized records into PostgreSQL.

```bash
PYTHONPATH=./ml-service python -m training.ingest --data ./data/apmc-arrivals-and-prices-old-data.csv
```

## Train an actual model

After PostgreSQL is running and data has been ingested:

```bash
PYTHONPATH=./ml-service python -m training.train \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --commodity Tomato \
  --horizon 7 \
  --model-dir ./ml-service/models
```

Training uses an expanding chronological split. It does not randomly split the time series and does not use future rows for lag features. Artifacts include the XGBoost model, feature statistics, metadata, and measured holdout metrics.

## Run ablation studies

Compare different framework configurations:

```bash
PYTHONPATH=./ml-service python -m training.experiments \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --commodity Tomato \
  --horizon 7 \
  --config ALL \
  --database-url "$DATABASE_URL"
```

This runs experiments A-E and saves comparative results.

## Backend API

See [API.md](API.md). Main routes include:

- `GET /api/dashboard`
- `POST /api/predictions`
- `GET /api/predictions`
- `POST /api/outcomes`
- `GET /api/failures`
- `GET /api/failure-memory/context` - Historical failure retrieval
- `GET /api/reliability`
- `GET /api/uncertainty`
- `GET /api/drift` - Drift detection with real metrics
- `GET /api/evaluation` - Real evaluation metrics
- `GET /api/experiments` - Experiment registry
- `POST /api/experiments` - Create experiment
- `GET /api/data`
- `POST /api/models/train`

## Tests and checks

```bash
npm run typecheck
npm test
npm run test:integration  # Integration tests
pytest -q ml-service/app/test_core.py
```

## Research integrity and limitations

- The supplied dataset covers approximately ten months of 2025; the project does not fabricate earlier years.
- Weather, policy, news, and supply events are not integrated and are not presented as observations.
- Demo decisions are deterministic and labelled; they are interface seed data, not experimental evidence.
- The system now supports real-time predictions with feature serving from the database.
- Evaluation metrics are calculated from actual prediction outcomes, not fabricated.
- Drift detection uses rolling error comparison between recent and historical predictions.
- Historical failure memory is retrieved and used in uncertainty calculations.
- Risk-coverage curves are generated from actual predictions and outcomes.
- Ablation studies can be executed to compare framework configurations.

## Documents

- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Complete setup instructions
- [AUDIT_REPORT.md](AUDIT_REPORT.md) - Comprehensive project audit
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [DATA_PIPELINE.md](DATA_PIPELINE.md) - Data processing details
- [ML_PIPELINE.md](ML_PIPELINE.md) - Machine learning pipeline
- [API.md](API.md) - API documentation
- [EXPERIMENTS.md](EXPERIMENTS.md) - Experiment framework(EXPERIMENTS.md)