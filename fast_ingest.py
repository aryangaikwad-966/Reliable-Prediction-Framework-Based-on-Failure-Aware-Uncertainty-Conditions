#!/usr/bin/env python3
"""Fast APMC+climate ingest using DuckDB to aggregate then COPY into PostgreSQL."""
import os
import duckdb
import psycopg
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
SRC_CSV = WORKSPACE / "apmc_failure_aware_output" / "apmc_climate_enriched.csv"
DB_URL = os.getenv("DATABASE_URL", "postgresql://aryangaikwad@localhost:5432/reliable_prediction")

CLIMATE_NUMERIC = ("temperature", "rainfall", "humidity", "wind_speed")
CLIMATE_BOOLEAN = ("is_heatwave", "is_coldwave", "is_heavy_rain", "is_extreme_event")

NATURAL_KEY = ("report_date", "market", "commodity", "variety")

def main():
    print(f"Source: {SRC_CSV}")
    print(f"DB: {DB_URL}")

    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")

    # Read CSV, normalize column names
    print("Loading CSV into DuckDB...")
    con.execute(f"""
        CREATE TABLE raw AS
        SELECT * FROM read_csv_auto('{SRC_CSV}', sample_size=50000, all_varchar=false)
    """)
    raw_count = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    print(f"  Raw rows: {raw_count:,}")

    # Normalize column names: market_center -> market
    print("Normalizing columns...")
    cols = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
    print(f"  Columns: {cols}")

    # Build the aggregation query
    # market_center -> market, district_name -> district, state_name -> state
    has_market = "market" in cols
    has_market_center = "market_center" in cols
    market_col = "market" if has_market else "market_center"

    # Build SELECT list
    select_parts = [
        "report_date",
        f"{market_col} AS market",
        "commodity",
        "variety",
        "market_code",
    ]

    # Aggregations
    select_parts.append("AVG(arrivals_tonnes) AS arrivals")
    select_parts.append("AVG(min_price) AS min_price")
    select_parts.append("AVG(max_price) AS max_price")
    select_parts.append("AVG(modal_price) AS modal_price")

    for col in CLIMATE_NUMERIC:
        if col in cols:
            select_parts.append(f"AVG({col}) AS {col}")
        else:
            select_parts.append(f"NULL::DOUBLE AS {col}")

    for col in CLIMATE_BOOLEAN:
        if col in cols:
            select_parts.append(f"BOOL_OR({col}) AS {col}")
        else:
            select_parts.append(f"false AS {col}")

    select_str = ", ".join(select_parts)

    print("Aggregating by natural key...")
    con.execute(f"""
        CREATE TABLE agg AS
        SELECT {select_str}
        FROM raw
        GROUP BY report_date, {market_col}, commodity, variety, market_code
    """)
    agg_count = con.execute("SELECT count(*) FROM agg").fetchone()[0]
    print(f"  Aggregated rows: {agg_count:,}")

    # Export to temp CSV
    tmp_csv = WORKSPACE / "tmp_ingest.csv"
    print(f"Exporting to {tmp_csv}...")
    con.execute(f"COPY (SELECT * FROM agg ORDER BY report_date, market, commodity, variety) TO '{tmp_csv}' (HEADER, DELIMITER ',')")
    con.close()

    # Bulk load into PostgreSQL using psql \copy (reads from file)
    print("Loading into PostgreSQL via psql COPY...")
    import subprocess
    import os as os_module
    
    # Truncate first
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE market_data")
            conn.commit()
            print("  Truncated market_data")

    # Use psql \copy for reliable bulk load from file
    env = os_module.environ.copy()
    env["PGHOST"] = "localhost"
    env["PGUSER"] = "aryangaikwad"
    env["PGDATABASE"] = "reliable_prediction"
    
    copy_cmd = f"\\copy market_data (report_date, market, commodity, variety, market_code, arrivals, min_price, max_price, modal_price, temperature, rainfall, humidity, wind_speed, is_heatwave, is_coldwave, is_heavy_rain, is_extreme_event) FROM '{tmp_csv}' WITH (FORMAT csv, HEADER true)"
    
    result = subprocess.run(
        ["psql", "-h", "localhost", "-U", "aryangaikwad", "-d", "reliable_prediction", "-c", copy_cmd],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"psql COPY error: {result.stderr}")
        raise SystemExit(1)
    print(f"  psql output: {result.stdout.strip()}")
    print(f"  Expected {agg_count:,} rows loaded")

    # Verify
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), min(report_date), max(report_date) FROM market_data")
            count, min_d, max_d = cur.fetchone()
            cur.execute("SELECT count(*) FROM market_data WHERE temperature IS NOT NULL")
            climate_count = cur.fetchone()[0]
            print(f"\nVerification:")
            print(f"  Total rows: {count:,}")
            print(f"  Date range: {min_d} to {max_d}")
            print(f"  Climate rows: {climate_count:,}")

    # Cleanup
    tmp_csv.unlink()
    print("\nDone!")

if __name__ == "__main__":
    main()