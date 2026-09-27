# Complete Setup Guide

This guide walks you through setting up the entire Reliable Prediction Framework from scratch.

## Prerequisites

- **PostgreSQL 16+** installed and running
- **Node.js 22+** with npm
- **Python 3.9+** with pip

## Step 1: Environment Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your configuration:
```env
NODE_ENV=development
PORT=3001
DEMO_MODE=false  # Set to true for demo mode without database
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/reliable_prediction
ML_SERVICE_URL=http://localhost:8000
VITE_API_BASE_URL=/api
DATA_PATH=./data/apmc-arrivals-and-prices-old-data.csv
MODEL_DIR=./ml-service/models
RELIABILITY_THRESHOLD=0.70
FAILURE_THRESHOLD=0.25
```

## Step 2: Database Setup

1. Create the database:
```bash
createdb reliable_prediction
```

2. Run the schema:
```bash
psql reliable_prediction -f db/schema.sql
```

## Step 3: Install Dependencies

### Backend (Node.js)
```bash
npm install
```

### ML Service (Python)
```bash
cd ml-service
pip install -r requirements.txt
# or using uv:
uv pip install -r requirements.txt
cd ..
```

## Step 4: Install ML Dependencies

### ML Service (Python)
```bash
cd ml-service
pip install -r requirements.txt
cd ..
```

## Step 5: Data Ingestion

The APMC dataset should be placed at `data/apmc-arrivals-and-prices-old-data.csv`.

Run the ingestion script:
```bash
PYTHONPATH=./ml-service python -m training.ingest \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --database-url "$DATABASE_URL"
```

This will:
- Read the 5.4M-row CSV in chunks
- Normalize column names
- Handle duplicate keys by aggregation
- Insert data into PostgreSQL
- Report the total rows ingested

**Expected output:** ~2-3M aggregated rows (due to duplicate key resolution)

## Step 6: Train the Model

Train an XGBoost model for Tomato price prediction:
```bash
PYTHONPATH=./ml-service python -m training.train \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --commodity Tomato \
  --horizon 7 \
  --model-dir ./ml-service/models
```

This will:
- Filter data for the specified commodity
- Engineer time-series features (lags, rolling windows, etc.)
- Perform chronological train/test split
- Train XGBoost model
- Save model artifact with metadata
- Output training metrics

**Expected output:**
```json
{
  "status": "TRAINED",
  "version": "20250927150000-tomato",
  "artifact": "./ml-service/models/20250927150000-tomato.joblib",
  "metrics": {
    "mae": 45.23,
    "rmse": 67.89,
    "r2": 0.85,
    "rows": 150000,
    "train_rows": 120000,
    "test_rows": 30000
  }
}
```

## Step 7: Start the Services

### Development Mode (All services)

```bash
npm run dev
```

This starts:
- Frontend (Vite) on http://localhost:5000
- Backend (Express) on http://localhost:3001
- ML Service (FastAPI) on http://localhost:3001 (needs separate terminal)

Start ML Service in a separate terminal:
```bash
npm run dev:ml
```

### Individual Services

**Backend only:**
```bash
npm run dev:server
```

**Frontend only:**
```bash
npm run dev:client
```

**ML Service only:**
```bash
npm run dev:ml
```

### Production Mode (Docker)

```bash
docker compose up --build
```

Services will be available at:
- Frontend: http://localhost:5000
- Backend API: http://localhost:3001
- ML Service: http://localhost:8000
- PostgreSQL: localhost:5432

## Step 8: Verify Installation

### Check Backend Health
```bash
curl http://localhost:3001/api/health
```

Expected response:
```json
{
  "ok": true,
  "service": "node-api",
  "database": { "connected": true, "mode": "LIVE" },
  "mlService": "http://localhost:8000",
  "demoMode": false
}
```

### Check ML Service Health
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "ok": true,
  "service": "fastapi-ml",
  "model_dir": "./ml-service/models"
}
```

### Check Model Availability
```bash
curl http://localhost:8000/metadata
```

Expected response:
```json
{
  "model_available": true,
  "model_dir": "./ml-service/models"
}
```

## Step 9: Make a Test Prediction

### Via API
```bash
curl -X POST http://localhost:3001/api/predictions \
  -H "Content-Type: application/json" \
  -d '{
    "commodity": "Tomato",
    "market": "Lasalgaon",
    "variety": "Local",
    "horizon": 7
  }'
```

Expected response:
```json
{
  "id": "pred_1727486400000_450",
  "commodity": "Tomato",
  "market": "Lasalgaon",
  "variety": "Local",
  "horizon": 7,
  "prediction": 456.78,
  "basePrediction": 456.78,
  "reliability": 0.8234,
  "failureRisk": 0.1766,
  "decision": "ACCEPTED",
  "createdAt": "2025-09-27T15:00:00.000Z",
  "isDemo": false,
  "signals": {
    "modelUncertainty": 0.18,
    "historicalFailureRisk": 0.12,
    "noveltyScore": 0.15,
    "driftScore": 0.08,
    "missingInformation": 0.0,
    "contextRisk": 0.0
  },
  "reasons": []
}
```

### Via Web Interface

1. Open http://localhost:5000
2. Navigate to "Predictions"
3. Select commodity, market, variety, and horizon
4. Click "Generate prediction"
5. View the reliability assessment and decision

## Step 10: Submit an Outcome

After the actual price is known, submit the outcome:

```bash
curl -X POST http://localhost:3001/api/outcomes \
  -H "Content-Type: application/json" \
  -d '{
    "predictionId": "pred_1727486400000_450",
    "actual": 465.0
  }'
