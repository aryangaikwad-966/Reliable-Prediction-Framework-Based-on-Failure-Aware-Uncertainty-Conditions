#!/usr/bin/env python3
from __future__ import annotations

import json
import numpy as np
import pandas as pd
import duckdb
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
import random

WORKSPACE = Path(__file__).resolve().parent.parent
SRC_CSV = WORKSPACE / "data" / "apmc-arrivals-and-prices-old-data.csv"
OUT_DIR = WORKSPACE / "apmc_failure_aware_output"
OUT_CSV = OUT_DIR / "apmc_climate_data.csv"

CLIMATE_ZONES = {
    "north": {
        "temp_base": 25.0,
        "temp_seasonal_amp": 15.0,
        "monsoon_rain": 200.0,
        "winter_rain": 10.0,
        "summer_rain": 50.0,
        "humidity_base": 0.50,
        "humidity_seasonal_amp": 0.30,
    },
    "central": {
        "temp_base": 28.0,
        "temp_seasonal_amp": 10.0,
        "monsoon_rain": 150.0,
        "winter_rain": 5.0,
        "summer_rain": 30.0,
        "humidity_base": 0.55,
        "humidity_seasonal_amp": 0.25,
    },
    "south": {
        "temp_base": 30.0,
        "temp_seasonal_amp": 5.0,
        "monsoon_rain": 250.0,
        "winter_rain": 20.0,
        "summer_rain": 40.0,
        "humidity_base": 0.65,
        "humidity_seasonal_amp": 0.20,
    },
}


def get_climate_zone(latitude: float) -> str:
    if latitude > 20:
        return "north"
    elif latitude > 15:
        return "central"
    else:
        return "south"


def seasonal_factor(date: datetime) -> float:
    day_of_year = date.timetuple().tm_yday
    if day_of_year < 60:
        return -1.0 + (day_of_year / 60) * 0.5
    elif day_of_year < 150:
        return -0.5 + ((day_of_year - 60) / 90) * 1.0
    elif day_of_year < 240:
        return 0.5 + ((day_of_year - 150) / 90) * 0.5
    else:
        return 1.0 - ((day_of_year - 240) / 125) * 1.5


def generate_daily_weather(
    date: datetime,
    latitude: float,
    longitude: float,
    prev_day_weather: Dict | None = None,
) -> Dict:
    zone = CLIMATE_ZONES[get_climate_zone(latitude)]
    season = seasonal_factor(date)

    temp_mean = zone["temp_base"] + season * zone["temp_seasonal_amp"]
    temp_std = 3.0
    temp = np.random.normal(temp_mean, temp_std)

    if prev_day_weather:
        temp = 0.7 * temp + 0.3 * prev_day_weather["temperature"]

    is_monsoon = 6 <= date.month <= 9
    rain_prob = 0.4 if is_monsoon else 0.1

    if np.random.random() < rain_prob:
        rain_mean = zone["monsoon_rain"] if is_monsoon else zone["winter_rain"]
        rain = np.random.exponential(rain_mean)
        if np.random.random() < 0.05:
            rain *= 3.0
    else:
        rain = 0.0

    humidity_mean = zone["humidity_base"] + season * zone["humidity_seasonal_amp"]
    if rain > 0:
        humidity_mean += 0.2
    humidity = np.clip(np.random.normal(humidity_mean, 0.1), 0.2, 1.0)

    wind_base = 5.0
    wind = np.random.gamma(2.0, wind_base / 2.0)
    if rain > 50:
        wind *= 1.5

    is_heatwave = temp > (temp_mean + 2 * temp_std) and not is_monsoon
    is_coldwave = temp < (temp_mean - 2 * temp_std) and date.month in [12, 1, 2]
    is_heavy_rain = rain > 100.0
    is_extreme_event = is_heatwave or is_coldwave or is_heavy_rain

    return {
        "date": date.strftime("%Y-%m-%d"),
        "latitude": latitude,
        "longitude": longitude,
        "temperature": round(temp, 1),
        "rainfall": round(rain, 1),
        "humidity": round(humidity, 3),
        "wind_speed": round(wind, 1),
        "is_heatwave": is_heatwave,
        "is_coldwave": is_coldwave,
        "is_heavy_rain": is_heavy_rain,
        "is_extreme_event": is_extreme_event,
    }


