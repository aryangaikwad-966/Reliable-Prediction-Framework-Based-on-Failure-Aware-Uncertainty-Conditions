from __future__ import annotations

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg
from fastapi import FastAPI, HTTPException

from .core import Signals, novelty_score, selective_decision
from .schemas import PredictionRequest, TrainRequest

app = FastAPI(title="Reliable Prediction ML Service", version="1.0.0")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "./models"))
DATABASE_URL = os.getenv("DATABASE_URL")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "fastapi-ml", "model_dir": str(MODEL_DIR)}


@app.post("/predict")
def predict(request: PredictionRequest) -> dict:
    model_path = MODEL_DIR / "latest.joblib"
    if not model_path.exists():
        raise HTTPException(status_code=503, detail="No trained model is available. Run the training pipeline first.")
    artifact = joblib.load(model_path)
    feature_names = artifact["features"]
    values = [float(request.features.get(name, np.nan)) for name in feature_names]
    if any(np.isnan(values)):
        raise HTTPException(status_code=422, detail="Required model features are missing from the request.")
    base = float(artifact["model"].predict(np.array([values]))[0])
    means = artifact["feature_means"]
    scales = artifact["feature_scales"]
    novelty = novelty_score(values, means, scales)
    
    # Calculate historical failure risk from database if available
    historical_failure_risk = 0.0
    if DATABASE_URL:
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) as total, 
                               SUM(CASE WHEN severity != 'NORMAL' THEN 1 ELSE 0 END) as failures
                        FROM failure_memory
                        WHERE commodity = %s AND market = %s
                    """, (request.commodity, request.market))
                    row = cur.fetchone()
                    if row and row[0] > 0:
                        historical_failure_risk = row[1] / row[0]
        except Exception:
            # If database query fails, use default
            historical_failure_risk = 0.0
    
    signals = Signals(
        model_uncertainty=float(artifact.get("model_uncertainty", 0.25)),
        historical_failure_risk=float(historical_failure_risk),
        novelty_score=novelty,
        drift_score=float(artifact.get("drift_score", 0.0)),
        missing_information=0.0,
        context_risk=0.0,
    )
    return selective_decision(base, signals, float(os.getenv("RELIABILITY_THRESHOLD", "0.70")))


@app.post("/train")
def train(request: TrainRequest) -> dict:
    from training.train import train_model

    try:
        result = train_model(request.data_path, request.commodity, request.market, request.horizon, request.test_fraction, MODEL_DIR)
        return result
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/metadata")
def metadata() -> dict:
    return {"model_available": (MODEL_DIR / "latest.joblib").exists(), "model_dir": str(MODEL_DIR)}


@app.post("/features")
def get_features(request: PredictionRequest) -> dict:
    """Compute time-series features for a prediction request."""
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL is required for feature serving.")
    
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Query historical data for the commodity/market/variety
                cur.execute("""
                    SELECT report_date, modal_price, arrivals
                    FROM market_data
                    WHERE commodity = %s AND market = %s AND variety = %s
                    ORDER BY report_date DESC
                    LIMIT 100
                """, (request.commodity, request.market, request.variety))
                
                rows = cur.fetchall()
                if len(rows) < 30:
                    raise HTTPException(
                        status_code=422, 
                        detail=f"Insufficient historical data: {len(rows)} rows (need at least 30)"
                    )
                
                # Convert to DataFrame
                df = pd.DataFrame(rows, columns=["report_date", "modal_price", "arrivals"])
                df["report_date"] = pd.to_datetime(df["report_date"])
                df = df.sort_values("report_date").reset_index(drop=True)
                
                # Import feature engineering
                from training.features import FEATURES, add_features
                
                # Add features
                df_featured = add_features(df, request.horizon)
                
                # Get the most recent feature row
                latest_features = df_featured.iloc[-1]
                
                # Extract feature values
                feature_dict = {}
                for feat in FEATURES:
                    val = latest_features.get(feat)
                    if pd.isna(val):
                        feature_dict[feat] = 0.0
                    else:
                        feature_dict[feat] = float(val)
                
                return {
                    "features": feature_dict,
                    "rows_used": len(rows),
                    "latest_date": str(df["report_date"].iloc[-1].date())
                }
                
    except psycopg.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feature computation error: {str(e)}")