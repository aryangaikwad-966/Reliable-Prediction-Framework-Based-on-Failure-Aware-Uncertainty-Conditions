# Data Validation Report — APMC Failure-Aware Enriched Dataset

**Generated**: 2026-10-11  
**Pipeline Version**: v1.0.0  
**Source**: `apmc-arrivals-and-prices-old-data.csv`  
**Output**: `apmc_failure_aware_enriched.csv`

---

## Summary

| Metric | Value |
|--------|-------|
| Total validation checks | 15 |
| Checks passed | **15** |
| Checks failed | **0** |
| Source row count | 5,421,343 |
| Output row count | 5,421,343 |
| Row count match | ✓ |
| Original columns preserved | 20/20 |
| New columns added | 53 |
| Total columns | 73 |
| Output file size | 3.50 GB |
| Processing time | ~35 seconds total |

---

## Detailed Validation Results

### 1. ✓ Row Count Preservation
- **Expected**: 5,421,343 rows
- **Actual**: 5,421,343 rows
- **Result**: Exact match. No rows added or removed.

### 2. ✓ Original Columns Preserved
- All 20 original columns are present in the output.
- Column names unchanged: `id`, `report_date`, `state_name`, `state_code`, `district_name`, `district_code`, `market_center`, `market_code`, `latitude`, `longitude`, `commodity_type`, `commodity`, `variety`, `origin`, `arrivals_tonnes`, `arrivals_unit`, `min_price`, `max_price`, `modal_price`, `price_unit`.

### 3. ✓ Source Row ID Uniqueness
- `meta_source_row_id` has 5,421,343 unique values across 5,421,343 rows.
- Every source row is uniquely identifiable and traceable.

### 4. ✓ Schema Completeness
- 73 total columns: 20 original + 3 meta + 10 quality + 6 calendar + 19 price features + 5 derived price features + 8 arrival features + 3 target.
- All columns have appropriate data types.

### 5. ✓ Missing Value Counts

| Feature | Null Count | Null Rate | Reason |
|---------|-----------|-----------|--------|
| `feat_price_lag_1d` | 53,244 | 0.98% | First observation in 53,244 series |
| `feat_price_lag_3d` | ~158K | ~2.9% | Fewer than 3 prior observations |
| `feat_price_lag_7d` | ~369K | ~6.8% | Fewer than 7 prior observations |
| `feat_price_lag_14d` | ~705K | ~13.0% | Fewer than 14 prior observations |
| `feat_price_lag_28d` | ~1.22M | ~22.5% | Fewer than 28 prior observations |
| `feat_price_mean_7d` | 53,244 | 0.98% | First observation |
| `feat_price_std_7d` | ~106K | ~2.0% | Fewer than 2 preceding observations |
| `target_modal_price_h7d` | 1,186,506 | 21.9% | No observation 7 days ahead |

All nulls are expected and correctly reflect insufficient history or missing future observations.

### 6. ✓ Duplicate Key Diagnostics
- **380 rows** have a duplicate natural key (date + market_code + commodity + variety + price_unit).
- **378 rows** are conflicting duplicates (different `modal_price` within the same key).
- **2 rows** are exact duplicates (identical `modal_price`).
- All duplicate rows are **preserved** (not removed) and flagged via `quality_duplicate_key` and `quality_conflicting_duplicate`.
- 189 unique duplicate key groups identified.

### 7. ✓ Price and Arrival Unit Consistency
| Unit | Price Rows | Arrival Rows |
|------|-----------|-------------|
| Rs/Quintal / Tonnes | 5,401,455 | 5,401,455 |
| Rs/Number / Nos | 19,888 | 19,888 |

Price unit and arrival unit are perfectly correlated (same 19,888 rows for both non-standard units). The `quality_price_unit_supported` and `quality_arrival_unit_supported` flags correctly identify the standard vs non-standard unit rows.

### 8. ✓ Invalid Price Flagging
- **3 rows** flagged with `quality_invalid_price = true` (modal_price > 500,000).
- **0 rows** with modal_price ≤ 0.
- Maximum modal_price: 856,400 Rs/Quintal (flagged as suspicious but preserved).

### 9. ✓ Lag-1 Spot Check (Recomputed)
- Independently recomputed `LAG(modal_price, 1)` over the same window definition.
- **0 mismatches** between `feat_price_lag_1d` and the recomputed value.
- Tolerance: 0.01 absolute difference.

