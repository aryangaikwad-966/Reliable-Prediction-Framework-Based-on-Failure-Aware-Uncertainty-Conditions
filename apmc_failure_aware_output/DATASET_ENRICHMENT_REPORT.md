# Dataset Enrichment Report — APMC Failure-Aware Feature Engineering

**Project**: Reliable Prediction Framework Based on Failure-Aware Uncertainty Conditions  
**Date**: 2026-10-11  
**Pipeline Version**: v1.0.0  

---

## 1. Overview

This report documents the feature engineering methodology applied to the APMC (Agricultural Produce Market Committee) market price dataset to support selective prediction research in non-stationary environments.

### Source Dataset
- **File**: `apmc-arrivals-and-prices-old-data.csv`
- **Size**: 1.005 GB (uncompressed)
- **Rows**: 5,421,343
- **Columns**: 20
- **Date range**: 2025-01-01 to 2025-10-26
- **Coverage**: 28 states, 557 districts, 3,111 markets, 331 commodities, 785 varieties

### Enriched Dataset
- **File**: `apmc_failure_aware_enriched.csv`
- **Size**: 3.50 GB (uncompressed)
- **Rows**: 5,421,343 (identical to source)
- **Columns**: 73 (20 original + 53 new)

---

## 2. Processing Approach

### 2.1 Technology Choice: DuckDB

The ~1 GB source CSV was processed using **DuckDB** rather than pandas, for several reasons:

1. **Memory efficiency**: DuckDB processes data in a columnar, vectorized engine with disk-backed storage, avoiding the need to load the entire dataset into Python memory.
2. **SQL window functions**: All lag, rolling-mean, rolling-std, and target-alignment operations were expressed as SQL window functions, which DuckDB optimizes internally.
3. **Performance**: The entire enrichment (load → transform → export) completed in ~35 seconds on 4 threads.

### 2.2 Processing Pipeline

```
Step 1: Load CSV → DuckDB table "raw" (8.5s)
Step 2: Add metadata columns (meta_source_row_id, meta_source_file, meta_processing_version)
Step 3: Build enriched table via SQL CTEs:
        CTE 1: base        — quality flags, calendar features
        CTE 2: dup_detect  — duplicate key detection
        CTE 3: with_dups   — merge duplicate flags
        CTE 4: with_price_feats — window-based price lags, rolling stats
        CTE 5: with_derived — change, trend, volatility features
        CTE 6: with_arrival_feats — arrival lags and rolling stats
        CTE 7: target_lookup — 7-day-ahead target via LEFT JOIN
Step 4: Deduplicate target join expansion (preserve 1:1 source row mapping)
Step 5: Export to CSV ordered by meta_source_row_id
Step 6: Run 15 validation checks
```

### 2.3 Series Definition

All time-series features are computed within **series boundaries** defined by:

```
(market_code, commodity, variety, price_unit)
```

This ensures:
- Different markets are never mixed
- Different commodities are never mixed  
- Different varieties of the same commodity are kept separate
- Different price units (Rs/Quintal vs Rs/Number) are never mixed

**53,254 unique series** exist in the dataset.

### 2.4 Ordering Within Series

Observations are ordered by `(report_date, id)` within each series. The `id` column (source row index) serves as a tiebreaker when multiple observations share the same date within a series.

---

## 3. Feature Groups

### 3.1 Calendar Features (6 features)

| Feature | Derivation |
|---------|-----------|
| `feat_day_of_week` | `dayofweek(report_date)`, 0=Monday, 6=Sunday |
| `feat_day_of_month` | `day(report_date)`, 1–31 |
| `feat_month` | `month(report_date)`, 1–12 |
| `feat_quarter` | `quarter(report_date)`, 1–4 |
| `feat_day_of_year` | `dayofyear(report_date)`, 1–366 |
| `feat_is_weekend` | True if day_of_week ∈ {0, 6} (Sunday=0, Saturday=6 in DuckDB) |

**Rationale**: Agricultural commodity prices exhibit strong weekly, monthly, and seasonal patterns. Weekend market closures affect reporting frequency and potentially next-open prices.

### 3.2 Price History Features (19 features)

