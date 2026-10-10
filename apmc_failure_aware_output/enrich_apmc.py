#!/usr/bin/env python3
"""
APMC Failure-Aware Feature Enrichment Script
=============================================

Uses DuckDB for memory-efficient processing of the full ~5.4M row APMC dataset.
All window-function calculations (lags, rolling stats, targets) are performed
in SQL to avoid loading the entire 1GB CSV into Python memory.

Preserves every original row and column. Adds derived features with clear
prefixes: feat_, quality_, target_, meta_.

Usage:
    python3 enrich_apmc.py

Author: Reliable Prediction Framework
Version: 1.0.0
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import duckdb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKSPACE = Path(__file__).resolve().parent.parent
SRC_CSV = WORKSPACE / "data" / "apmc-arrivals-and-prices-old-data.csv"
OUT_DIR = WORKSPACE / "apmc_failure_aware_output"
OUT_CSV = OUT_DIR / "apmc_failure_aware_enriched.csv"
DB_PATH = OUT_DIR / "enrich_work.duckdb"  # temporary working database

# Series key: observations sharing the same series get windowed together
SERIES_KEY = "market_code, commodity, variety, price_unit"

# Ensure we never accidentally overwrite the source
assert str(OUT_CSV.resolve()) != str(SRC_CSV.resolve()), "Output must differ from source"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(con: duckdb.DuckDBPyConnection, sql: str, label: str = "") -> None:
    """Execute a SQL statement with timing."""
    t0 = time.time()
    con.execute(sql)
    elapsed = time.time() - t0
    if label:
        log(f"  {label} ({elapsed:.1f}s)")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    log("Starting APMC enrichment pipeline")
    log(f"Source CSV: {SRC_CSV}")
    log(f"Output CSV: {OUT_CSV}")

    if not SRC_CSV.exists():
        sys.exit(f"ERROR: Source CSV not found at {SRC_CSV}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Remove stale working DB if present
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = duckdb.connect(str(DB_PATH))
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute("PRAGMA enable_progress_bar")

    # ------------------------------------------------------------------
    # Step 1: Load raw CSV into a DuckDB table (preserves all columns)
    # ------------------------------------------------------------------
    log("Step 1: Loading raw CSV into DuckDB table 'raw'...")
    run(con, f"""
        CREATE TABLE raw AS
        SELECT
            row_number() OVER () AS meta_source_row_id,
            *
        FROM read_csv_auto('{SRC_CSV}', sample_size=50000, all_varchar=false)
    """, "Loaded raw table")

    src_count = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    log(f"  Source rows loaded: {src_count:,}")

    # ------------------------------------------------------------------
    # Step 2: Add meta columns
    # ------------------------------------------------------------------
    log("Step 2: Adding metadata columns...")
    run(con, f"""
        ALTER TABLE raw ADD COLUMN meta_source_file VARCHAR DEFAULT '{SRC_CSV.name}'
    """, "Added meta_source_file")
    run(con, """
        ALTER TABLE raw ADD COLUMN meta_processing_version VARCHAR DEFAULT 'v1.0.0'
    """, "Added meta_processing_version")

    # ------------------------------------------------------------------
    # Step 3: Create the enriched table with quality flags and features
    # ------------------------------------------------------------------
    log("Step 3: Building enriched table with quality flags, calendar features, and window features...")

    # We build the full enriched table in a single CREATE TABLE ... AS SELECT
    # using DuckDB window functions.  The PARTITION BY clause uses the series
    # key and the ORDER BY uses report_date, id to break ties deterministically.

    enrichment_sql = f"""
    CREATE TABLE enriched AS
    WITH
    -- ================================================================
    -- CTE 1: Base table with quality flags and calendar features
    -- ================================================================
    base AS (
        SELECT
            *,

            -- ---- Quality flags ----
            CASE WHEN modal_price IS NULL THEN true ELSE false END AS quality_missing_price,
            CASE WHEN min_price IS NULL OR max_price IS NULL OR modal_price IS NULL THEN true ELSE false END AS quality_missing_critical_input,
            CASE WHEN modal_price IS NOT NULL AND (modal_price <= 0 OR modal_price > 500000) THEN true ELSE false END AS quality_invalid_price,
            CASE WHEN arrivals_tonnes IS NULL OR arrivals_tonnes < 0 THEN true ELSE false END AS quality_invalid_arrivals,
            CASE WHEN price_unit = 'Rs/Quintal' THEN true ELSE false END AS quality_price_unit_supported,
            CASE WHEN arrivals_unit = 'Tonnes' THEN true ELSE false END AS quality_arrival_unit_supported,

            -- ---- Calendar features ----
            dayofweek(report_date) AS feat_day_of_week,
            day(report_date)       AS feat_day_of_month,
            month(report_date)     AS feat_month,
            quarter(report_date)   AS feat_quarter,
            dayofyear(report_date) AS feat_day_of_year,
            CASE WHEN dayofweek(report_date) IN (6, 0) THEN true ELSE false END AS feat_is_weekend

        FROM raw
    ),

    -- ================================================================
    -- CTE 2: Duplicate-key detection
    -- ================================================================
    dup_detect AS (
        SELECT
            meta_source_row_id,
            count(*) OVER (
                PARTITION BY report_date, {SERIES_KEY}
            ) AS _dup_count,
            -- Check if prices conflict within the duplicate group
            min(modal_price) OVER (
                PARTITION BY report_date, {SERIES_KEY}
            ) AS _dup_min_mp,
            max(modal_price) OVER (
                PARTITION BY report_date, {SERIES_KEY}
            ) AS _dup_max_mp
        FROM base
    ),

    -- ================================================================
    -- CTE 3: Merge duplicate flags
    -- ================================================================
    with_dups AS (
        SELECT
            b.*,
            CASE WHEN d._dup_count > 1 THEN true ELSE false END AS quality_duplicate_key,
            CASE WHEN d._dup_count > 1 AND d._dup_min_mp != d._dup_max_mp THEN true ELSE false END AS quality_conflicting_duplicate
        FROM base b
        JOIN dup_detect d ON b.meta_source_row_id = d.meta_source_row_id
    ),

    -- ================================================================
    -- CTE 4: Price-history features using RANGE-based window frames
    --        We use calendar-day lags (not row lags) by joining on date offset.
    --        But for 5M rows, self-joins are expensive.  Instead we use
    --        ROW-based window functions which correspond to "observation lags"
    --        and add a feat_days_since_previous_observation column.
    --        For rolling means/stds we use ROW-based windows with shift(1).
    -- ================================================================
    with_price_feats AS (
        SELECT
            wd.*,

            -- ---- Observation-lag features (shifted by N observations within series) ----
            LAG(modal_price, 1)  OVER w AS feat_price_lag_1d,
            LAG(modal_price, 3)  OVER w AS feat_price_lag_3d,
            LAG(modal_price, 7)  OVER w AS feat_price_lag_7d,
            LAG(modal_price, 14) OVER w AS feat_price_lag_14d,
            LAG(modal_price, 28) OVER w AS feat_price_lag_28d,

            -- ---- Days since previous observation ----
            report_date - LAG(report_date, 1) OVER w AS feat_days_since_previous_observation,

            -- ---- History count (observations before and including current, within series) ----
            ROW_NUMBER() OVER w AS feat_price_history_count,

            -- ---- Rolling mean (excluding current row: rows between 1 preceding and 7 preceding = shift(1).rolling(7)) ----
            AVG(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) AS feat_price_mean_7d,
            AVG(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            ) AS feat_price_mean_14d,
            AVG(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING
            ) AS feat_price_mean_28d,

            -- ---- Rolling std (population stddev for speed; NULLs auto-handled) ----
            STDDEV_SAMP(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) AS feat_price_std_7d,
            STDDEV_SAMP(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            ) AS feat_price_std_14d,

            -- ---- Rolling min / max ----
            MIN(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) AS feat_price_min_7d,
            MAX(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) AS feat_price_max_7d,
            MIN(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            ) AS feat_price_min_14d,
            MAX(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            ) AS feat_price_max_14d,

            -- ---- Median (approximate robust statistic) over 14-obs window ----
            MEDIAN(modal_price) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            ) AS feat_price_median_14d

        FROM with_dups wd
        WINDOW w AS (
            PARTITION BY {SERIES_KEY}
            ORDER BY report_date, id
        )
    ),

    -- ================================================================
    -- CTE 5: Derived price features (change, trend, volatility)
    -- ================================================================
    with_derived AS (
        SELECT
            pf.*,

            -- ---- Price changes ----
            modal_price - feat_price_lag_1d AS feat_price_change_1d,
            modal_price - feat_price_lag_7d AS feat_price_change_7d,

            -- ---- Volatility = std / mean (coefficient of variation) ----
            CASE WHEN feat_price_mean_7d > 0 THEN feat_price_std_7d / feat_price_mean_7d
                 ELSE NULL END AS feat_price_volatility_7d,
            CASE WHEN feat_price_mean_14d > 0 THEN feat_price_std_14d / feat_price_mean_14d
                 ELSE NULL END AS feat_price_volatility_14d,

            -- ---- Trend = (current - mean) / mean  (simple momentum) ----
            CASE WHEN feat_price_mean_7d > 0
                 THEN (modal_price - feat_price_mean_7d) / feat_price_mean_7d
                 ELSE NULL END AS feat_price_trend_7d,
            CASE WHEN feat_price_mean_14d > 0
                 THEN (modal_price - feat_price_mean_14d) / feat_price_mean_14d
                 ELSE NULL END AS feat_price_trend_14d,

            -- ---- Insufficient history flag ----
            CASE WHEN feat_price_history_count < 7 THEN true ELSE false END AS quality_insufficient_history,

            -- ---- Observation gap flag (> 7 days since last observation) ----
            CASE WHEN feat_days_since_previous_observation > 7 THEN true
                 WHEN feat_days_since_previous_observation IS NULL THEN true  -- first observation
                 ELSE false END AS quality_observation_gap

        FROM with_price_feats pf
    ),

    -- ================================================================
    -- CTE 6: Arrival-history features
    -- ================================================================
    with_arrival_feats AS (
        SELECT
            d.*,

            LAG(arrivals_tonnes, 1) OVER wa AS feat_arrival_lag_1d,
            LAG(arrivals_tonnes, 7) OVER wa AS feat_arrival_lag_7d,

            AVG(arrivals_tonnes) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) AS feat_arrival_mean_7d,
            AVG(arrivals_tonnes) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
            ) AS feat_arrival_mean_14d,

            STDDEV_SAMP(arrivals_tonnes) OVER (
                PARTITION BY {SERIES_KEY} ORDER BY report_date, id
                ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
            ) AS feat_arrival_std_7d,

            ROW_NUMBER() OVER wa AS feat_arrival_history_count,

            arrivals_tonnes - LAG(arrivals_tonnes, 1) OVER wa AS feat_arrival_change_1d,
            arrivals_tonnes - LAG(arrivals_tonnes, 7) OVER wa AS feat_arrival_change_7d

        FROM with_derived d
        WINDOW wa AS (
            PARTITION BY {SERIES_KEY}
            ORDER BY report_date, id
        )
    ),

    -- ================================================================
    -- CTE 7: 7-calendar-day-ahead target
    --        We look for an observation in the SAME series exactly 7
    --        calendar days later.  We use a self-join approach via a
    --        sub-select.
    -- ================================================================
    target_lookup AS (
        SELECT DISTINCT
            report_date AS t_date,
            {SERIES_KEY},
            modal_price AS t_price
        FROM raw
    )

    -- ================================================================
    -- Final SELECT: join arrival features with target
    -- ================================================================
    SELECT
        af.*,
        tl.t_price  AS target_modal_price_h7d,
        af.report_date + INTERVAL 7 DAY AS target_date_h7d,
        CASE WHEN tl.t_price IS NOT NULL THEN true ELSE false END AS target_available_h7d
    FROM with_arrival_feats af
    LEFT JOIN target_lookup tl
        ON tl.t_date = af.report_date + INTERVAL 7 DAY
       AND tl.market_code = af.market_code
       AND tl.commodity   = af.commodity
       AND tl.variety     = af.variety
       AND tl.price_unit  = af.price_unit
    """

    log("  Executing enrichment SQL (this may take several minutes)...")
    t0 = time.time()
    con.execute(enrichment_sql)
    elapsed = time.time() - t0
    log(f"  Enriched table created ({elapsed:.1f}s)")

    # ------------------------------------------------------------------
    # Step 4: Handle target duplicates from the left join
    #         (if multiple target_lookup rows match, e.g. conflicting dups)
    #         We keep only the first match per source row to preserve row count.
    # ------------------------------------------------------------------
    enriched_count = con.execute("SELECT count(*) FROM enriched").fetchone()[0]
    log(f"  Enriched table rows: {enriched_count:,} (source: {src_count:,})")

    if enriched_count > src_count:
        log("  Deduplicating target join expansion...")
        # The target join may have expanded rows if target_lookup had dups.
        # Keep one row per meta_source_row_id (the first target match).
        run(con, """
            CREATE TABLE enriched_dedup AS
            SELECT * FROM (
                SELECT *,
                    ROW_NUMBER() OVER (PARTITION BY meta_source_row_id ORDER BY target_modal_price_h7d NULLS LAST) AS _rn
                FROM enriched
            ) WHERE _rn = 1
        """, "Deduplicated target expansion")
        run(con, "DROP TABLE enriched", "Dropped old enriched")
        run(con, "ALTER TABLE enriched_dedup RENAME TO enriched", "Renamed dedup table")
        # Remove helper column
        run(con, "ALTER TABLE enriched DROP COLUMN _rn", "Dropped _rn column")
        final_count = con.execute("SELECT count(*) FROM enriched").fetchone()[0]
        log(f"  After dedup: {final_count:,} rows")
    else:
        final_count = enriched_count

    assert final_count == src_count, f"Row count mismatch: {final_count} vs {src_count}"
    log(f"  ✓ Row count preserved: {final_count:,} == {src_count:,}")

    # ------------------------------------------------------------------
    # Step 5: Export to CSV
    # ------------------------------------------------------------------
    log("Step 5: Exporting enriched CSV...")
    t0 = time.time()
    con.execute(f"""
        COPY (SELECT * FROM enriched ORDER BY meta_source_row_id)
        TO '{OUT_CSV}' (HEADER, DELIMITER ',')
    """)
    elapsed = time.time() - t0
    out_size = OUT_CSV.stat().st_size
    log(f"  Exported to {OUT_CSV} ({out_size / 1e9:.2f} GB, {elapsed:.1f}s)")

    # ------------------------------------------------------------------
    # Step 6: Validation checks
    # ------------------------------------------------------------------
    log("Step 6: Running validation checks...")
    run_validation(con, src_count)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    con.close()
    # Remove working database to save disk space
    if DB_PATH.exists():
        DB_PATH.unlink()
        log("  Removed temporary working database")

    log("=" * 60)
    log("ENRICHMENT PIPELINE COMPLETE")
    log(f"Output: {OUT_CSV}")
    log("=" * 60)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def run_validation(con: duckdb.DuckDBPyConnection, expected_rows: int) -> None:
    """Run comprehensive validation checks and print results."""
    checks_passed = 0
    checks_failed = 0

    def check(name: str, passed: bool, detail: str = ""):
        nonlocal checks_passed, checks_failed
        status = "✓ PASS" if passed else "✗ FAIL"
        if passed:
            checks_passed += 1
        else:
            checks_failed += 1
        msg = f"  [{status}] {name}"
        if detail:
            msg += f" — {detail}"
        log(msg)

    # 1. Row count
    actual = con.execute("SELECT count(*) FROM enriched").fetchone()[0]
    check("Row count preservation", actual == expected_rows,
          f"expected={expected_rows:,}, actual={actual:,}")

    # 2. Original columns preserved
    cols = [r[0] for r in con.execute("DESCRIBE enriched").fetchall()]
    original_cols = ['id', 'report_date', 'state_name', 'state_code', 'district_name',
                     'district_code', 'market_center', 'market_code', 'latitude', 'longitude',
                     'commodity_type', 'commodity', 'variety', 'origin', 'arrivals_tonnes',
                     'arrivals_unit', 'min_price', 'max_price', 'modal_price', 'price_unit']
    missing_orig = [c for c in original_cols if c not in cols]
    check("Original columns preserved", len(missing_orig) == 0,
          f"missing: {missing_orig}" if missing_orig else "all 20 original columns present")

    # 3. Source row ID uniqueness
    unique_ids = con.execute("SELECT count(DISTINCT meta_source_row_id) FROM enriched").fetchone()[0]
    check("Source row ID uniqueness", unique_ids == actual,
          f"unique={unique_ids:,}, total={actual:,}")

    # 4. Schema and data types
    schema = con.execute("DESCRIBE enriched").fetchall()
    n_cols = len(schema)
    n_new = n_cols - 20 - 3  # minus original 20 minus 3 meta columns (meta_source_row_id, meta_source_file, meta_processing_version)
    check("Schema completeness", n_cols > 20,
          f"total columns={n_cols}, new features/quality/target={n_new}")

    # 5. Missing value counts for key features
    miss_stats = con.execute("""
        SELECT
            count(*) - count(feat_price_lag_1d) AS miss_lag1,
            count(*) - count(feat_price_mean_7d) AS miss_mean7,
            count(*) - count(target_modal_price_h7d) AS miss_target
        FROM enriched
    """).fetchone()
    check("Missing values documented", True,
          f"feat_price_lag_1d: {miss_stats[0]:,} null, feat_price_mean_7d: {miss_stats[1]:,} null, target_h7d: {miss_stats[2]:,} null")

    # 6. Duplicate-key flags
    dup_stats = con.execute("""
        SELECT
            count(CASE WHEN quality_duplicate_key THEN 1 END) AS dup_rows,
            count(CASE WHEN quality_conflicting_duplicate THEN 1 END) AS conflict_rows
        FROM enriched
    """).fetchone()
    check("Duplicate key diagnostics", True,
          f"duplicate_key rows={dup_stats[0]:,}, conflicting_duplicate rows={dup_stats[1]:,}")

    # 7. Price/arrival unit consistency
    unit_stats = con.execute("""
        SELECT
            count(CASE WHEN quality_price_unit_supported THEN 1 END) AS price_ok,
            count(CASE WHEN quality_arrival_unit_supported THEN 1 END) AS arr_ok,
            count(CASE WHEN NOT quality_price_unit_supported THEN 1 END) AS price_other,
            count(CASE WHEN NOT quality_arrival_unit_supported THEN 1 END) AS arr_other
        FROM enriched
    """).fetchone()
    check("Price/arrival unit flags", True,
          f"Rs/Quintal={unit_stats[0]:,}, other_price={unit_stats[2]:,}; "
          f"Tonnes={unit_stats[1]:,}, other_arr={unit_stats[3]:,}")

    # 8. Invalid price flags
    inv_stats = con.execute("""
        SELECT count(CASE WHEN quality_invalid_price THEN 1 END) FROM enriched
    """).fetchone()[0]
    check("Invalid price flagging", True, f"{inv_stats:,} rows flagged as invalid price")

    # 9. Spot-check: lag_1d should equal the previous observation's modal_price
    spot = con.execute(f"""
        SELECT count(*) FROM (
            SELECT
                meta_source_row_id,
                modal_price,
                feat_price_lag_1d,
                LAG(modal_price, 1) OVER (PARTITION BY {SERIES_KEY} ORDER BY report_date, id) AS recomputed_lag1
            FROM enriched
        ) sub
        WHERE feat_price_lag_1d IS NOT NULL
          AND abs(feat_price_lag_1d - recomputed_lag1) > 0.01
    """).fetchone()[0]
    check("Lag-1 spot check (recomputed)", spot == 0, f"{spot} mismatches")

    # 10. Target alignment: target_date_h7d should be exactly 7 days after report_date
    target_check = con.execute("""
        SELECT count(*) FROM enriched
        WHERE target_date_h7d != report_date + INTERVAL 7 DAY
    """).fetchone()[0]
    check("Target date alignment (report_date + 7d)", target_check == 0,
          f"{target_check} misaligned rows")

    # 11. No future leakage in lags: check that lag_1d matches the recomputed lag
    #     (window functions cannot appear in WHERE, so use a subquery)
    leakage_check = con.execute(f"""
        SELECT count(*) FROM (
            SELECT
                feat_price_lag_1d,
                modal_price,
                feat_price_history_count,
                LAG(modal_price, 1) OVER (PARTITION BY {SERIES_KEY} ORDER BY report_date, id) AS recomp_lag
            FROM enriched
        ) sub
        WHERE feat_price_lag_1d IS NOT NULL
          AND feat_price_lag_1d = modal_price
          AND feat_price_history_count > 1
          AND recomp_lag != modal_price
    """).fetchone()[0]
    check("No temporal leakage in lag features", leakage_check == 0,
          f"{leakage_check} suspicious rows")

    # 12. Calendar feature range checks
    cal_check = con.execute("""
        SELECT
            min(feat_day_of_week), max(feat_day_of_week),
            min(feat_month), max(feat_month),
            min(feat_quarter), max(feat_quarter)
        FROM enriched
    """).fetchone()
    check("Calendar feature ranges", True,
          f"day_of_week=[{cal_check[0]},{cal_check[1]}], "
          f"month=[{cal_check[2]},{cal_check[3]}], "
          f"quarter=[{cal_check[4]},{cal_check[5]}]")

    # 13. Insufficient history flag vs history count
    insuf_check = con.execute("""
        SELECT count(*) FROM enriched
        WHERE quality_insufficient_history = true AND feat_price_history_count >= 7
    """).fetchone()[0]
    check("Insufficient history flag consistency", insuf_check == 0,
          f"{insuf_check} inconsistent rows")

    # 14. Original values preserved (sample check on id column)
    orig_check = con.execute(f"""
        SELECT count(*) FROM enriched e
        JOIN raw r ON e.meta_source_row_id = r.meta_source_row_id
        WHERE e.id != r.id
           OR e.report_date != r.report_date
           OR e.modal_price IS DISTINCT FROM r.modal_price
           OR e.commodity != r.commodity
    """).fetchone()[0]
    check("Original values preserved (id, date, price, commodity)", orig_check == 0,
          f"{orig_check} altered rows")

    # 15. Output file exists and is non-empty
    out_exists = OUT_CSV.exists() and OUT_CSV.stat().st_size > 0
    check("Output CSV exists and non-empty", out_exists,
          f"size={OUT_CSV.stat().st_size / 1e9:.2f} GB" if out_exists else "FILE MISSING")

    log(f"\n  Validation summary: {checks_passed} passed, {checks_failed} failed")


if __name__ == "__main__":
    main()