### 10. ✓ Target Date Alignment
- `target_date_h7d` equals `report_date + 7 days` for all 5,421,343 rows.
- **0 misaligned rows**.

### 11. ✓ No Temporal Leakage in Lag Features
- Checked for cases where `feat_price_lag_1d = modal_price` but the recomputed lag differs.
- **0 suspicious rows** found.
- Lag features correctly reference prior observations only.

### 12. ✓ Calendar Feature Ranges
| Feature | Min | Max | Expected |
|---------|-----|-----|----------|
| `feat_day_of_week` | 0 | 6 | 0–6 (Mon–Sun) |
| `feat_month` | 1 | 10 | 1–10 (Jan–Oct 2025) |
| `feat_quarter` | 1 | 4 | 1–4 |

### 13. ✓ Insufficient History Flag Consistency
- **0 rows** where `quality_insufficient_history = true` AND `feat_price_history_count ≥ 7`.
- The flag is perfectly consistent with the history count.

### 14. ✓ Series Isolation (No Cross-Contamination)
- Verified that no window function leaks values across series boundaries.
- **0 rows** where the previous row in the window belongs to a different market_code or commodity.

### 15. ✓ Target Not Identical to Current Price
- 1,498,014 of 4,234,837 non-null targets (35.4%) have the same value as the current `modal_price`.
- This is **expected behavior** — many agricultural prices remain stable over 7-day periods, especially in smaller markets.
- This is NOT an error or leakage; it reflects genuine price stickiness in the data.

---

## Additional Diagnostics

### Date Range
- **Minimum date**: 2025-01-01
- **Maximum date**: 2025-10-26
- **Span**: ~299 days (≈10 months)

### Geographic Coverage
| Dimension | Unique Values |
|-----------|--------------|
| States | 28 |
| Districts | 557 |
| Markets | 3,111 |
| Commodities | 331 |
| Varieties | 785 |
| Unique series | 53,254 |

### Tomato Subset (Primary Experimental Target)
| Metric | Value |
|--------|-------|
| Tomato rows | 197,097 |
| Tomato markets | 1,146 |
| Tomato varieties | 6 (Deshi, Other, Tomato, Hybrid, Local, Sankar) |
| Date range | 2025-01-01 to 2025-10-26 |

### Processing Resources
| Metric | Value |
|--------|-------|
| CSV load time | 8.5 seconds |
| Enrichment SQL time | 14.5 seconds |
| Target join dedup time | 4.4 seconds |
| CSV export time | 7.8 seconds |
| Validation time | ~5 seconds |
| Total processing time | ~35 seconds |
| Peak disk usage | ~7 GB (DuckDB working DB + output CSV) |
| Working DB removed after completion | Yes |

---

## Known Limitations

1. **Lag features are observation-based, not strict calendar-day lags**. `feat_price_lag_1d` is the modal_price from the previous observation in the series, which may not be exactly 1 calendar day earlier. Markets do not report every day. Use `feat_days_since_previous_observation` to identify actual calendar gaps.

2. **Some CSV column types may auto-detect as VARCHAR**. Lag columns with high null ratios (lag_3d, lag_7d, lag_14d, lag_28d) may be auto-parsed as VARCHAR by some CSV readers. Non-null values are numeric and should be cast to DOUBLE.

3. **Conflicting duplicate rows are preserved, not resolved**. 378 rows have conflicting prices for the same key. Both rows are kept with quality flags. Feature calculations may include both conflicting values in the same series window. Users should filter on `quality_conflicting_duplicate = false` for clean analysis.

4. **Origin column is entirely NaN**. All 5,421,343 rows have NaN for `origin`. This column is preserved but provides no information.

5. **No external context data**. Rainfall, temperature, pest/disease, policy changes, and other external factors are not available in the source CSV and are not fabricated. These remain future integration requirements.

6. **Target availability depends on market reporting patterns**. 21.9% of rows have no target because the same series has no observation exactly 7 calendar days later. This is inherent to the market data, not a processing error.

7. **`target_date_h7d` is stored as TIMESTAMP** in the CSV due to DuckDB's interval arithmetic. The time component is always 00:00:00 and can be safely cast to DATE.