#### Lag Features (5)
`feat_price_lag_{1,3,7,14,28}d` — Prior observation modal prices.

**Critical note**: These are **observation-based** lags, not strict calendar-day lags. In agricultural markets, observations are not daily — markets may close on holidays, weekends, or due to disruptions. `feat_price_lag_1d` is always the immediately preceding observation in the same series, regardless of how many calendar days have elapsed.

The `feat_days_since_previous_observation` column provides the actual calendar gap to interpret lag features correctly.

#### Rolling Statistics (10)
| Feature | Window | Statistic |
|---------|--------|-----------|
| `feat_price_mean_{7,14,28}d` | 1–{7,14,28} preceding obs | Mean |
| `feat_price_std_{7,14}d` | 1–{7,14} preceding obs | Sample Std Dev |
| `feat_price_min_{7,14}d` | 1–{7,14} preceding obs | Minimum |
| `feat_price_max_{7,14}d` | 1–{7,14} preceding obs | Maximum |
| `feat_price_median_14d` | 1–14 preceding obs | Median |

All rolling windows **exclude the current observation** (ROWS BETWEEN N PRECEDING AND 1 PRECEDING). This prevents temporal leakage — the current price is never included in its own rolling statistics.

#### Meta Features (2)
- `feat_price_history_count`: Ordinal position in the series (1 = first observation)
- `feat_days_since_previous_observation`: Calendar days since the previous observation

### 3.3 Derived Price Features (6 features)

| Feature | Formula | Interpretation |
|---------|---------|----------------|
| `feat_price_change_1d` | `modal_price - lag_1d` | Absolute change from previous observation |
| `feat_price_change_7d` | `modal_price - lag_7d` | Absolute change from 7 observations ago |
| `feat_price_volatility_7d` | `std_7d / mean_7d` | Coefficient of variation (7-obs window) |
| `feat_price_volatility_14d` | `std_14d / mean_14d` | Coefficient of variation (14-obs window) |
| `feat_price_trend_7d` | `(price - mean_7d) / mean_7d` | Relative momentum (7-obs window) |
| `feat_price_trend_14d` | `(price - mean_14d) / mean_14d` | Relative momentum (14-obs window) |

### 3.4 Arrival History Features (8 features)

| Feature | Description |
|---------|-------------|
| `feat_arrival_lag_{1,7}d` | Arrivals from {1, 7} observations ago |
| `feat_arrival_mean_{7,14}d` | Rolling mean arrivals |
| `feat_arrival_std_7d` | Rolling std dev of arrivals |
| `feat_arrival_history_count` | Observation count in arrival series |
| `feat_arrival_change_{1,7}d` | Absolute change in arrivals |

**Unit separation**: Arrival features use the raw `arrivals_tonnes` column. Since `arrivals_unit` perfectly correlates with `price_unit` (both switch together between Tonnes/Rs/Quintal and Nos/Rs/Number), and `price_unit` is part of the series key, different arrival units are never mixed within a series.

### 3.5 Data Quality Features (10 features)

| Feature | Logic |
|---------|-------|
| `quality_missing_price` | modal_price IS NULL |
| `quality_missing_critical_input` | any of min/max/modal price IS NULL |
| `quality_invalid_price` | modal_price ≤ 0 OR > 500,000 |
| `quality_invalid_arrivals` | arrivals_tonnes IS NULL OR < 0 |
| `quality_price_unit_supported` | price_unit = 'Rs/Quintal' |
| `quality_arrival_unit_supported` | arrivals_unit = 'Tonnes' |
| `quality_duplicate_key` | duplicate natural key exists |
| `quality_conflicting_duplicate` | duplicate key with different modal_price |
| `quality_insufficient_history` | fewer than 7 prior observations |
| `quality_observation_gap` | >7 calendar days since previous observation |

All quality flags are **Boolean** (`true`/`false`) and derived exclusively from source record values.

### 3.6 Target Features (3 features)

| Feature | Description |
|---------|-------------|
| `target_modal_price_h7d` | Modal price observed exactly 7 calendar days later, same series |
| `target_date_h7d` | report_date + 7 days |
| `target_available_h7d` | Whether the target observation exists |

