"""Ablation study execution framework.

This script runs the five experiment configurations:
A: Base Model
B: Base + Uncertainty
C: Base + Failure Memory
D: Base + Failure Memory + OOD
E: Full Framework (all components)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from training.features import FEATURES, add_features, normalize_columns


def calculate_selective_metrics(predictions: np.ndarray, actuals: np.ndarray, reliabilities: np.ndarray, threshold: float = 0.7) -> dict:
    """Calculate selective prediction metrics."""
    # Binary decision based on reliability
    accepted = reliabilities >= threshold
    
    # Coverage
    coverage = accepted.mean()
    
    if coverage == 0:
        return {
            "coverage": 0.0,
            "selective_mae": None,
            "selective_rmse": None,
            "selective_r2": None,
            "abstention_rate": 1.0
        }
    
    # Metrics on accepted predictions only
    accepted_preds = predictions[accepted]
    accepted_actuals = actuals[accepted]
    
    mae = mean_absolute_error(accepted_actuals, accepted_preds)
    rmse = np.sqrt(mean_squared_error(accepted_actuals, accepted_preds))
    r2 = r2_score(accepted_actuals, accepted_preds)
    
    return {
        "coverage": float(coverage),
        "selective_mae": float(mae),
        "selective_rmse": float(rmse),
        "selective_r2": float(r2),
        "abstention_rate": float(1 - coverage)
    }


def calculate_aurc(predictions: np.ndarray, actuals: np.ndarray, reliabilities: np.ndarray) -> float:
    """Calculate Area Under Risk-Coverage curve."""
    # Sort by reliability (descending)
    sorted_indices = np.argsort(reliabilities)[::-1]
    sorted_preds = predictions[sorted_indices]
    sorted_actuals = actuals[sorted_indices]
    
    n = len(predictions)
    if n == 0:
        return 0.0
    
    risks = []
    for i in range(1, n + 1):
        subset_preds = sorted_preds[:i]
        subset_actuals = sorted_actuals[:i]
        errors = np.abs(subset_actuals - subset_preds)
        risk = errors.mean()
        risks.append(risk)
    
    # Normalize coverage to [0, 1]
    coverages = np.linspace(0, 1, n)
    
    # Calculate AUC using trapezoidal rule
    aurc = np.trapz(risks, coverages)
    return float(aurc)


def run_experiment(
    config: str,
    data_path: str,
    commodity: str,
    market: str | None,
    horizon: int,
    model_dir: Path,
    database_url: str | None,
) -> dict:
    """Run a single experiment configuration."""
    print(f"\n{'='*60}")
    print(f"Running Experiment {config}")
    print(f"{'='*60}")
    
    # Load and prepare data
    chunks = []
    for chunk in pd.read_csv(data_path, chunksize=100_000, low_memory=False):
        normalized = normalize_columns(chunk)
        filtered = normalized[normalized["commodity"].str.casefold() == commodity.casefold()]
        if market:
            filtered = filtered[filtered["market"].str.casefold() == market.casefold()]
        if not filtered.empty:
            chunks.append(filtered)
    
    if not chunks:
        raise ValueError("No data matched the commodity/market filter.")
    
    df = pd.concat(chunks, ignore_index=True)
    df = add_features(df, horizon)
    df = df.sort_values("report_date")
    
    # Chronological split
    split = max(1, int(len(df) * 0.8))
    train, test = df.iloc[:split], df.iloc[split:]
    
    print(f"Training rows: {len(train)}")
    print(f"Test rows: {len(test)}")
    
    # Train base model
    model = XGBRegressor(n_estimators=250, max_depth=5, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, objective="reg:squarederror", random_state=42)
    model.fit(train[FEATURES], train["target"])
    
    # Get predictions
    base_predictions = model.predict(test[FEATURES])
    actuals = test["target"].values
    
    # Base metrics
    mae = float(mean_absolute_error(actuals, base_predictions))
    rmse = float(np.sqrt(mean_squared_error(actuals, base_predictions)))
    r2 = float(r2_score(actuals, base_predictions))
    
    print(f"Base MAE: {mae:.2f}")
    print(f"Base RMSE: {rmse:.2f}")
    print(f"Base R²: {r2:.4f}")
    
    # Calculate reliability based on configuration
    reliabilities = np.ones(len(base_predictions))  # Default: all accepted
    
    if config in ["B", "C", "D", "E"]:
        # Add model uncertainty
        residuals = actuals - base_predictions
        model_uncertainty = np.abs(residuals) / (np.mean(np.abs(actuals)) + 1e-9)
        reliabilities = 1 - model_uncertainty * 0.5
    
    if config in ["C", "D", "E"] and database_url:
        # Add historical failure risk
        try:
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) as total, 
                               SUM(CASE WHEN severity != 'NORMAL' THEN 1 ELSE 0 END) as failures
                        FROM failure_memory
                        WHERE commodity = %s
                    """, (commodity,))
                    row = cur.fetchone()
                    if row and row[0] > 0:
                        historical_risk = row[1] / row[0]
                        reliabilities *= (1 - historical_risk * 0.3)
        except Exception as e:
            print(f"Warning: Could not fetch historical failure rate: {e}")
    
    if config in ["D", "E"]:
        # Add novelty score
        feature_means = train[FEATURES].mean()
        feature_stds = train[FEATURES].std().replace(0, 1)
        
        novelty_scores = []
        for _, row in test.iterrows():
            values = row[FEATURES].values
            standardized = np.abs((values - feature_means) / feature_stds)
            novelty = np.mean(standardized) / 3.0
            novelty_scores.append(min(1.0, novelty))
        
        reliabilities *= (1 - np.array(novelty_scores) * 0.2)
    
    if config == "E":
        # Full framework: apply reliability threshold
        threshold = 0.7
        reliabilities = np.where(reliabilities >= threshold, reliabilities, 0)
    
    # Calculate selective metrics
    selective_metrics = calculate_selective_metrics(base_predictions, actuals, reliabilities)
    aurc = calculate_aurc(base_predictions, actuals, reliabilities)
    
    results = {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "coverage": selective_metrics["coverage"],
        "selective_mae": selective_metrics["selective_mae"],
        "selective_rmse": selective_metrics["selective_rmse"],
        "selective_r2": selective_metrics["selective_r2"],
        "abstention_rate": selective_metrics["abstention_rate"],
        "aurc": aurc,
        "test_rows": len(test),
        "train_rows": len(train)
    }
    
    print(f"\nExperiment {config} Results:")
    print(json.dumps(results, indent=2))
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Run ablation study experiments")
    parser.add_argument("--data", required=True, help="Path to APMC CSV")
    parser.add_argument("--commodity", default="Tomato", help="Commodity to forecast")
    parser.add_argument("--market", help="Market (optional)")
    parser.add_argument("--horizon", type=int, default=7, help="Forecast horizon")
    parser.add_argument("--model-dir", default="./ml-service/models", help="Model directory")
    parser.add_argument("--database-url", help="PostgreSQL connection string")
    parser.add_argument("--config", choices=["A", "B", "C", "D", "E", "ALL"], default="ALL", help="Experiment configuration")
    
    args = parser.parse_args()
    
    configs = ["A", "B", "C", "D", "E"] if args.config == "ALL" else [args.config]
    
    all_results = {}
    for config in configs:
        try:
            results = run_experiment(
                config=config,
                data_path=args.data,
                commodity=args.commodity,
                market=args.market,
                horizon=args.horizon,
                model_dir=Path(args.model_dir),
                database_url=args.database_url,
            )
            all_results[config] = results
        except Exception as e:
            print(f"Error running experiment {config}: {e}")
            all_results[config] = {"error": str(e)}
    
    # Save results
    output_path = Path(args.model_dir) / f"experiment_results_{args.commodity}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    output_path.write_text(json.dumps(all_results, indent=2))
    print(f"\nResults saved to {output_path}")
    
    # Print comparison table
    print(f"\n{'='*80}")
    print("EXPERIMENT COMPARISON")
    print(f"{'='*80}")
    print(f"{'Config':<8} {'MAE':<10} {'RMSE':<10} {'R²':<10} {'Coverage':<10} {'AURC':<10}")
    print(f"{'-'*80}")
    for config in ["A", "B", "C", "D", "E"]:
        if config in all_results and "error" not in all_results[config]:
            r = all_results[config]
            print(f"{config:<8} {r['mae']:<10.2f} {r['rmse']:<10.2f} {r['r2']:<10.4f} {r['coverage']:<10.2f} {r['aurc']:<10.4f}")
        else:
            print(f"{config:<8} {'ERROR':<10}")


if __name__ == "__main__":
    main()
