# Reliable Prediction Framework Based on Failure-Aware Uncertainty Conditions

This project implements a **Failure-Aware Selective Prediction Framework** for non-stationary, highly volatile commodity markets (e.g., Agricultural produce like Tomatoes). 

In dynamic markets, base machine learning models (like XGBoost) frequently break down and experience severe out-of-distribution (OOD) errors due to sudden trend shifts. This framework demonstrates how estimating prediction uncertainty and incorporating historical context can successfully flag these unpredictable transitions and **abstain** from making dangerous predictions.

By abstaining on the riskiest ~23.5% of cases, the selective framework correctly reduces prediction error (MAE) by substantial margins, outperforming both the base model and naive persistence baselines.

## System Architecture

The project consists of three main pipelines:
1. **Data Enrichment & Feature Engineering**: Processes millions of rows of APMC data using DuckDB to efficiently compute rolling statistics, momentum, and strict observation-based lags (preventing temporal leakage).
2. **Selective Prediction ML Pipeline**: Trains the base XGBoost model, alongside an out-of-sample risk estimator that calculates prediction unreliability and applies validation-tuned abstention thresholds.
3. **Application & Dashboard**: A real-time Node.js/Express backend paired with a PostgreSQL database and a frontend UI. It ingests historical predictions, tracks "Failure Memory," and visually presents the selective risk distribution.

---

## Getting Started

### 1. Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL 16+
- [DuckDB](https://duckdb.org/) (installed via Python requirements)

### 2. Environment Setup

**Python Dependencies:**
```bash
pip install -r ml-service/requirements.txt
```

**Node Dependencies:**
```bash
npm install
cd server && npm install
cd ..
```

**PostgreSQL Database:**
Ensure PostgreSQL is running locally, then initialize the schema:
```bash
createdb reliable_prediction
psql reliable_prediction -f db/schema.sql
```

Create a `.env` file in the project root:
```env
DATABASE_URL=postgresql://your_user@localhost:5432/reliable_prediction
PORT=3001
ML_SERVICE_URL=http://localhost:8000
```

---

## Running the Complete Framework

### Phase 1: Data Enrichment (DuckDB)
The original dataset must be enriched with time-series features. *Note: If `apmc_failure_aware_enriched.csv` already exists in `apmc_failure_aware_output/`, you can skip this.*

```bash
python apmc_failure_aware_output/enrich_apmc.py
```
This generates the enriched 5.4M row dataset using memory-efficient DuckDB queries.

### Phase 2: Experimental Pipeline & Evaluation
Run the chronological split training, risk estimation, and selective prediction pipeline. This outputs predictions to `failure_memory_schema.csv`.

```bash
python apmc_failure_aware_output/experiment_pipeline.py
```

### Phase 3: Ablation Study
To verify the performance of the various methods (Persistence vs XGBoost vs Selective Uncertainty), run the reproducible ablation study:

```bash
python apmc_failure_aware_output/ablation_study.py
```
*Results will be printed to the terminal and saved to `apmc_failure_aware_output/ablation_results.json`.*

### Phase 4: Populate the Application Database
To visualize the real test predictions and historical failure memory on the application dashboard, ingest the generated evaluation artifacts into PostgreSQL:

```bash
python populate_db.py
```

### Phase 5: Start the Dashboard
Launch the web application (starts both the frontend and the Express backend):

```bash
npm run dev
```
Navigate to `http://localhost:5173` to view the Failure-Aware Dashboard.

---

## Verification & Audits

Extensive audits and evaluation reports have been produced to verify the reproducibility of this research:
- `EVALUATION_AUDIT_REPORT.md` - Details the metric verification, identification of base model limitations, and evaluation logic.
- `FINAL_REPRODUCIBILITY_REPORT.md` - Confirms zero temporal leakage, fair comparison methodologies, and final validation of the research claims.
- `apmc_failure_aware_output/DATA_VALIDATION_REPORT.md` - Proves the temporal validity of the DuckDB generated features.