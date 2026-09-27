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
                grouped = frame.groupby(["report_date", "market", "commodity", "variety"], as_index=False).agg(
                    market_code=("market_code", "first") if "market_code" in frame.columns else ("market", "first"),
                    arrivals=("arrivals", "mean"),
                    min_price=("min_price", "mean") if "min_price" in frame.columns else ("modal_price", "min"),
                    max_price=("max_price", "mean") if "max_price" in frame.columns else ("modal_price", "max"),
                    modal_price=("modal_price", "mean"),
                )
                rows = [tuple(row) for row in grouped.itertuples(index=False, name=None)]
                cursor.executemany(
                    """insert into market_data (report_date, market, commodity, variety, market_code, arrivals, min_price, max_price, modal_price)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    rows,
                )
                connection.commit()
                total += len(rows)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=os.getenv("DATA_PATH", "./data/apmc-arrivals-and-prices-old-data.csv"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required for ingestion.")
    print(f"Ingested {ingest(args.data, args.database_url):,} aggregated rows.")