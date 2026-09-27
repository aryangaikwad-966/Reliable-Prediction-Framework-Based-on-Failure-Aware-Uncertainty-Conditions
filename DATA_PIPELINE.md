# Data pipeline

## Source contract

The validation source is `apmc-arrivals-and-prices-old-data.csv`, approximately 5.42 million records covering 2025-01-01 through 2025-10-26. The first target is `modal_price` where `price_unit = Rs/Quintal`.

The implementation accepts common header variants (`Report Date` / `report_date`, `Modal Price` / `modal_price`, and so on) and fails explicitly if the required date, market, commodity, or target fields are not present.

## Quality decisions

- `origin` is not used because the verified source field is entirely missing.
- Invalid dates and invalid/non-numeric targets are removed.
- Negative prices are removed.
- Missing arrival values become zero only for the optional arrival feature; missing target values are removed.
- Missing varieties become `UNKNOWN`, not an invented variety.
- Repeated natural keys are retained through a documented mean aggregation of numeric values by date, market, commodity, and variety. This avoids silent row deletion while producing one aligned daily series for forecasting.
- Rows are sorted by group and report date before any lag or rolling feature is created.

## Scaling

The ingestion command uses pandas chunks rather than loading all 5.4 million rows into application memory. PostgreSQL indexes support date, commodity, market, market code, district, state, and the forecasting natural key.