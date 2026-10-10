# Data Dictionary — APMC Failure-Aware Enriched Dataset

**File**: `apmc_failure_aware_enriched.csv`  
**Generated**: 2026-10-11  
**Source**: `apmc-arrivals-and-prices-old-data.csv` (5,421,343 rows)  
**Processing Version**: v1.0.0  
**Total Columns**: 73 (20 original + 53 derived)  
**Total Rows**: 5,421,343 (exact match with source)

---

## Column Categories

| Prefix | Category | Description |
|--------|----------|-------------|
| *(none)* | Original | Source columns preserved verbatim |
| `meta_` | Metadata | Source lineage and processing info |
| `quality_` | Data Quality | Flags for missing, invalid, or suspicious data |
| `feat_` | Feature | Engineered predictor variables for ML |
| `target_` | Target | Forecast outcome labels (future-looking) |

---

## Original Source Columns (1–20)

> All original columns are preserved exactly as in the source CSV. No renaming, no value modification.

| # | Column | Type | Description | Unit | Missing |
|---|--------|------|-------------|------|---------|
| 1 | `id` | BIGINT | Source-assigned row index (0-based) | — | 0 |
| 2 | `report_date` | DATE | Date the market observation was reported | YYYY-MM-DD | 0 |
| 3 | `state_name` | VARCHAR | Indian state name | — | 0 |
| 4 | `state_code` | VARCHAR | State code | — | 0 |
| 5 | `district_name` | VARCHAR | District name | — | 0 |
| 6 | `district_code` | VARCHAR | District code | — | 0 |
| 7 | `market_center` | VARCHAR | Name of the APMC market center | — | 0 |
| 8 | `market_code` | BIGINT | Numeric code identifying the market | — | 0 |
| 9 | `latitude` | DOUBLE | Market center latitude | Decimal degrees | 0 |
| 10 | `longitude` | DOUBLE | Market center longitude | Decimal degrees | 0 |
| 11 | `commodity_type` | VARCHAR | Broad commodity category (e.g., Vegetables, Fruits, Other) | — | 0 |
| 12 | `commodity` | VARCHAR | Commodity name (e.g., Tomato, Onion, Rice) | — | 0 |
| 13 | `variety` | VARCHAR | Variety of the commodity (e.g., Local, Hybrid, Deshi) | — | 0 |
| 14 | `origin` | DOUBLE | Origin identifier — ALL values are NaN in this dataset | — | 5,421,343 (100%) |
| 15 | `arrivals_tonnes` | DOUBLE | Quantity of commodity arriving at market | Tonnes or Nos (see `arrivals_unit`) | 0 |
| 16 | `arrivals_unit` | VARCHAR | Unit of arrivals measurement: "Tonnes" (5,401,455) or "Nos" (19,888) | — | 0 |
| 17 | `min_price` | DOUBLE | Minimum transaction price for the day | Rs/Quintal or Rs/Number (see `price_unit`) | 0 |
| 18 | `max_price` | DOUBLE | Maximum transaction price for the day | Rs/Quintal or Rs/Number (see `price_unit`) | 3,646 |
| 19 | `modal_price` | DOUBLE | Most common transaction price (mode) | Rs/Quintal or Rs/Number (see `price_unit`) | 0 |
| 20 | `price_unit` | VARCHAR | Unit of price measurement: "Rs/Quintal" (5,401,455) or "Rs/Number" (19,888) | — | 0 |

---

## Metadata Columns (21–23)

| # | Column | Type | Description | Missing |
|---|--------|------|-------------|---------|
| 21 | `meta_source_row_id` | BIGINT | Stable, unique row identifier (1-based). Matches 1:1 with source rows. | 0 |
| 22 | `meta_source_file` | VARCHAR | Name of the source CSV file | 0 |
| 23 | `meta_processing_version` | VARCHAR | Version of the enrichment pipeline (e.g., "v1.0.0") | 0 |

---

## Data Quality Columns (24–33)

All quality columns are BOOLEAN (`true`/`false`). They are derived directly from source record values.

| # | Column | Description | True Count |
|---|--------|-------------|------------|
| 24 | `quality_missing_price` | `modal_price` is NULL | 0 |
| 25 | `quality_missing_critical_input` | Any of `min_price`, `max_price`, `modal_price` is NULL | 3,646 |
| 26 | `quality_invalid_price` | `modal_price` ≤ 0 or > 500,000 (extreme outlier) | 3 |
| 27 | `quality_invalid_arrivals` | `arrivals_tonnes` is NULL or negative | 0 |
| 28 | `quality_price_unit_supported` | `price_unit` = "Rs/Quintal" (the primary supported unit) | 5,401,455 |
| 29 | `quality_arrival_unit_supported` | `arrivals_unit` = "Tonnes" (the primary supported unit) | 5,401,455 |
| 30 | `quality_duplicate_key` | Row shares its natural key (date + market_code + commodity + variety + price_unit) with another row | 380 |
| 31 | `quality_conflicting_duplicate` | Duplicate key AND `modal_price` differs between duplicates | 378 |
| 32 | `quality_insufficient_history` | Fewer than 7 prior observations in the same series | ~249K |
| 33 | `quality_observation_gap` | Gap of >7 calendar days since previous observation in the same series, or first observation | ~53K |

