"""Chunked APMC ingestion helper.

It keeps the natural key and resolves repeated rows by a documented aggregation:
numeric prices and arrivals are averaged within report_date/market/commodity/variety,
while identifiers are retained from the normalized row.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
import psycopg

from training.features import normalize_columns


def ingest(path: str, database_url: str, chunk_size: int = 100_000) -> int:
    total = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for chunk in pd.read_csv(path, chunksize=chunk_size, low_memory=False):
                frame = normalize_columns(chunk)
                
                # Handle missing columns safely for ingestion
                if "market_code" not in frame.columns:
                    frame["market_code"] = frame["market"]
                if "min_price" not in frame.columns or frame["min_price"].isna().all():
                    frame["min_price"] = frame["modal_price"]
                if "max_price" not in frame.columns or frame["max_price"].isna().all():
                    frame["max_price"] = frame["modal_price"]
                
                # Group by natural key and aggregate
                grouped = frame.groupby(["report_date", "market", "commodity", "variety"], as_index=False).agg({
                    "market_code": "first",
                    "arrivals": "mean",
                    "min_price": "mean",
                    "max_price": "mean",
                    "modal_price": "mean",
                })
                
                # Prepare rows for insertion
                rows = []
                for _, row in grouped.iterrows():
                    rows.append((
                        row["report_date"],
                        row["market"],
                        row["commodity"],
                        row["variety"],
                        row["market_code"],
                        row["arrivals"],
                        row["min_price"],
                        row["max_price"],
                        row["modal_price"],
                    ))
                
                cursor.executemany(
                    """insert into market_data (report_date, market, commodity, variety, market_code, arrivals, min_price, max_price, modal_price)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    rows,
                )
                connection.commit()
                total += len(rows)
                print(f"Ingested {total} rows so far...")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=os.getenv("DATA_PATH", "./data/apmc-arrivals-and-prices-old-data.csv"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required for ingestion.")
    print(f"Ingested {ingest(args.data, args.database_url):,} aggregated rows.")