def main():
    print("=" * 70)
    print("SYNTHETIC CLIMATE DATA GENERATOR")
    print("=" * 70)
    print(f"Source APMC: {SRC_CSV}")
    print(f"Output: {OUT_CSV}")
    print()
    print("DATA PROVENANCE: SYNTHETIC")
    print("This generates realistic weather patterns based on Indian climatology.")
    print("The APMC dataset contains future dates (2025), so real historical")
    print("climate data cannot be matched. This is for demonstration only.")
    print()

    if not SRC_CSV.exists():
        raise SystemExit(f"ERROR: Source APMC CSV not found at {SRC_CSV}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading APMC data to extract market locations and date range...")
    con = duckdb.connect()
    con.execute(f"""
        CREATE TEMP TABLE apmc AS
        SELECT DISTINCT market_code, market_center, latitude, longitude, report_date
        FROM read_csv_auto('{SRC_CSV}', sample_size=50000)
    """)

    markets = con.execute("""
        SELECT market_code, market_center, latitude, longitude
        FROM apmc
        GROUP BY market_code, market_center, latitude, longitude
        ORDER BY market_code
    """).fetchall()

    date_range = con.execute("""
        SELECT MIN(report_date) as min_date, MAX(report_date) as max_date
        FROM apmc
    """).fetchone()

    con.close()

    print(f"Found {len(markets)} unique market locations")
    print(f"Date range: {date_range[0]} to {date_range[1]}")
    print()

    start_date = pd.to_datetime(date_range[0])
    end_date = pd.to_datetime(date_range[1])
    date_range_pd = pd.date_range(start_date, end_date, freq="D")

    print(f"Generating weather for {len(date_range_pd)} days x {len(markets)} markets...")
    print(f"Total records: {len(date_range_pd) * len(markets):,}")
    print()

    weather_records = []

    for i, (market_code, market_center, lat, lon) in enumerate(markets):
        if (i + 1) % 100 == 0:
            print(f"  Processing market {i+1}/{len(markets)}...")

        prev_weather = None
        for date in date_range_pd:
            weather = generate_daily_weather(date, lat, lon, prev_weather)
            weather["market_code"] = market_code
            weather["market_center"] = market_center
            weather_records.append(weather)
            prev_weather = weather

    df = pd.DataFrame(weather_records)
    
    print(f"Generated {len(df):,} weather records")
    print(f"Extreme events: {df['is_extreme_event'].sum():,}")
    print(f"  Heat waves: {df['is_heatwave'].sum():,}")
    print(f"  Cold waves: {df['is_coldwave'].sum():,}")
    print(f"  Heavy rain: {df['is_heavy_rain'].sum():,}")
    print()

    df.to_csv(OUT_CSV, index=False)
    print(f"Saved to: {OUT_CSV}")
    print(f"File size: {OUT_CSV.stat().st_size / 1e6:.2f} MB")

    metadata = {
        "provenance": "SYNTHETIC",
        "purpose": "Demonstration of climate-aware prediction framework",
        "note": "APMC dataset contains future dates (2025), so real historical climate data cannot be matched. This synthetic data is generated based on Indian climatic patterns for framework demonstration.",
        "generation_date": datetime.now().isoformat(),
        "source_markets": len(markets),
        "date_range": [str(start_date.date()), str(end_date.date())],
        "total_records": len(df),
        "climate_zones": {
            "north": sum(1 for _, _, lat, _ in markets if lat > 20),
            "central": sum(1 for _, _, lat, _ in markets if 15 < lat <= 20),
            "south": sum(1 for _, _, lat, _ in markets if lat <= 15),
        },
        "extreme_events": {
            "total": int(df["is_extreme_event"].sum()),
            "heat_waves": int(df["is_heatwave"].sum()),
            "cold_waves": int(df["is_coldwave"].sum()),
            "heavy_rain": int(df["is_heavy_rain"].sum()),
        },
    }

    metadata_file = OUT_DIR / "climate_data_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to: {metadata_file}")

    print()
    print("=" * 70)
    print("CLIMATE DATA GENERATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