---

## Calendar Feature Columns (34–39)

Deterministic features derived from `report_date`. Always available, no missing values.

| # | Column | Type | Description | Range |
|---|--------|------|-------------|-------|
| 34 | `feat_day_of_week` | BIGINT | Day of week (0=Monday, 6=Sunday) | 0–6 |
| 35 | `feat_day_of_month` | BIGINT | Day of the month | 1–31 |
| 36 | `feat_month` | BIGINT | Calendar month | 1–12 |
| 37 | `feat_quarter` | BIGINT | Calendar quarter | 1–4 |
| 38 | `feat_day_of_year` | BIGINT | Day of the year | 1–366 |
| 39 | `feat_is_weekend` | BOOLEAN | True if Saturday (5) or Sunday (6) | — |

---

## Price History Feature Columns (40–56)

All price features are computed **within the same series** defined by: `(market_code, commodity, variety, price_unit)`.

**Temporal guarantee**: All features use only past observations (shifted by ≥1 observation). Rolling windows exclude the current row.

**Important**: Lag features (lag_1d, lag_3d, etc.) are **observation-based lags**, not strict calendar-day lags. `feat_price_lag_1d` is the modal_price from the immediately preceding observation in the same series, which may not be exactly 1 calendar day earlier. Use `feat_days_since_previous_observation` to determine the actual calendar gap.

| # | Column | Type | Description | Null Reason |
|---|--------|------|-------------|-------------|
| 40 | `feat_price_lag_1d` | DOUBLE | Modal price from 1 observation ago in the series | First observation in series |
| 41 | `feat_price_lag_3d` | DOUBLE | Modal price from 3 observations ago | Fewer than 3 prior observations |
| 42 | `feat_price_lag_7d` | DOUBLE | Modal price from 7 observations ago | Fewer than 7 prior observations |
| 43 | `feat_price_lag_14d` | DOUBLE | Modal price from 14 observations ago | Fewer than 14 prior observations |
| 44 | `feat_price_lag_28d` | DOUBLE | Modal price from 28 observations ago | Fewer than 28 prior observations |
| 45 | `feat_days_since_previous_observation` | BIGINT | Calendar days between current and previous observation in series | First observation |
| 46 | `feat_price_history_count` | BIGINT | Ordinal position within the series (1 = first observation) | Never null |
| 47 | `feat_price_mean_7d` | DOUBLE | Mean of modal_price over preceding 1–7 observations | First observation |
| 48 | `feat_price_mean_14d` | DOUBLE | Mean of modal_price over preceding 1–14 observations | First observation |
| 49 | `feat_price_mean_28d` | DOUBLE | Mean of modal_price over preceding 1–28 observations | First observation |
| 50 | `feat_price_std_7d` | DOUBLE | Sample std dev of modal_price over preceding 1–7 observations | Fewer than 2 preceding observations |
| 51 | `feat_price_std_14d` | DOUBLE | Sample std dev of modal_price over preceding 1–14 observations | Fewer than 2 preceding observations |
| 52 | `feat_price_min_7d` | DOUBLE | Minimum modal_price over preceding 1–7 observations | First observation |
| 53 | `feat_price_max_7d` | DOUBLE | Maximum modal_price over preceding 1–7 observations | First observation |
| 54 | `feat_price_min_14d` | DOUBLE | Minimum modal_price over preceding 1–14 observations | First observation |
| 55 | `feat_price_max_14d` | DOUBLE | Maximum modal_price over preceding 1–14 observations | First observation |
| 56 | `feat_price_median_14d` | DOUBLE | Median modal_price over preceding 1–14 observations | First observation |

---

## Derived Price Feature Columns (57–62)

| # | Column | Type | Description | Null Reason |
|---|--------|------|-------------|-------------|
| 57 | `feat_price_change_1d` | DOUBLE | `modal_price - feat_price_lag_1d` (absolute price change vs previous observation) | `feat_price_lag_1d` is null |
| 58 | `feat_price_change_7d` | DOUBLE | `modal_price - feat_price_lag_7d` (absolute price change vs 7-obs-ago) | `feat_price_lag_7d` is null |
| 59 | `feat_price_volatility_7d` | DOUBLE | Coefficient of variation: `feat_price_std_7d / feat_price_mean_7d` | Std or mean unavailable |
| 60 | `feat_price_volatility_14d` | DOUBLE | Coefficient of variation: `feat_price_std_14d / feat_price_mean_14d` | Std or mean unavailable |
| 61 | `feat_price_trend_7d` | DOUBLE | Momentum: `(modal_price - feat_price_mean_7d) / feat_price_mean_7d` | Mean unavailable |
| 62 | `feat_price_trend_14d` | DOUBLE | Momentum: `(modal_price - feat_price_mean_14d) / feat_price_mean_14d` | Mean unavailable |

