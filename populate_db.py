import os
import pandas as pd
import psycopg
import json
from datetime import datetime

DB_URL = os.getenv("DATABASE_URL", "postgresql://aryangaikwad@localhost:5432/reliable_prediction")
CSV_FILE = "apmc_failure_aware_output/failure_memory_schema.csv"

def populate():
    print(f"Connecting to DB: {DB_URL}")
    df = pd.read_csv(CSV_FILE)
    
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            print("Clearing existing data...")
            cur.execute("TRUNCATE TABLE failure_memory CASCADE;")
            cur.execute("TRUNCATE TABLE prediction_outcomes CASCADE;")
            cur.execute("TRUNCATE TABLE uncertainty_assessments CASCADE;")
            cur.execute("TRUNCATE TABLE predictions CASCADE;")
            
            print("Inserting predictions...")
            for _, row in df.iterrows():
                # Parse series_id (market_code_commodity_variety_price_unit)
                # Wait, the series_id in the script was f"{row['market_code']}_{row['commodity']}_{row['variety']}_{row['price_unit']}"
                parts = row['series_id'].split('_')
                market = parts[0]
                commodity = parts[1]
                variety = parts[2]
                
                ctx = json.loads(row['prediction_context'])
                decision = "ACCEPTED" if ctx["decision"] == "PREDICT" else "ABSTAINED"
                
                signals = {
                    "model_uncertainty": float(row['prediction_uncertainty']),
                    "historical_failure_risk": 0.0,
                    "novelty_score": 0.0,
                    "drift_score": 0.0,
                    "missing_information": 0.0,
                    "context_risk": 0.0
                }
                
                failure_risk = min(1.0, max(0.0, float(row['prediction_uncertainty']) / 3000.0))
                reliability = 1.0 - failure_risk
                
                # Insert prediction
                cur.execute("""
                    INSERT INTO predictions (id, commodity, market, variety, horizon, prediction, base_prediction, reliability, failure_risk, decision, is_demo, signals, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row['prediction_id'], commodity, market, variety, 7,
                    row['predicted_price'] if decision == 'ACCEPTED' else None,
                    row['predicted_price'],
                    reliability,
                    failure_risk, 
                    decision, False, json.dumps(signals), row['prediction_origin_date']
                ))
                
                # Insert outcome
                cur.execute("""
                    INSERT INTO prediction_outcomes (prediction_id, actual, observed_at)
                    VALUES (%s, %s, %s)
                """, (
                    row['prediction_id'], row['actual_price'], row['outcome_observed_at']
                ))
                
                severity = row['failure_severity']
                if severity == 'WARNING': severity = 'MODERATE'
                if severity == 'CRITICAL': severity = 'HIGH'
                
                # Insert failure memory
                cur.execute("""
                    INSERT INTO failure_memory (id, prediction_id, event_date, commodity, market, variety, prediction, actual, absolute_error, relative_error, failure_threshold, severity, reliability, context)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row['failure_record_id'], row['prediction_id'], row['target_date'],
                    commodity, market, variety, row['predicted_price'], row['actual_price'],
                    row['absolute_error'], row['relative_error'], row['unacceptable_error_threshold'],
                    severity,
                    reliability, json.dumps(ctx)
                ))
                
            conn.commit()
            print(f"Successfully inserted {len(df)} records into the database.")

if __name__ == "__main__":
    populate()
