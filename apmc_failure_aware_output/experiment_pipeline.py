import os
import json
import uuid
import numpy as np
import pandas as pd
import duckdb
from datetime import datetime, timezone
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
CSV_PATH = OUT_DIR / "apmc_failure_aware_enriched.csv"
MEMORY_CSV = OUT_DIR / "failure_memory_schema.csv"
RESULTS_FILE = OUT_DIR / "evaluation_results.json"

# Unacceptable error threshold (e.g., 20% relative error or 300 Rs/Quintal)
# We will use an absolute error threshold of 300 Rs/Quintal for this experiment
UNACCEPTABLE_ERROR_THRESHOLD = 300.0

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def calculate_selective_metrics(predictions, actuals, reliabilities, threshold):
    accepted = reliabilities >= threshold
    coverage = accepted.mean()
    if coverage == 0:
        return {"coverage": 0.0, "selective_mae": None, "selective_rmse": None, "abstention_rate": 1.0}
    
    accepted_preds = predictions[accepted]
    accepted_actuals = actuals[accepted]
    mae = mean_absolute_error(accepted_actuals, accepted_preds)
    rmse = np.sqrt(mean_squared_error(accepted_actuals, accepted_preds))
    
    return {
        "coverage": float(coverage),
        "selective_mae": float(mae),
        "selective_rmse": float(rmse),
        "abstention_rate": float(1 - coverage)
    }

def calculate_aurc(predictions, actuals, reliabilities):
    sorted_indices = np.argsort(reliabilities)[::-1]
    sorted_preds = predictions[sorted_indices]
    sorted_actuals = actuals[sorted_indices]
    n = len(predictions)
    if n == 0: return 0.0
    
    risks = []
    for i in range(1, n + 1):
        subset_preds = sorted_preds[:i]
        subset_actuals = sorted_actuals[:i]
        errors = np.abs(subset_actuals - subset_preds)
        risks.append(errors.mean())
        
    coverages = np.linspace(0, 1, n)
    return float(np.trapz(risks, coverages))

def load_data():
    log("Loading Tomato dataset from enriched CSV via DuckDB...")
    con = duckdb.connect()
    
    # We must explicitly cast some lag columns to DOUBLE because they might have been read as VARCHAR
    query = """
    SELECT 
        report_date, market_code, commodity, variety, price_unit, modal_price, target_date_h7d,
        CAST(feat_price_lag_1d AS DOUBLE) as feat_price_lag_1d,
        CAST(feat_price_lag_3d AS DOUBLE) as feat_price_lag_3d,
        CAST(feat_price_lag_7d AS DOUBLE) as feat_price_lag_7d,
        CAST(feat_price_lag_14d AS DOUBLE) as feat_price_lag_14d,
        CAST(feat_price_lag_28d AS DOUBLE) as feat_price_lag_28d,
        feat_price_mean_7d, feat_price_mean_14d, feat_price_mean_28d,
        feat_price_std_7d, feat_price_std_14d,
        feat_price_min_7d, feat_price_max_7d, feat_price_min_14d, feat_price_max_14d, feat_price_median_14d,
        feat_price_change_1d, 
        CAST(feat_price_change_7d AS DOUBLE) as feat_price_change_7d,
        feat_price_volatility_7d, feat_price_volatility_14d,
        feat_price_trend_7d, feat_price_trend_14d,
        feat_days_since_previous_observation, feat_price_history_count,
        feat_day_of_week, feat_day_of_month, feat_month, feat_quarter, feat_day_of_year, feat_is_weekend,
        feat_arrival_lag_1d, 
        CAST(feat_arrival_lag_7d AS DOUBLE) as feat_arrival_lag_7d,
        feat_arrival_mean_7d, feat_arrival_mean_14d, feat_arrival_std_7d, feat_arrival_history_count,
        feat_arrival_change_1d, 
        CAST(feat_arrival_change_7d AS DOUBLE) as feat_arrival_change_7d,
        target_modal_price_h7d
    FROM read_csv_auto('{csv_path}', sample_size=50000)
    WHERE commodity = 'Tomato' 
      AND price_unit = 'Rs/Quintal'
      AND quality_insufficient_history = false
      AND target_available_h7d = true
    ORDER BY report_date, market_code, variety
    """
    df = con.execute(query.format(csv_path=CSV_PATH)).fetchdf()
    con.close()
    
    # Cast report_date to datetime
    df['report_date'] = pd.to_datetime(df['report_date'])
    df['target_date_h7d'] = pd.to_datetime(df['target_date_h7d'])
    
    log(f"Loaded {len(df)} rows.")
    return df

