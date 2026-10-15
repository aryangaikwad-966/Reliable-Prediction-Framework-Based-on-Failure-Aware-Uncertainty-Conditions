from __future__ import annotations

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from .core import Signals, novelty_score, selective_decision
from .schemas import PredictionRequest, TrainRequest
from training.anomaly_detection import (
    ClimateAnomalyDetector,
    MarketDataAnomalyDetector,
    FeatureDistributionAnomalyDetector,
    AnomalyResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The Node service already reads the root .env.  Load the same non-secret
# configuration here so `npm run dev:ml` has the documented database and model
# settings without requiring callers to export them manually.
load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(title="Reliable Prediction ML Service", version="1.0.0")
configured_model_dir = Path(os.getenv("MODEL_DIR", "ml-service/models"))
MODEL_DIR = configured_model_dir if configured_model_dir.is_absolute() else (PROJECT_ROOT / configured_model_dir).resolve()
DATABASE_URL = os.getenv("DATABASE_URL")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "fastapi-ml",
        "model_dir": str(MODEL_DIR),
        "model_available": (MODEL_DIR / "latest.joblib").exists(),
        "database_configured": bool(DATABASE_URL),
    }


@app.post("/predict")
def predict(request: PredictionRequest) -> dict:
    model_path = MODEL_DIR / "latest.joblib"
    if not model_path.exists():
        raise HTTPException(status_code=503, detail="No trained model is available. Run the training pipeline first.")
    artifact = joblib.load(model_path)
    model_commodity = artifact.get("metadata", {}).get("commodity")
    if model_commodity and request.commodity != model_commodity:
        raise HTTPException(
            status_code=422,
            detail=f"The loaded model supports {model_commodity} only; {request.commodity} is out of scope.",
        )
    feature_names = artifact["features"]
    values = [float(request.features.get(name, np.nan)) for name in feature_names]
    if any(np.isnan(values)):
        raise HTTPException(status_code=422, detail="Required model features are missing from the request.")
    base = float(artifact["model"].predict(np.array([values]))[0])
    means = artifact["feature_means"]
    scales = artifact["feature_scales"]
    novelty = novelty_score(values, means, scales)
    
    # Calculate historical failure risk from database if available
    historical_failure_risk: float | None = None
    if DATABASE_URL:
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    # Evaluation imports preserve the source market code in
                    # failure_memory, whereas live requests use the market's
                    # display name.  Resolve the selected series back to its
                    # code and only retrieve outcomes available by its latest
                    # observation date, so later outcomes cannot leak into a
                    # historical as-of prediction.
                    cur.execute("""
                        SELECT COUNT(*) AS total,
                               SUM(CASE WHEN f.severity != 'NORMAL' THEN 1 ELSE 0 END) AS failures
                        FROM failure_memory f
                        WHERE f.commodity = %s
                          AND f.variety = %s
                          AND f.market IN (
                              SELECT DISTINCT md.market_code::text
                              FROM market_data md
                              WHERE md.commodity = %s
                                AND md.market = %s
                                AND md.variety = %s
                          )
                          AND f.event_date::date <= (
                              SELECT MAX(md.report_date)
                              FROM market_data md
                              WHERE md.commodity = %s
                                AND md.market = %s
                                AND md.variety = %s
                          )
                    """, (
                        request.commodity,
                        request.variety,
                        request.commodity,
                        request.market,
                        request.variety,
                        request.commodity,
                        request.market,
                        request.variety,
                    ))
                    row = cur.fetchone()
                    if row and row[0] > 0:
                        historical_failure_risk = row[1] / row[0]
        except Exception:
            # An unavailable history signal is not the same as zero risk.
            historical_failure_risk = None
    
    # Climate anomaly detection using ClimateAnomalyDetector
    climate_anomaly: float | None = None
    climate_anomaly_result = None
    climate_available = False
    
    # Check if climate features are provided in the request
    climate_values = {
        name: request.features.get(name)
        for name in ("temperature", "rainfall", "humidity")
    }
    climate_values_valid = all(value is not None and np.isfinite(value) for value in climate_values.values())
    climate_values_valid = climate_values_valid and climate_values["rainfall"] >= 0 and 0 <= climate_values["humidity"] <= 1
    climate_status = "evaluated" if climate_values_valid else (
        "not_evaluated" if all(value is None for value in climate_values.values()) else "invalid_or_incomplete"
    )

    if climate_values_valid:
        climate_available = True
        weather_data = {
            "temperature": climate_values["temperature"],
            "rainfall": climate_values["rainfall"],
            "humidity": climate_values["humidity"],
        }
        for name in ("wind_speed", "is_heatwave", "is_coldwave", "is_heavy_rain"):
            if request.features.get(name) is not None:
                weather_data[name] = request.features[name]
        climate_detector = ClimateAnomalyDetector()
        climate_anomaly_result = climate_detector.detect(weather_data)
        climate_anomaly = climate_anomaly_result.score
    
    # Market data anomaly detection using MarketDataAnomalyDetector
    market_data_anomaly: float | None = None
    market_data_anomaly_result = None
    
    # Extract market data from features
    modal_price = request.features.get("lag_1")  # Most recent price
    arrivals = request.features.get("arrival_lag_1")  # Most recent arrivals
    
    if modal_price is not None or arrivals is not None:
        market_data = {
            "modal_price": modal_price,
            "arrivals_tonnes": arrivals,
        }
        market_detector = MarketDataAnomalyDetector()
        market_data_anomaly_result = market_detector.detect(market_data, request.commodity)
        market_data_anomaly = market_data_anomaly_result.score
    
    signals = Signals(
        model_uncertainty=float(artifact.get("model_uncertainty", 0.25)),
        historical_failure_risk=historical_failure_risk,
        novelty_score=novelty,
        drift_score=float(artifact.get("drift_score", 0.0)),
        missing_information=0.0,
        context_risk=0.0,
        climate_anomaly=climate_anomaly,
        market_data_anomaly=market_data_anomaly,
    )
    
    decision = selective_decision(base, signals, float(os.getenv("RELIABILITY_THRESHOLD", "0.70")))
    
    # Add anomaly detection details to response
    decision["anomaly_detection"] = {
        "climate_available": climate_available,
        "climate_status": climate_status,
        "climate_anomaly": {
            "score": climate_anomaly,
            "severity": climate_anomaly_result.severity if climate_anomaly_result else None,
            "reason": climate_anomaly_result.reason if climate_anomaly_result else "Climate data not provided",
        } if climate_available else None,
        "market_data_status": "evaluated" if market_data_anomaly_result else "not_evaluated",
        "market_data_anomaly": {
            "score": market_data_anomaly,
            "severity": market_data_anomaly_result.severity if market_data_anomaly_result else None,
            "reason": market_data_anomaly_result.reason if market_data_anomaly_result else "Market data insufficient",
        } if market_data_anomaly_result else None,
    }
    
    return decision


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
                    SELECT report_date, market, commodity, variety, modal_price, arrivals,
                           temperature, rainfall, humidity, wind_speed,
                           is_heatwave, is_coldwave, is_heavy_rain
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
                df = pd.DataFrame(rows, columns=[
                    "report_date", "market", "commodity", "variety", "modal_price", "arrivals",
                    "temperature", "rainfall", "humidity", "wind_speed",
                    "is_heatwave", "is_coldwave", "is_heavy_rain",
                ])
                df["report_date"] = pd.to_datetime(df["report_date"])
                df = df.sort_values("report_date").reset_index(drop=True)
                
                # Import feature engineering. Climate columns are returned only
                # when they are present in the database row; never synthesize
                # missing climate observations as zeroes.
                from training.features import FEATURES_WITHOUT_CLIMATE, add_features
                
                # Add features
                df_featured = add_features(df, request.horizon, is_training=False)
                
                # Get the most recent feature row
                latest_features = df_featured.iloc[-1]
                
                # Extract feature values
                feature_dict = {}
                for feat in FEATURES_WITHOUT_CLIMATE:
                    val = latest_features.get(feat)
                    if pd.isna(val):
                        raise HTTPException(status_code=422, detail=f"Required market feature is unavailable: {feat}")
                    feature_dict[feat] = float(val)

                climate_columns = ("temperature", "rainfall", "humidity")
                if all(column in df.columns and pd.notna(latest_features.get(column)) for column in climate_columns):
                    for column in ("temperature", "rainfall", "humidity", "wind_speed", "is_heatwave", "is_coldwave", "is_heavy_rain"):
                        value = latest_features.get(column)
                        if column in df.columns and pd.notna(value):
                            feature_dict[column] = float(value)
                
                return {
                    "features": feature_dict,
                    "rows_used": len(rows),
                    "latest_date": str(df["report_date"].iloc[-1].date())
                }
                
    except HTTPException:
        raise
    except psycopg.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feature computation error: {str(e)}")
