import os
import json
import numpy as np
import pandas as pd
import duckdb
from datetime import datetime
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor
from scipy.spatial.distance import mahalanobis
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
CSV_PATH = OUT_DIR / "apmc_failure_aware_enriched.csv"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def smape(A, F):
    return 100/len(A) * np.sum(2 * np.abs(F - A) / (np.abs(A) + np.abs(F) + 1e-8))

def calculate_selective_metrics(predictions, actuals, reliabilities, threshold, unacceptable_error=300.0):
    accepted = reliabilities >= threshold
    coverage = accepted.mean()
    if coverage == 0:
        return {"coverage": 0.0, "mae": None, "rmse": None, "smape": None, "abstention_rate": 1.0, 
                "failure_detection_rate": 0.0, "false_acceptance_rate": 0.0, "accepted_count": 0}
    
    accepted_preds = predictions[accepted]
    accepted_actuals = actuals[accepted]
    mae = mean_absolute_error(accepted_actuals, accepted_preds)
    rmse = np.sqrt(mean_squared_error(accepted_actuals, accepted_preds))
    s_mape = smape(accepted_actuals, accepted_preds)
    
    # Failure detection metrics
    actual_errors = np.abs(predictions - actuals)
    is_failure = actual_errors > unacceptable_error
    is_abstained = ~accepted
    
    true_failures = np.sum(is_failure)
    detected_failures = np.sum(is_failure & is_abstained)
    failure_detection_rate = detected_failures / true_failures if true_failures > 0 else 0.0
    
    false_acceptances = np.sum(is_failure & accepted)
    accepted_total = np.sum(accepted)
    false_acceptance_rate = false_acceptances / accepted_total if accepted_total > 0 else 0.0
    
    return {
        "coverage": float(coverage),
        "mae": float(mae),
        "rmse": float(rmse),
        "smape": float(s_mape),
        "abstention_rate": float(1 - coverage),
        "failure_detection_rate": float(failure_detection_rate),
        "false_acceptance_rate": float(false_acceptance_rate),
        "accepted_count": int(accepted_total)
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
    # Using trapezoidal rule
    return float(np.trapz(risks, coverages))

def load_data():
    log("Loading dataset from enriched CSV via DuckDB...")
    con = duckdb.connect()
    
    query = """
    SELECT *
    FROM read_csv_auto('{csv_path}', sample_size=50000)
    WHERE commodity = 'Tomato' 
      AND price_unit = 'Rs/Quintal'
      AND quality_insufficient_history = false
      AND target_available_h7d = true
    ORDER BY report_date, market_code, variety
    """
    df = con.execute(query.format(csv_path=CSV_PATH)).fetchdf()
    con.close()
    
    df['report_date'] = pd.to_datetime(df['report_date'])
    df['target_date_h7d'] = pd.to_datetime(df['target_date_h7d'])
    
    # Fix VARCHAR lags by casting to float
    for col in df.columns:
        if col.startswith('feat_') and df[col].dtype == 'O':
            try:
                df[col] = df[col].astype(float)
            except:
                pass
                
    log(f"Loaded {len(df)} rows.")
    return df

def split_data(df):
    dates = np.sort(df['report_date'].unique())
    n_dates = len(dates)
    train_end = dates[int(n_dates * 0.6)]
    val_end = dates[int(n_dates * 0.8)]
    
    train_df = df[df['report_date'] < train_end].copy()
    val_df = df[(df['report_date'] >= train_end) & (df['report_date'] < val_end)].copy()
    test_df = df[df['report_date'] >= val_end].copy()
    
    log(f"Chronological Split: Train ({len(train_df)}), Val ({len(val_df)}), Test ({len(test_df)})")
    return train_df, val_df, test_df

def main():
    log("=== Phase 4: Independent Evaluation Audit and Ablation Study ===")
    df = load_data()
    train_df, val_df, test_df = split_data(df)
    
    features = [c for c in train_df.columns if c.startswith('feat_')] + ['modal_price', 'arrivals_tonnes']
    target = 'target_modal_price_h7d'
    
    log(f"Using {len(features)} features for XGBoost.")
    
    # DEFECT FIX: Trees cannot extrapolate non-stationary trends. 
    # We must predict the price change (target_diff) and reconstruct.
    train_df['target_diff'] = train_df[target] - train_df['modal_price']
    val_df['target_diff'] = val_df[target] - val_df['modal_price']
    test_df['target_diff'] = test_df[target] - test_df['modal_price']
    
    log("--- Method A: Persistence Baseline ---")
    test_actuals = test_df[target].values
    val_actuals = val_df[target].values
    
    test_persistence_preds = test_df['modal_price'].values
    val_persistence_preds = val_df['modal_price'].values
    
    a_mae = mean_absolute_error(test_actuals, test_persistence_preds)
    a_rmse = np.sqrt(mean_squared_error(test_actuals, test_persistence_preds))
    log(f"Method A (Persistence) - MAE: {a_mae:.2f}, RMSE: {a_rmse:.2f}")
    
    log("--- Method B: XGBoost Base (Differenced Target) ---")
    base_model = XGBRegressor(n_estimators=150, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=-1)
    base_model.fit(train_df[features], train_df['target_diff'])
    
    val_preds = val_df['modal_price'].values + base_model.predict(val_df[features])
    test_preds = test_df['modal_price'].values + base_model.predict(test_df[features])
    
    b_mae = mean_absolute_error(test_actuals, test_preds)
    b_rmse = np.sqrt(mean_squared_error(test_actuals, test_preds))
    log(f"Method B (XGBoost) - MAE: {b_mae:.2f}, RMSE: {b_rmse:.2f}")
    
    log("--- Method C: Uncertainty-based Abstention ---")
    train_dates = np.sort(train_df['report_date'].unique())
    train_split = train_dates[int(len(train_dates) * 0.7)]
    
    train1 = train_df[train_df['report_date'] < train_split].copy()
    train2 = train_df[train_df['report_date'] >= train_split].copy()
    
    tmp_model = XGBRegressor(n_estimators=150, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=-1)
    tmp_model.fit(train1[features], train1['target_diff'])
    
    train2_preds = train2['modal_price'].values + tmp_model.predict(train2[features])
    train2_residuals = np.abs(train2[target].values - train2_preds)
    
    uncertainty_model = XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, n_jobs=-1)
    uncertainty_model.fit(train2[features], train2_residuals)
    
    val_uncertainty = uncertainty_model.predict(val_df[features])
    test_uncertainty = uncertainty_model.predict(test_df[features])
    
    c_threshold_risk = np.percentile(val_uncertainty, 80)
    test_reliabilities_c = 1.0 - (np.clip(test_uncertainty, 0, np.max(val_uncertainty)) / np.max(val_uncertainty))
    c_rel_threshold = 1.0 - (c_threshold_risk / np.max(val_uncertainty))
    
    metrics_c = calculate_selective_metrics(test_preds, test_actuals, test_reliabilities_c, c_rel_threshold)
    log(f"Method C - Selective MAE: {metrics_c['mae']:.2f}, Coverage: {metrics_c['coverage']*100:.1f}%")
    
    log("--- Method D: Contextual Failure Memory ---")
    unacceptable_error = 300.0
    train2['failure'] = (train2_residuals > unacceptable_error).astype(int)
    market_failure_rates = train2.groupby('market_code')['failure'].mean().to_dict()
    global_failure_rate = train2['failure'].mean()
    
    def get_failure_risk(market_code):
        return market_failure_rates.get(market_code, global_failure_rate)
        
    val_failure_risk = np.array([get_failure_risk(m) for m in val_df['market_code']])
    test_failure_risk = np.array([get_failure_risk(m) for m in test_df['market_code']])
    
    d_threshold_risk = np.percentile(val_failure_risk, 80)
    test_reliabilities_d = 1.0 - test_failure_risk
    d_rel_threshold = 1.0 - d_threshold_risk
    
    metrics_d = calculate_selective_metrics(test_preds, test_actuals, test_reliabilities_d, d_rel_threshold)
    log(f"Method D - Selective MAE: {metrics_d['mae']:.2f}, Coverage: {metrics_d['coverage']*100:.1f}%")
    
    log("--- Method E: Combined Selective Prediction ---")
    train_means = train_df[features].mean()
    train_stds = train_df[features].std().replace(0, 1)
    
    def get_novelty(df_sub):
        norm = np.abs((df_sub[features] - train_means) / train_stds)
        return norm.mean(axis=1).values
        
    val_novelty = get_novelty(val_df)
    test_novelty = get_novelty(test_df)
    
    def normalize(val_arr, test_arr):
        v_max = np.max(val_arr) + 1e-6
        return np.clip(val_arr / v_max, 0, 1), np.clip(test_arr / v_max, 0, 1)
        
    val_unc_norm, test_unc_norm = normalize(val_uncertainty, test_uncertainty)
    val_nov_norm, test_nov_norm = normalize(val_novelty, test_novelty)
    val_fail_norm, test_fail_norm = normalize(val_failure_risk, test_failure_risk)
    
    val_combined_risk = 0.5 * val_unc_norm + 0.3 * val_fail_norm + 0.2 * val_nov_norm
    test_combined_risk = 0.5 * test_unc_norm + 0.3 * test_fail_norm + 0.2 * test_nov_norm
    
    e_threshold_risk = np.percentile(val_combined_risk, 80)
    test_reliabilities_e = 1.0 - test_combined_risk
    e_rel_threshold = 1.0 - e_threshold_risk
    
    metrics_e = calculate_selective_metrics(test_preds, test_actuals, test_reliabilities_e, e_rel_threshold)
    log(f"Method E - Selective MAE: {metrics_e['mae']:.2f}, Coverage: {metrics_e['coverage']*100:.1f}%")
    
    metrics_a_selective = calculate_selective_metrics(test_persistence_preds, test_actuals, test_reliabilities_e, e_rel_threshold)
    
    results = {
        "A_Persistence": {"mae": a_mae, "rmse": a_rmse},
        "B_XGBoost_Differenced": {"mae": b_mae, "rmse": b_rmse},
        "C_Uncertainty": metrics_c,
        "D_FailureMemory": metrics_d,
        "E_Combined": metrics_e,
        "A_Persistence_at_E_Coverage": metrics_a_selective,
        "AURC_E": calculate_aurc(test_preds, test_actuals, test_reliabilities_e),
        "Total_Test_Samples": len(test_df)
    }
    
    with open(OUT_DIR / "ablation_results.json", "w") as f:
        json.dump(results, f, indent=4)
        
    log("=== Results ===")
    print(json.dumps(results, indent=4))
    
if __name__ == "__main__":
    main()
