# Local Setup Guide (No Docker)

This guide is for running the Reliable Prediction Framework locally without Docker.

## System Requirements

- **macOS or Linux** (Windows may work with WSL)
- **PostgreSQL 16+** installed and running
- **Node.js 22+** with npm
- **Python 3.9+** with pip

## Quick Start

1. **Install PostgreSQL** (if not already installed)
   ```bash
   # macOS
   brew install postgresql
   brew services start postgresql
   
   # Linux (Ubuntu/Debian)
   sudo apt-get install postgresql postgresql-contrib
   sudo systemctl start postgresql
   ```

2. **Clone and setup**
   ```bash
   cd Reliable-Prediction-Framework-Based-on-Failure-Aware-Uncertainty-Conditions-main
   
   # Install dependencies
   npm install
   cd ml-service && pip install -r requirements.txt && cd ..
   
   # Setup database
   createdb reliable_prediction
   psql reliable_prediction -f db/schema.sql
   
   # Configure environment
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start services**
   ```bash
   # Quick start (all services)
   ./start.sh
   
   # Or manually:
   # Terminal 1
   npm run dev
   
   # Terminal 2
   npm run dev:ml
   ```

4. **Access the application**
   - Frontend: http://localhost:5000
   - Backend API: http://localhost:3001
   - ML Service: http://localhost:8000

## Detailed Setup

### Step 1: PostgreSQL Setup

#### macOS
```bash
# Install
brew install postgresql@16

# Start service
brew services start postgresql@16

# Create database
createdb reliable_prediction

# Apply schema
psql reliable_prediction -f db/schema.sql

# Verify
psql reliable_prediction -c "\dt"
```

#### Linux (Ubuntu/Debian)
```bash
# Install
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib

# Start service
sudo systemctl start postgresql

# Create database
sudo -u postgres createdb reliable_prediction

# Apply schema
sudo -u postgres psql reliable_prediction -f db/schema.sql

# Verify
sudo -u postgres psql reliable_prediction -c "\dt"
```

### Step 2: Node.js Setup

```bash
# Verify Node.js version
node --version  # Should be 22+

# Install dependencies
npm install

# Verify installation
npm list --depth=0
```

### Step 3: Python Setup

```bash
# Verify Python version
python3 --version  # Should be 3.9+

# Install ML service dependencies
cd ml-service
pip3 install -r requirements.txt
cd ..

# Verify installation
python3 -c "import fastapi; import xgboost; import pandas; print('All OK')"
```

### Step 4: Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env  # or use your preferred editor
```

Required settings:
```env
NODE_ENV=development
PORT=3001
DEMO_MODE=false
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/reliable_prediction
ML_SERVICE_URL=http://localhost:8000
VITE_API_BASE_URL=/api
DATA_PATH=./data/apmc-arrivals-and-prices-old-data.csv
MODEL_DIR=./ml-service/models
RELIABILITY_THRESHOLD=0.70
FAILURE_THRESHOLD=0.25
```

### Step 5: Data Ingestion

```bash
# Ingest APMC dataset (this may take several minutes)
PYTHONPATH=./ml-service python3 -m training.ingest \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --database-url "postgresql://postgres:yourpassword@localhost:5432/reliable_prediction"
```

Expected output:
```
Ingested 2,345,678 aggregated rows.
```

### Step 6: Model Training

```bash
# Train XGBoost model for Tomato
PYTHONPATH=./ml-service python3 -m training.train \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --commodity Tomato \
  --horizon 7 \
  --model-dir ./ml-service/models
```

Expected output:
```json
{
  "status": "TRAINED",
  "version": "20250927150000-tomato",
  "artifact": "./ml-service/models/20250927150000-tomato.joblib",
  "metrics": {
    "mae": 45.23,
    "rmse": 67.89,
    "r2": 0.85
  }
}
```

### Step 7: Start Services

#### Option A: Quick Start Script
```bash
./start.sh
```

#### Option B: Manual Start

**Terminal 1 - Backend + Frontend:**
```bash
npm run dev
```

**Terminal 2 - ML Service:**
```bash
npm run dev:ml
```

