from __future__ import annotations

import pandas as pd


FEATURES = [
    "lag_1", "lag_2", "lag_3", "lag_7", "lag_14", "lag_30",
    "rolling_mean_7", "rolling_mean_14", "rolling_mean_30",
    "rolling_std_7", "rolling_std_30", "price_change_1", "price_change_7",
    "price_volatility", "arrival_lag_1", "arrival_lag_7",
    "rolling_arrival_mean", "arrival_change", "day_of_week", "day_of_month",
    "month", "week_of_year",
]


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "report_date": "report_date",
        "Report Date": "report_date",
        "market_code": "market_code",
        "Market Code": "market_code",
        "market": "market",
        "Market": "market",
        "commodity": "commodity",
        "Commodity": "commodity",
        "variety": "variety",
        "Variety": "variety",
        "modal_price": "modal_price",
        "Modal Price": "modal_price",
        "arrival": "arrivals",
        "arrivals": "arrivals",
        "Arrivals": "arrivals",
        "price_unit": "price_unit",
    }
    frame = frame.rename(columns={key: value for key, value in rename.items() if key in frame.columns})
    required = {"report_date", "market", "commodity", "modal_price"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    frame["modal_price"] = pd.to_numeric(frame["modal_price"], errors="coerce")
    frame["arrivals"] = pd.to_numeric(frame.get("arrivals", 0), errors="coerce").fillna(0)
    frame["variety"] = frame.get("variety", "UNKNOWN").fillna("UNKNOWN").astype(str).str.strip()
    frame["market"] = frame["market"].fillna("UNKNOWN").astype(str).str.strip()
    frame["commodity"] = frame["commodity"].fillna("UNKNOWN").astype(str).str.strip()
    frame = frame.dropna(subset=["report_date", "modal_price"])
    frame = frame[frame["modal_price"] >= 0]
    return frame


def add_features(frame: pd.DataFrame, horizon: int = 7) -> pd.DataFrame:
    frame = frame.sort_values(["market", "commodity", "variety", "report_date"]).copy()
    group = frame.groupby(["market", "commodity", "variety"], group_keys=False)
    for lag in [1, 2, 3, 7, 14, 30]:
        frame[f"lag_{lag}"] = group["modal_price"].shift(lag)
    for window in [7, 14, 30]:
        frame[f"rolling_mean_{window}"] = group["modal_price"].transform(lambda series: series.shift(1).rolling(window, min_periods=2).mean())
    for window in [7, 30]:
        frame[f"rolling_std_{window}"] = group["modal_price"].transform(lambda series: series.shift(1).rolling(window, min_periods=2).std())
    frame["price_change_1"] = frame["modal_price"] - frame["lag_1"]
    frame["price_change_7"] = frame["modal_price"] - frame["lag_7"]
    frame["price_volatility"] = frame["rolling_std_7"] / frame["rolling_mean_7"].replace(0, pd.NA)
    frame["arrival_lag_1"] = group["arrivals"].shift(1)
    frame["arrival_lag_7"] = group["arrivals"].shift(7)
    frame["rolling_arrival_mean"] = group["arrivals"].transform(lambda series: series.shift(1).rolling(7, min_periods=2).mean())
    frame["arrival_change"] = frame["arrivals"] - frame["arrival_lag_1"]
    frame["day_of_week"] = frame["report_date"].dt.dayofweek
    frame["day_of_month"] = frame["report_date"].dt.day
    frame["month"] = frame["report_date"].dt.month
    frame["week_of_year"] = frame["report_date"].dt.isocalendar().week.astype(int)
    frame["target"] = group["modal_price"].shift(-horizon)
    return frame.replace([float("inf"), float("-inf")], pd.NA).dropna(subset=FEATURES + ["target"])