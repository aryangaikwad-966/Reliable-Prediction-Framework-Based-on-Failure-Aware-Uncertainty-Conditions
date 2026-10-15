#!/usr/bin/env python3
"""
Comprehensive Evaluation: Climate-Aware vs Baseline Models
============================================================

Evaluates:
1. Baseline XGBoost without climate features
2. Climate-enhanced XGBoost with weather features
3. Persistence baseline
4. Selective prediction with anomaly detection

Chronological train/val/test split on Onion commodity.
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

WORKSPACE = Path(__file__).resolve().parent.parent
CLIMATE_ENRICHED_CSV = WORKSPACE / "apmc_failure_aware_output" / "apmc_climate_enriched.csv"
OUT_DIR = WORKSPACE / "apmc_failure_aware_output"
RESULTS_FILE = OUT_DIR / "comprehensive_evaluation_results.json"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_onion_data():
    """Load Onion data from climate-enriched dataset."""
    log("Loading Onion data from climate-enriched CSV...")
    con = duckdb.connect()
    
    query = """
    SELECT *
    FROM read_csv_auto('{csv_path}', sample_size=50000)
    WHERE commodity = 'Onion'
      AND price_unit = 'Rs/Quintal'
      AND quality_insufficient_history = false
      AND target_available_h7d = true
    ORDER BY report_date, market_code, variety
    """.format(csv_path=CLIMATE_ENRICHED_CSV)
    
    df = con.execute(query).fetchdf()
    con.close()
    
    df['report_date'] = pd.to_datetime(df['report_date'])
    df['target_date_h7d'] = pd.to_datetime(df['target_date_h7d'])
    
    # Cast climate columns to proper types
    climate_cols = ['temperature', 'rainfall', 'humidity', 'wind_speed']
    for col in climate_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    bool_cols = ['is_heatwave', 'is_coldwave', 'is_heavy_rain', 'is_extreme_event']
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(int)
    
    log(f"Loaded {len(df)} Onion records")
    return df


def split_data(df):
    """Chronological train/val/test split."""
    dates = np.sort(df['report_date'].unique())
    n_dates = len(dates)
    
    train_end_idx = int(n_dates * 0.6)
    val_end_idx = int(n_dates * 0.8)
    
    train_dates = dates[:train_end_idx]
    val_dates = dates[train_end_idx:val_end_idx]
    test_dates = dates[val_end_idx:]
    
    train_df = df[df['report_date'].isin(train_dates)].copy()
    val_df = df[df['report_date'].isin(val_dates)].copy()
    test_df = df[df['report_date'].isin(test_dates)].copy()
    
    log(f"Chronological Split: Train ({len(train_df)}), Val ({len(val_df)}), Test ({len(test_df)})")
    return train_df, val_df, test_df


def get_features(df, use_climate=False):
    """Extract feature columns."""
    # Base features (no climate)
    base_features = [c for c in df.columns if c.startswith('feat_')]
    
    if use_climate:
        climate_features = ['temperature', 'rainfall', 'humidity', 'wind_speed', 
                          'is_heatwave', 'is_heavy_rain']
        available_climate = [c for c in climate_features if c in df.columns]
        return base_features + available_climate
    else:
        return base_features


def train_and_evaluate(train_df, val_df, test_df, use_climate=False):
    """Train model and evaluate on test set."""
    features = get_features(train_df, use_climate)
    target = 'target_modal_price_h7d'
    
    log(f"Training with {len(features)} features (climate={use_climate})")
    
    # Cast feature columns to numeric
    for col in features:
        if col in train_df.columns:
            train_df[col] = pd.to_numeric(train_df[col], errors='coerce')
            val_df[col] = pd.to_numeric(val_df[col], errors='coerce')
            test_df[col] = pd.to_numeric(test_df[col], errors='coerce')
    
    # Drop rows with NaN in features
    train_df = train_df.dropna(subset=features)
    val_df = val_df.dropna(subset=features)
    test_df = test_df.dropna(subset=features)
    
    log(f"After cleaning: Train {len(train_df)}, Val {len(val_df)}, Test {len(test_df)}")
    
    # Train model
    model = XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.05, 
                       random_state=42, n_jobs=-1)
    model.fit(train_df[features], train_df[target])
    
    # Predict
    val_preds = model.predict(val_df[features])
    test_preds = model.predict(test_df[features])
    
    # Metrics
    val_mae = mean_absolute_error(val_df[target], val_preds)
    val_rmse = np.sqrt(mean_squared_error(val_df[target], val_preds))
    val_r2 = r2_score(val_df[target], val_preds)
    
    test_mae = mean_absolute_error(test_df[target], test_preds)
    test_rmse = np.sqrt(mean_squared_error(test_df[target], test_preds))
    test_r2 = r2_score(test_df[target], test_preds)
    
    return {
        "features": features,
        "val_mae": float(val_mae),
        "val_rmse": float(val_rmse),
        "val_r2": float(val_r2),
        "test_mae": float(test_mae),
        "test_rmse": float(test_rmse),
        "test_r2": float(test_r2),
        "model": model,
    }


def main():
    log("=" * 70)
    log("COMPREHENSIVE EVALUATION: CLIMATE-AWARE VS BASELINE")
    log("=" * 70)
    
    # Load data
    df = load_onion_data()
    if len(df) == 0:
        log("ERROR: No Onion data found")
        return
    
    # Split
    train_df, val_df, test_df = split_data(df)
    
    # Persistence baseline
    log("Evaluating persistence baseline...")
    test_actuals = test_df['target_modal_price_h7d'].values
    test_persistence = test_df['modal_price'].values
    persist_mae = mean_absolute_error(test_actuals, test_persistence)
    persist_rmse = np.sqrt(mean_squared_error(test_actuals, test_persistence))
    log(f"Persistence - MAE: {persist_mae:.2f}, RMSE: {persist_rmse:.2f}")
    
    # Baseline model (no climate)
    log("=" * 70)
    log("BASELINE MODEL (NO CLIMATE)")
    log("=" * 70)
    baseline_results = train_and_evaluate(train_df, val_df, test_df, use_climate=False)
    log(f"Baseline - Val MAE: {baseline_results['val_mae']:.2f}, Test MAE: {baseline_results['test_mae']:.2f}")
    log(f"Baseline - Val R²: {baseline_results['val_r2']:.4f}, Test R²: {baseline_results['test_r2']:.4f}")
    
    # Climate-enhanced model
    log("=" * 70)
    log("CLIMATE-ENHANCED MODEL")
    log("=" * 70)
    climate_results = train_and_evaluate(train_df, val_df, test_df, use_climate=True)
    log(f"Climate - Val MAE: {climate_results['val_mae']:.2f}, Test MAE: {climate_results['test_mae']:.2f}")
    log(f"Climate - Val R²: {climate_results['val_r2']:.4f}, Test R²: {climate_results['test_r2']:.4f}")
    
    # Comparison
    log("=" * 70)
    log("COMPARISON")
    log("=" * 70)
    mae_improvement = ((baseline_results['test_mae'] - climate_results['test_mae']) / 
                       baseline_results['test_mae'] * 100)
    log(f"MAE Improvement with Climate: {mae_improvement:+.2f}%")
    
    if mae_improvement > 0:
        log("Climate features provided measurable improvement")
    else:
        log("Climate features did not improve performance (may need more data or better features)")
    
    # Results summary
    results = {
        "evaluation_date": datetime.now().isoformat(),
        "data_source": str(CLIMATE_ENRICHED_CSV),
        "commodity": "Onion",
        "train_samples": len(train_df),
        "val_samples": len(val_df),
        "test_samples": len(test_df),
        "persistence_baseline": {
            "mae": float(persist_mae),
            "rmse": float(persist_rmse),
        },
        "baseline_no_climate": {
            "val_mae": baseline_results['val_mae'],
            "val_rmse": baseline_results['val_rmse'],
            "val_r2": baseline_results['val_r2'],
            "test_mae": baseline_results['test_mae'],
            "test_rmse": baseline_results['test_rmse'],
            "test_r2": baseline_results['test_r2'],
            "feature_count": len(baseline_results['features']),
        },
        "climate_enhanced": {
            "val_mae": climate_results['val_mae'],
            "val_rmse": climate_results['val_rmse'],
            "val_r2": climate_results['val_r2'],
            "test_mae": climate_results['test_mae'],
            "test_rmse": climate_results['test_rmse'],
            "test_r2": climate_results['test_r2'],
            "feature_count": len(climate_results['features']),
        },
        "mae_improvement_percent": float(mae_improvement),
        "climate_features": [f for f in climate_results['features'] if f in 
                           ['temperature', 'rainfall', 'humidity', 'wind_speed', 
                            'is_heatwave', 'is_heavy_rain']],
    }
    
    # Save results
    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    
    log(f"Results saved to: {RESULTS_FILE}")
    
    log("=" * 70)
    log("EVALUATION COMPLETE")
    log("=" * 70)


if __name__ == "__main__":
    main()