---

## Arrival History Feature Columns (63–70)

Computed within the same series `(market_code, commodity, variety, price_unit)`. Uses `arrivals_tonnes` as the source value.

**Caveat**: The `arrivals_unit` may be "Nos" (numbers) for 19,888 rows. The feature pipeline does not mix units within a series (since `price_unit` is part of the series key and perfectly correlates with `arrivals_unit`), but users should check `quality_arrival_unit_supported` before using arrival features across different unit types.

| # | Column | Type | Description | Null Reason |
|---|--------|------|-------------|-------------|
| 63 | `feat_arrival_lag_1d` | DOUBLE | Arrivals from 1 observation ago | First observation |
| 64 | `feat_arrival_lag_7d` | DOUBLE | Arrivals from 7 observations ago | Fewer than 7 prior observations |
| 65 | `feat_arrival_mean_7d` | DOUBLE | Mean arrivals over preceding 1–7 observations | First observation |
| 66 | `feat_arrival_mean_14d` | DOUBLE | Mean arrivals over preceding 1–14 observations | First observation |
| 67 | `feat_arrival_std_7d` | DOUBLE | Sample std dev of arrivals over preceding 1–7 observations | Fewer than 2 preceding |
| 68 | `feat_arrival_history_count` | BIGINT | Ordinal position in arrival series (same as price history count) | Never null |
| 69 | `feat_arrival_change_1d` | DOUBLE | `arrivals_tonnes - feat_arrival_lag_1d` | First observation |
| 70 | `feat_arrival_change_7d` | DOUBLE | `arrivals_tonnes - feat_arrival_lag_7d` | Fewer than 7 prior |

---

## Target Columns (71–73)

These columns represent the **forecast outcome** — they contain future information and **must never be used as predictor features**.

| # | Column | Type | Description | Null Reason |
|---|--------|------|-------------|-------------|
| 71 | `target_modal_price_h7d` | DOUBLE | Modal price observed exactly 7 calendar days after `report_date`, in the same series | No observation exists 7 days ahead |
| 72 | `target_date_h7d` | DATE | `report_date + 7 days` (the target date, whether or not an observation exists) | Never null |
| 73 | `target_available_h7d` | BOOLEAN | True if `target_modal_price_h7d` is non-null | Never null |

**Target construction**:
- Matches on exact calendar date +7 days, same `(market_code, commodity, variety, price_unit)`.
- If the target date has no observation in the same series, the target is `NULL` — no interpolation or nearby-date substitution.
- If the target date has conflicting duplicate observations, the lower modal_price is used (deterministic).
- 4,234,837 rows (78.1%) have a valid target; 1,186,506 rows (21.9%) have no matching future observation.

---

## Series Definition

A **series** is defined as a unique combination of:
- `market_code` — numeric market identifier
- `commodity` — commodity name
- `variety` — commodity variety
- `price_unit` — price measurement unit

There are **53,254 unique series** in the dataset. All window functions (lags, rolling statistics) are computed strictly within series boundaries.

---

## Fields NOT Included (and Why)

The following fields are **not populated** because they require model predictions, runtime evaluation, or external data that is not available from the source CSV alone:

| Field Category | Examples | Reason |
|----------------|----------|--------|
| Uncertainty scores | `model_uncertainty`, `confidence_score` | Requires trained model inference |
| Failure risk | `failure_probability`, `failure_severity` | Requires comparison of predictions with observed outcomes |
| Drift indicators | `drift_score`, `concept_drift_flag` | Requires running model and monitoring residual distributions |
| Novelty scores | `ood_score`, `novelty_indicator` | Requires training data statistics from a fitted model |
| Decision states | `PREDICT`, `ABSTAIN`, `OUT_OF_SCOPE` | Requires runtime application logic, not historical labels |
| External context | Rainfall, temperature, pest outbreaks, policy changes | Not available in the source CSV; requires verified external datasets |
| Calibrated probabilities | `p_unacceptable_error` | Requires calibration evaluation on held-out predictions |

These fields are documented in the **failure memory schema** (`failure_memory_schema.csv`) and will be populated during chronological model evaluation.

---

## CSV Serialization Notes

1. **Boolean values** are stored as `true`/`false` strings in CSV.
2. **NULL/missing values** are stored as empty fields (`,,`).
3. **Dates** are in `YYYY-MM-DD` format. `target_date_h7d` may include a timestamp component (`YYYY-MM-DD 00:00:00`) due to DuckDB's interval arithmetic.
4. **Some lag columns** (lag_3d, lag_7d, lag_14d, lag_28d, arrival_lag_7d, price_change_7d, arrival_change_7d) may be auto-detected as VARCHAR by some CSV parsers due to high NULL ratios at series starts. The actual non-null values are numeric and should be cast to DOUBLE/FLOAT when loading.
5. **Floating-point precision**: Prices are stored with full double precision. Source values like `3200.0` are faithfully preserved.
