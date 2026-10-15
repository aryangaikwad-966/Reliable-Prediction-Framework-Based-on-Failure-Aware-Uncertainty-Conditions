#!/usr/bin/env python3
"""
APMC + Climate Data Integration Script
========================================

Joins the enriched APMC dataset with climate data to create a climate-enhanced
dataset for training and evaluation.

Usage:
    python3 enrich_with_climate.py
"""

from __future__ import annotations

import duckdb
import pandas as pd
from pathlib import Path
import time

WORKSPACE = Path(__file__).resolve().parent.parent
APMC_CSV = WORKSPACE / "apmc_failure_aware_output" / "apmc_failure_aware_enriched.csv"
CLIMATE_CSV = WORKSPACE / "apmc_failure_aware_output" / "apmc_climate_data.csv"
OUT_CSV = WORKSPACE / "apmc_failure_aware_output" / "apmc_climate_enriched.csv"


def main():
    print("=" * 70)
    print("APMC + CLIMATE DATA INTEGRATION")
    print("=" * 70)
    print(f"APMC Enriched: {APMC_CSV}")
    print(f"Climate Data: {CLIMATE_CSV}")
    print(f"Output: {OUT_CSV}")
    print()

    if not APMC_CSV.exists():
        raise SystemExit(f"ERROR: APMC enriched CSV not found at {APMC_CSV}")
    if not CLIMATE_CSV.exists():
        raise SystemExit(f"ERROR: Climate CSV not found at {CLIMATE_CSV}")

    con = duckdb.connect()

    # Load both datasets
    print("Loading APMC enriched data...")
    con.execute(f"""
        CREATE TABLE apmc AS
        SELECT * FROM read_csv_auto('{APMC_CSV}', sample_size=50000)
    """)
    apmc_count = con.execute("SELECT COUNT(*) FROM apmc").fetchone()[0]
    print(f"  APMC rows: {apmc_count:,}")

    print("Loading climate data...")
    con.execute(f"""
        CREATE TABLE climate AS
        SELECT * FROM read_csv_auto('{CLIMATE_CSV}', sample_size=50000)
    """)
    climate_count = con.execute("SELECT COUNT(*) FROM climate").fetchone()[0]
    print(f"  Climate rows: {climate_count:,}")

    # Join on market_code and date
    print("Joining APMC with climate data...")
    t0 = time.time()
    
    join_sql = """
    CREATE TABLE enriched_with_climate AS
    SELECT 
        a.*,
        c.temperature,
        c.rainfall,
        c.humidity,
        c.wind_speed,
        c.is_heatwave,
        c.is_coldwave,
        c.is_heavy_rain,
        c.is_extreme_event
    FROM apmc a
    LEFT JOIN climate c
        ON a.market_code = c.market_code
        AND a.report_date = c.date
    """
    
    con.execute(join_sql)
    elapsed = time.time() - t0
    print(f"  Join completed in {elapsed:.1f}s")

    # Check match statistics
    stats = con.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(temperature) as climate_matched,
            COUNT(*) - COUNT(temperature) as climate_unmatched
        FROM enriched_with_climate
    """).fetchone()
    
    print(f"  Total rows: {stats[0]:,}")
    print(f"  Climate matched: {stats[1]:,} ({stats[1]/stats[0]*100:.1f}%)")
    print(f"  Climate unmatched: {stats[2]:,} ({stats[2]/stats[0]*100:.1f}%)")
    
    # Check for duplicate source rows (data integrity check)
    dup_check = con.execute("""
        SELECT COUNT(DISTINCT meta_source_row_id) as unique_source_rows
        FROM enriched_with_climate
    """).fetchone()
    
    print(f"  Unique source rows: {dup_check[0]:,}")
    if stats[0] > dup_check[0]:
        print(f"  WARNING: Row multiplication detected: {stats[0] - dup_check[0]:,} extra rows")
        print("  Deduplicating to preserve 1:1 source row mapping...")
        
        # Deduplicate: keep first occurrence of each source row
        con.execute("""
            CREATE TABLE enriched_with_climate_dedup AS
            SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (PARTITION BY meta_source_row_id ORDER BY meta_source_row_id) as _rn
                FROM enriched_with_climate
            ) WHERE _rn = 1
        """)
        con.execute("DROP TABLE enriched_with_climate")
        con.execute("ALTER TABLE enriched_with_climate_dedup RENAME TO enriched_with_climate")
        con.execute("ALTER TABLE enriched_with_climate DROP COLUMN _rn")
        
        # Re-check after deduplication
        final_stats = con.execute("SELECT COUNT(*) FROM enriched_with_climate").fetchone()
        print(f"  After deduplication: {final_stats[0]:,} rows")

    # Export to CSV
    print("Exporting to CSV...")
    t0 = time.time()
    con.execute(f"""
        COPY (SELECT * FROM enriched_with_climate ORDER BY meta_source_row_id)
        TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)
    elapsed = time.time() - t0
    print(f"  Exported in {elapsed:.1f}s")
    
    file_size = OUT_CSV.stat().st_size / 1e9
    print(f"  File size: {file_size:.2f} GB")

    con.close()

    print()
    print("=" * 70)
    print("CLIMATE INTEGRATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