**Target construction rules**:
1. Exact calendar-day match only — no interpolation, no nearby-date substitution
2. Same series (market_code + commodity + variety + price_unit)
3. If multiple observations exist on the target date (conflicting duplicates), the lower modal_price is used deterministically
4. 78.1% target availability (4,234,837 of 5,421,343 rows)

---

## 4. Temporal Leakage Prevention

### 4.1 Design Guarantees

1. **All lag features** use `LAG(..., N)` with N ≥ 1, referencing only prior observations
2. **All rolling windows** use `ROWS BETWEEN K PRECEDING AND 1 PRECEDING`, excluding the current row
3. **Ordering** within series is by `(report_date, id)`, ensuring chronological correctness
4. **Target columns** (`target_modal_price_h7d`, `target_date_h7d`, `target_available_h7d`) contain future information and are clearly separated from predictor features
5. **No future-derived statistics** are included in predictor features

### 4.2 Verified via Testing

- **Lag-1 spot check**: Independently recomputed `LAG(modal_price, 1)` and compared — 0 mismatches
- **Leakage detection**: Checked for cases where lag features improperly reference the current row — 0 found
- **Series isolation**: Verified no window function crosses series boundaries — 0 violations
- **Target alignment**: All `target_date_h7d` values exactly equal `report_date + 7 days` — 0 misalignments

---

## 5. Failure-Aware Framework Support

### 5.1 How This Dataset Supports the Three Decision States

#### PREDICT
The enriched features (price lags, rolling statistics, volatility, trends, arrivals, calendar patterns, quality flags) provide the input feature space for training a predictive model. After training:
- Model produces a point forecast
- Features like volatility, trend, and history count inform uncertainty estimation
- Quality flags indicate data completeness

#### ABSTAIN
The framework abstains based on evidence from:
- **`quality_insufficient_history`**: Not enough past data to form reliable predictions
- **`quality_observation_gap`**: Large gap suggests irregular market conditions
- **`quality_conflicting_duplicate`**: Ambiguous source data
- **`quality_invalid_price`**: Suspicious price outliers
- **`quality_missing_critical_input`**: Incomplete price information
- **`feat_price_volatility_*`**: High volatility signals unstable price dynamics
- **Model uncertainty**: Computed at inference time using prediction intervals or ensemble disagreement
- **Historical failure risk**: Computed from the failure memory table after initial predictions

#### OUT_OF_SCOPE
- Requires application-level validation (e.g., is the requested commodity in the supported list?)
- Cannot be determined from historical CSV data alone
- Supported commodities, markets, and date ranges can be derived from the enriched dataset

### 5.2 Uncertainty and Risk Estimation (Future Work)

The enriched features support computing the following at model evaluation time:

| Signal | How to Compute from Enriched Features |
|--------|---------------------------------------|
| **Predictive uncertainty** | Train an ensemble or quantile regression; use spread of predictions |
| **Conditional failure risk** | After generating predictions on validation set, compute failure rates conditioned on feature bins (e.g., high volatility + low history count) |
| **Novelty/OOD** | Compute Mahalanobis distance from training feature distribution to new observation features |
| **Covariate drift** | Monitor rolling statistics of feature distributions (e.g., compare recent `feat_price_volatility_7d` distribution to training period) |
| **Missing-information risk** | Aggregate quality flags: `quality_missing_critical_input`, `quality_insufficient_history`, `quality_observation_gap` |
| **Selective risk-coverage** | After predictions, sort by reliability score, compute risk at each coverage level |

### 5.3 Failure Memory Schema

The file `failure_memory_schema.csv` defines the schema for storing prediction outcomes:

| Column | Type | Description |
|--------|------|-------------|
| `failure_record_id` | STRING | Unique identifier for the failure record |
| `prediction_id` | STRING | Identifier linking to the specific prediction |
| `series_id` | STRING | Market+commodity+variety+unit combination |
| `prediction_origin_date` | DATE | Date the prediction was made |
| `target_date` | DATE | Date being predicted (origin + 7 days) |
| `model_version` | STRING | Version of the model used |
| `predicted_price` | DOUBLE | The model's price forecast |
| `actual_price` | DOUBLE | Observed price on the target date |
| `absolute_error` | DOUBLE | |predicted - actual| |
| `relative_error` | DOUBLE | |predicted - actual| / actual |
| `unacceptable_error_threshold` | DOUBLE | Error threshold for failure classification |
| `failure_flag` | BOOLEAN | True if error exceeds threshold |
| `prediction_uncertainty` | DOUBLE | Model's uncertainty estimate at prediction time |
| `prediction_context` | JSON | Feature values and quality flags at prediction time |
| `failure_severity` | STRING | Severity classification (e.g., NORMAL, WARNING, CRITICAL) |
| `outcome_observed_at` | TIMESTAMP | When the actual price became available |

**Status**: Empty schema only. Records will be populated during chronological walk-forward model evaluation.

---

## 6. Experimental Use Cases

### 6.1 Primary: 7-Day Tomato Price Forecast

**Subset**: Filter `commodity = 'Tomato'` AND `price_unit = 'Rs/Quintal'` (197,097 rows).

**Predictor features**: All `feat_*` columns (except target columns) where `quality_price_unit_supported = true` and `quality_insufficient_history = false`.

**Target**: `target_modal_price_h7d` where `target_available_h7d = true`.

**Evaluation**: Chronological or walk-forward split only. **Never random train/test split** for time-series data.

### 6.2 Multi-Commodity Extension

The enriched dataset retains all 331 commodities. Researchers can:
1. Filter by commodity and price_unit
2. Further subset by specific markets or varieties
3. Train commodity-specific or multi-commodity models
4. Compare prediction difficulty across commodities using quality flags and volatility features

### 6.3 Selective Prediction Research

1. Train a base model on the predictor features
2. Generate predictions on a validation set (chronological split)
3. Compute uncertainty signals (ensemble disagreement, quantile spread)
4. Compare predictions with `target_modal_price_h7d` to populate the failure memory table
5. Train a failure-risk estimator conditioned on features + quality flags
6. Apply selective prediction: PREDICT when risk is acceptable, ABSTAIN when risk is elevated
7. Evaluate selective risk, coverage, and AURC

---

## 7. Limitations and Future Work

### 7.1 Current Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Observation-based lags (not calendar-day) | Lags may span variable calendar intervals | Use `feat_days_since_previous_observation` to filter or weight |
| No external context (weather, policy) | Missing important price drivers | Document as future data integration |
| 21.9% missing targets | Reduces effective training/evaluation set | Inherent to market reporting; cannot be imputed |
| 378 conflicting duplicate rows | Ambiguous price signals | Flagged; filter via `quality_conflicting_duplicate` |
| Some lag columns stored as VARCHAR in CSV | Parsing friction | Cast to DOUBLE when loading |
| `origin` column entirely NaN | Provides no information | Preserved for schema completeness |
| No model uncertainty scores | Cannot compute PREDICT/ABSTAIN decisions | Requires trained model; documented as future step |

### 7.2 Future Data Integration Requirements

| Data Source | Purpose | Requirements |
|-------------|---------|-------------|
| IMD rainfall data | Weather-driven price shocks | Station-level daily rainfall with geographic matching |
| Temperature data | Crop growth conditions | District-level daily temperature |
| Pest/disease reports | Supply disruption indicators | Crop-specific, date-stamped, region-matched |
| Government policy data | MSP changes, export restrictions | Date-of-announcement timestamps |
| Transport disruptions | Market access events | Date and region of disruption |
| Festival/holiday calendar | Demand-driven price spikes | State-specific holiday dates |

### 7.3 Recommended Next Steps

1. **Train base XGBoost model** on Tomato subset using enriched features
2. **Generate walk-forward predictions** and populate failure memory table
3. **Compute uncertainty estimates** using ensemble or quantile methods
4. **Train failure-risk estimator** conditioned on features + quality flags
5. **Implement selective prediction** with PREDICT/ABSTAIN decisions
6. **Evaluate selective metrics**: selective MAE, selective coverage, AURC
7. **Integrate external data** as it becomes available with verified provenance