### Step 8: Verify Setup

```bash
# Check backend health
curl http://localhost:3001/api/health

# Check ML service health
curl http://localhost:8000/health

# Check model availability
curl http://localhost:8000/metadata
```

Expected responses:
```json
// Backend
{
  "ok": true,
  "service": "node-api",
  "database": { "connected": true, "mode": "LIVE" },
  "mlService": "http://localhost:8000",
  "demoMode": false
}

// ML Service
{
  "ok": true,
  "service": "fastapi-ml",
  "model_dir": "./ml-service/models"
}

// Metadata
{
  "model_available": true,
  "model_dir": "./ml-service/models"
}
```

## Troubleshooting

### PostgreSQL Issues

**Problem:** "connection refused"
```bash
# Check if PostgreSQL is running
pg_isready

# Start PostgreSQL
brew services start postgresql  # macOS
sudo systemctl start postgresql  # Linux
```

**Problem:** "database does not exist"
```bash
# Create database
createdb reliable_prediction

# Apply schema
psql reliable_prediction -f db/schema.sql
```

### Node.js Issues

**Problem:** "command not found: node"
```bash
# Install Node.js using nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 22
nvm use 22
```

**Problem:** "npm install fails"
```bash
# Clear cache and retry
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

### Python Issues

**Problem:** "python3: command not found"
```bash
# Install Python 3.9+
brew install python@3.9  # macOS
sudo apt-get install python3.9  # Linux
```

**Problem:** "pip install fails"
```bash
# Upgrade pip
python3 -m pip install --upgrade pip

# Install with user flag
pip3 install --user -r ml-service/requirements.txt
```

### Port Conflicts

**Problem:** "Port already in use"
```bash
# Find process using port
lsof -ti:3001 | xargs kill -9  # Backend
lsof -ti:5000 | xargs kill -9  # Frontend
lsof -ti:8000 | xargs kill -9  # ML Service

# Or change ports in .env
PORT=3002  # Backend
```

### Database Connection Issues

**Problem:** "FATAL: password authentication failed"
```bash
# Update DATABASE_URL in .env with correct password
# Or set PostgreSQL password
psql -d postgres
ALTER USER postgres PASSWORD 'yourpassword';
\q
```

## Running Tests

```bash
# Backend tests
npm test

# ML service tests
cd ml-service
pytest test_core.py
cd ..

# Integration tests
npm run test:integration
```

## Stopping Services

```bash
# If using start.sh, press Ctrl+C

# If running manually:
# Kill backend/frontend
lsof -ti:3001 | xargs kill -9
lsof -ti:5000 | xargs kill -9

# Kill ML service
lsof -ti:8000 | xargs kill -9
```

## Production Deployment

For production deployment:

1. Set `NODE_ENV=production` in `.env`
2. Build frontend: `npm run build`
3. Use process manager (PM2) for Node.js
4. Use systemd for ML service
5. Configure reverse proxy (nginx) for frontend
6. Enable SSL/TLS
7. Set up proper logging and monitoring

See SETUP_GUIDE.md for detailed production instructions.

## Data Management

### Backup Database
```bash
pg_dump reliable_prediction > backup.sql
```

### Restore Database
```bash
psql reliable_prediction < backup.sql
```

### Reset Database
```bash
dropdb reliable_prediction
createdb reliable_prediction
psql reliable_prediction -f db/schema.sql
```

## Performance Tips

1. **Database Indexes:** Ensure indexes exist on frequently queried fields
2. **Connection Pooling:** Adjust pool size in `server/src/db.ts`
3. **Caching:** React Query provides frontend caching
4. **Chunked Processing:** Data ingestion uses chunks (100,000 rows)
5. **Query Limits:** API queries are limited (100-1000 rows)

## Next Steps

1. Ingest the full APMC dataset
2. Train models for different commodities
3. Run ablation studies
4. Monitor prediction accuracy
5. Tune reliability thresholds
6. Integrate external event data (optional)

## Support

For issues:
- Check FINAL_VERIFICATION_REPORT.md for known limitations
- Review code comments for implementation details
- Check logs for error messages
- Verify all services are running before testing