```

This will:
- Calculate absolute and relative error
- Classify failure severity
- Store in failure memory
- Make available for future predictions

## Step 11: View Evaluation Metrics

After accumulating predictions with outcomes:

```bash
curl http://localhost:3001/api/evaluation
```

Expected response:
```json
{
  "status": "MEASURED",
  "mae": 42.3,
  "rmse": 65.8,
  "mape": 0.085,
  "r2": 0.87,
  "coverage": 0.75,
  "selectiveRisk": 42.3,
  "abstentionRate": 0.25,
  "failureDetectionRate": 0.15,
  "aurc": 0.032
}
```

## Running Experiments

The framework supports ablation studies to compare different configurations:

### Via API
```bash
curl -X POST http://localhost:3001/api/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "BASE",
    "configuration": {
      "commodity": "Tomato",
      "market": "Lasalgaon",
      "horizon": 7,
      "components": ["base_model"]
    }
  }'
```

### Experiment Configurations

- **A (BASE)**: XGBoost base forecast only
- **B (UNCERTAINTY)**: Base + model uncertainty
- **C (FAILURE_MEMORY)**: Base + contextual failure cases
- **D (MEMORY_OOD)**: Base + failure memory + novelty detection
- **E (FULL_FRAMEWORK)**: All components + drift + abstention

## Troubleshooting

### Database Connection Issues

**Error:** "connection refused" or "database does not exist"

**Solution:**
1. Verify PostgreSQL is running: `pg_isready`
2. Check DATABASE_URL in `.env`
3. Create database: `createdb reliable_prediction`
4. Run schema: `psql reliable_prediction -f db/schema.sql`

### Model Not Found

**Error:** "No trained model is available"

**Solution:**
1. Ensure data ingestion completed successfully
2. Run training script with correct paths
3. Check MODEL_DIR in `.env`
4. Verify model file exists: `ls ml-service/models/`

### Feature Serving Errors

**Error:** "Insufficient historical data"

**Solution:**
1. Ensure data ingestion completed
2. Check that market/commodity has sufficient data
3. Query database: `SELECT COUNT(*) FROM market_data WHERE commodity = 'Tomato' AND market = 'Lasalgaon'`

### ML Service Unavailable

**Error:** "The live ML service is unavailable"

**Solution:**
1. Start ML service: `npm run dev:ml`
2. Check ML_SERVICE_URL in `.env`
3. Verify ML service health: `curl http://localhost:8000/health`

### Port Conflicts

**Error:** "Port already in use"

**Solution:**
1. Change PORT in `.env`
2. Kill process using the port: `lsof -ti:3001 | xargs kill`

## Development Workflow

### Making Changes

1. **Backend changes**: Edit `server/src/*.ts`, server auto-reloads
2. **ML service changes**: Edit `ml-service/app/*.py`, restart ML service
3. **Frontend changes**: Edit `src/*.tsx`, Vite hot-reloads

### Running Tests

```bash
# Backend tests
npm test

# ML service tests
pytest ml-service/app/test_core.py

# Type checking
npm run typecheck
```

### Database Reset

```bash
# Drop and recreate database
dropdb reliable_prediction
createdb reliable_prediction
psql reliable_prediction -f db/schema.sql

# Re-ingest data
PYTHONPATH=./ml-service python -m training.ingest \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --database-url "$DATABASE_URL"
```

## Production Deployment

### Environment Variables

Set these in production:
```env
NODE_ENV=production
DEMO_MODE=false
DATABASE_URL=postgresql://user:password@host:5432/dbname
ML_SERVICE_URL=http://localhost:8000
RELIABILITY_THRESHOLD=0.70
FAILURE_THRESHOLD=0.25
```

### Manual Deployment

1. Build frontend: `npm run build`
2. Start backend: `npm start`
3. Start ML service in separate terminal:
```bash
cd ml-service
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Monitoring

### Check Service Status
```bash
# Backend
curl http://localhost:3001/api/health

# ML Service
curl http://localhost:8000/health

# Database
psql reliable_prediction -c "SELECT COUNT(*) FROM market_data"
```

### View Recent Predictions
```bash
curl http://localhost:3001/api/predictions
```

### View Failure Memory
```bash
curl http://localhost:3001/api/failures
```

## Next Steps

1. **Train models for other commodities**: Onion, Potato, Wheat
2. **Experiment with different horizons**: 14, 30 days
3. **Tune reliability thresholds**: Based on your risk tolerance
4. **Integrate external events**: Weather, policy data
5. **Run ablation studies**: Compare configurations A-E
6. **Monitor drift**: Regularly check drift detection status

## Support

For issues or questions:
- Check the audit report: `AUDIT_REPORT.md`
- Review architecture: `ARCHITECTURE.md`
- API documentation: `API.md`
- Experiment guide: `EXPERIMENTS.md`