def split_data(df):
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

def main():
    log("=== Phase 2 & 3: Baseline and Selective Prediction ===")
    df = load_data()
    train_df, val_df, test_df = split_data(df)
    
    features = [c for c in train_df.columns if c.startswith('feat_')]
    target = 'target_modal_price_h7d'
    
    log("Training Baseline XGBoost Model...")
    # XGBRegressor handles NaNs automatically
    base_model = XGBRegressor(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42, n_jobs=-1)
    base_model.fit(train_df[features], train_df[target])
    
    # Evaluate Baseline on Val and Test
    val_preds = base_model.predict(val_df[features])
    test_preds = base_model.predict(test_df[features])
    
    val_mae = mean_absolute_error(val_df[target], val_preds)
    test_mae = mean_absolute_error(test_df[target], test_preds)
    log(f"Baseline MAE: Val={val_mae:.2f}, Test={test_mae:.2f}")
    
    # Simple persistence baseline for comparison
    val_persistence = val_df['feat_price_lag_1d'].fillna(val_df['modal_price'])
    test_persistence = test_df['feat_price_lag_1d'].fillna(test_df['modal_price'])
    val_persist_mae = mean_absolute_error(val_df[target], val_persistence)
    test_persist_mae = mean_absolute_error(test_df[target], test_persistence)
    log(f"Persistence (lag_1d) MAE: Val={val_persist_mae:.2f}, Test={test_persist_mae:.2f}")
    
    log("Training Failure Risk Estimator...")
    # We'll use out-of-sample predictions on Train to train the risk estimator
    # For simplicity, we split Train into TrainA and TrainB
    dates_train = np.sort(train_df['report_date'].unique())
    split_idx = int(len(dates_train) * 0.7)
    train_a_dates = dates_train[:split_idx]
    train_b_dates = dates_train[split_idx:]
    
    train_a = train_df[train_df['report_date'].isin(train_a_dates)]
    train_b = train_df[train_df['report_date'].isin(train_b_dates)]
    
    # Fit temporary model on TrainA, predict on TrainB to get out-of-sample residuals
    tmp_model = XGBRegressor(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42, n_jobs=-1)
    tmp_model.fit(train_a[features], train_a[target])
    
    train_b_preds = tmp_model.predict(train_b[features])
    # The target for risk estimator is absolute error
    train_b_error = np.abs(train_b[target] - train_b_preds)
    
    # Risk estimator takes base features and predicts absolute error
    risk_model = XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, n_jobs=-1)
    risk_model.fit(train_b[features], train_b_error)
    
    log("Tuning Abstention Threshold on Validation Set...")
    # We want to select a threshold on predicted risk (expected error) to abstain.
    # Our unacceptable error threshold is 300. So if predicted error > some threshold, we abstain.
    # We tune this threshold on Validation to maximize coverage while keeping Selective MAE < some target, 
    # or just use the model's calibrated prediction. Let's use predicted risk > 250 as abstain threshold.
    
    val_risk_preds = risk_model.predict(val_df[features])
    
    # Let's search for a threshold on Val that gives 80% coverage
    thresholds = np.percentile(val_risk_preds, np.linspace(0, 100, 100))
    best_threshold = np.percentile(val_risk_preds, 80) # abstain on top 20% riskiest
    
    log(f"Selected Risk Threshold on Val (80th percentile risk): {best_threshold:.2f}")
    
    # Calculate Reliabilities (inverse of predicted risk)
    # Higher reliability = lower predicted risk
    # We normalize reliability to 0-1 for AURC calculation
    max_risk = np.max(val_risk_preds)
    val_reliabilities = 1.0 - (np.clip(val_risk_preds, 0, max_risk) / max_risk)
    test_risk_preds = risk_model.predict(test_df[features])
    test_reliabilities = 1.0 - (np.clip(test_risk_preds, 0, max_risk) / max_risk)
    
    rel_threshold = 1.0 - (best_threshold / max_risk)
    
    log("Evaluating Selective Prediction on Test Set...")
    metrics_base = calculate_selective_metrics(test_preds, test_df[target].values, test_reliabilities, -1.0)
    metrics_selective = calculate_selective_metrics(test_preds, test_df[target].values, test_reliabilities, rel_threshold)
    aurc = calculate_aurc(test_preds, test_df[target].values, test_reliabilities)
    
    log(f"Test Base MAE: {metrics_base['selective_mae']:.2f}")
    log(f"Test Selective MAE: {metrics_selective['selective_mae']:.2f} (Coverage: {metrics_selective['coverage']*100:.1f}%)")
    log(f"Test AURC: {aurc:.2f}")
    
    results = {
        "Base_MAE": metrics_base["selective_mae"],
        "Selective_MAE": metrics_selective["selective_mae"],
        "Coverage": metrics_selective["coverage"],
        "Abstention_Rate": metrics_selective["abstention_rate"],
        "AURC": aurc,
        "Risk_Threshold": float(best_threshold)
    }
    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=4)
        
    log("=== Populating Failure Memory ===")
    # Simulate the real-time application recording
    # We will log the predictions and their outcomes for the test set
    
    # Prepare failure memory records
    records = []
    
    for i in range(len(test_df)):
        row = test_df.iloc[i]
        pred_price = test_preds[i]
        pred_risk = test_risk_preds[i]
        actual_price = row[target]
        
        # Application Logic
        if pred_risk > best_threshold:
            decision = "ABSTAIN"
            final_prediction = None
        else:
            decision = "PREDICT"
            final_prediction = pred_price
            
        abs_err = abs(pred_price - actual_price)
        rel_err = abs_err / actual_price if actual_price > 0 else 0
        failure_flag = abs_err > UNACCEPTABLE_ERROR_THRESHOLD
        
        # Populate context as json string
        context = {
            "market_code": int(row['market_code']),
            "commodity": str(row['commodity']),
            "feat_price_lag_1d": float(row['feat_price_lag_1d']) if pd.notna(row['feat_price_lag_1d']) else None,
            "decision": decision
        }
        
        records.append({
            "failure_record_id": str(uuid.uuid4()),
            "prediction_id": f"pred_{i}",
            "series_id": f"{row['market_code']}_{row['commodity']}_{row['variety']}_{row['price_unit']}",
            "prediction_origin_date": row['report_date'].strftime('%Y-%m-%d'),
            "target_date": row['target_date_h7d'].strftime('%Y-%m-%d'),
            "model_version": "v1.0.0-xgb",
            "predicted_price": pred_price,
            "actual_price": actual_price,
            "absolute_error": abs_err,
            "relative_error": rel_err,
            "unacceptable_error_threshold": UNACCEPTABLE_ERROR_THRESHOLD,
            "failure_flag": failure_flag,
            "prediction_uncertainty": pred_risk,
            "prediction_context": json.dumps(context),
            "failure_severity": "CRITICAL" if abs_err > (UNACCEPTABLE_ERROR_THRESHOLD * 2) else ("WARNING" if failure_flag else "NORMAL"),
            "outcome_observed_at": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        })
    
    mem_df = pd.DataFrame(records)
    mem_df.to_csv(MEMORY_CSV, index=False)
    log(f"Successfully populated {len(mem_df)} real evaluation records into failure memory.")
    
    failures = mem_df['failure_flag'].sum()
    log(f"Failure Analysis: {failures} failures detected out of {len(mem_df)} predictions ({failures/len(mem_df)*100:.1f}%).")
    
if __name__ == "__main__":
    main()
