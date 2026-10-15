"""Chunked APMC ingestion with optional, validated climate columns.

The enriched CSV is already keyed by ``market_code`` and ``report_date``.
Ingestion never performs a climate join: it imports the values attached to
each source row and aggregates repeated market-series rows deterministically.
"""
from __future__ import annotations

import argparse
import os
from typing import Any

import pandas as pd
import psycopg

from training.features import normalize_columns


CLIMATE_NUMERIC = ("temperature", "rainfall", "humidity", "wind_speed")
CLIMATE_BOOLEAN = ("is_heatwave", "is_coldwave", "is_heavy_rain", "is_extreme_event")
CLIMATE_COLUMNS = CLIMATE_NUMERIC + CLIMATE_BOOLEAN
NATURAL_KEY = ("report_date", "market", "commodity", "variety")


def _as_db_value(value: Any) -> Any:
    return None if pd.isna(value) else value


def prepare_chunk(chunk: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Normalize and deterministically aggregate one CSV chunk.

    Numeric climate values are averaged and flags use ``any``. The conflict
    count reports natural-key groups with conflicting climate values.
    """
    frame = normalize_columns(chunk.copy())
    if "market_code" not in frame.columns:
        frame["market_code"] = frame["market"]
    if "min_price" not in frame.columns or frame["min_price"].isna().all():
        frame["min_price"] = frame["modal_price"]
    if "max_price" not in frame.columns or frame["max_price"].isna().all():
        frame["max_price"] = frame["modal_price"]

    has_climate = all(column in frame.columns for column in CLIMATE_COLUMNS)
    for column in CLIMATE_NUMERIC:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in CLIMATE_BOOLEAN:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = frame[column].map(lambda value: pd.NA if pd.isna(value) else bool(value))

    source_order = next((c for c in ("meta_source_row_id", "id") if c in frame.columns), None)
    if source_order:
        frame = frame.sort_values(source_order, kind="stable")

    grouped_rows = []
    conflict_count = 0
    for _, group in frame.groupby(list(NATURAL_KEY), dropna=False, sort=True):
        if has_climate:
            distinct = group.loc[:, list(CLIMATE_COLUMNS)].drop_duplicates().shape[0]
            conflict_count += int(distinct > 1)
        first = group.iloc[0]
        row = {key: first[key] for key in (*NATURAL_KEY, "market_code")}
        for column in ("arrivals", "min_price", "max_price", "modal_price", *CLIMATE_NUMERIC):
            row[column] = pd.to_numeric(group[column], errors="coerce").mean()
        for column in CLIMATE_BOOLEAN:
            values = group[column].dropna()
            row[column] = bool(values.any()) if not values.empty else pd.NA
        grouped_rows.append(row)
    return pd.DataFrame(grouped_rows), conflict_count


def ingest(path: str, database_url: str, chunk_size: int = 100_000) -> int:
    total = 0
    conflicts = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                create temporary table ingest_stage (
                    report_date date not null,
                    market text not null,
                    commodity text not null,
                    variety text not null,
                    market_code text,
                    arrivals numeric,
                    min_price numeric,
                    max_price numeric,
                    modal_price numeric,
                    temperature numeric,
                    rainfall numeric,
                    humidity numeric,
                    wind_speed numeric,
                    is_heatwave boolean,
                    is_coldwave boolean,
                    is_heavy_rain boolean,
                    is_extreme_event boolean
                ) on commit delete rows
            """)
            for chunk in pd.read_csv(path, chunksize=chunk_size, low_memory=False):
                grouped, chunk_conflicts = prepare_chunk(chunk)
                conflicts += chunk_conflicts
                source_has_climate = all(column in chunk.columns for column in CLIMATE_COLUMNS)
                rows = [
                    tuple(_as_db_value(row[column]) for column in (
                        "report_date", "market", "commodity", "variety", "market_code",
                        "arrivals", "min_price", "max_price", "modal_price", *CLIMATE_COLUMNS,
                    ))
                    for _, row in grouped.iterrows()
                ]
                
                cursor.executemany(
                    """insert into ingest_stage (
                        report_date, market, commodity, variety, market_code,
                        arrivals, min_price, max_price, modal_price,
                        temperature, rainfall, humidity, wind_speed,
                        is_heatwave, is_coldwave, is_heavy_rain, is_extreme_event
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    rows,
                )
                climate_update = """
                    temperature = s.temperature,
                    rainfall = s.rainfall,
                    humidity = s.humidity,
                    wind_speed = s.wind_speed,
                    is_heatwave = s.is_heatwave,
                    is_coldwave = s.is_coldwave,
                    is_heavy_rain = s.is_heavy_rain,
                    is_extreme_event = s.is_extreme_event,
                """ if source_has_climate else ""
                climate_clause = f", {climate_update.strip().rstrip(',')}" if climate_update else ""
                cursor.execute(f"""
                    update market_data AS m
                    set arrivals = s.arrivals,
                        min_price = s.min_price,
                        max_price = s.max_price,
                        modal_price = s.modal_price,
                        market_code = s.market_code{climate_clause}
                    from ingest_stage AS s
                    where m.report_date = s.report_date
                      and m.market = s.market
                      and m.commodity = s.commodity
                      and m.variety = s.variety
                """)
                cursor.execute("""
                    insert into market_data (
                        report_date, market, commodity, variety, market_code,
                        arrivals, min_price, max_price, modal_price,
                        temperature, rainfall, humidity, wind_speed,
                        is_heatwave, is_coldwave, is_heavy_rain, is_extreme_event
                    )
                    select s.report_date, s.market, s.commodity, s.variety, s.market_code,
                           s.arrivals, s.min_price, s.max_price, s.modal_price,
                           s.temperature, s.rainfall, s.humidity, s.wind_speed,
                           s.is_heatwave, s.is_coldwave, s.is_heavy_rain, s.is_extreme_event
                    from ingest_stage AS s
                    where not exists (
                        select 1 from market_data AS m
                        where m.report_date = s.report_date
                          and m.market = s.market
                          and m.commodity = s.commodity
                          and m.variety = s.variety
                    )
                """)
                connection.commit()
                total += len(rows)
                print(f"Ingested {total} rows so far...")
    if conflicts:
        print(f"Resolved {conflicts} conflicting natural-key climate groups deterministically.")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        default=os.getenv("DATA_PATH", "./data/apmc-arrivals-and-prices-old-data.csv"),
        help="Market CSV, or apmc_climate_enriched.csv to import optional climate columns.",
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required for ingestion.")
    print(f"Ingested {ingest(args.data, args.database_url):,} aggregated rows.")
