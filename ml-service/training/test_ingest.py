import pandas as pd

from training.ingest import prepare_chunk


def _market_rows(with_climate: bool = True) -> pd.DataFrame:
    rows = [
        {
            "report_date": "2025-01-01", "market": "A", "commodity": "Onion", "variety": "Red",
            "market_code": "A1", "arrivals": 10, "min_price": 90, "max_price": 110, "modal_price": 100,
            "meta_source_row_id": 2,
        },
        {
            "report_date": "2025-01-01", "market": "A", "commodity": "Onion", "variety": "Red",
            "market_code": "A1", "arrivals": 20, "min_price": 100, "max_price": 120, "modal_price": 110,
            "meta_source_row_id": 1,
        },
    ]
    if with_climate:
        for row, temperature, heatwave in zip(rows, (20, 40), (False, True)):
            row.update({
                "temperature": temperature, "rainfall": 5, "humidity": 0.5,
                "wind_speed": 4, "is_heatwave": heatwave, "is_coldwave": False,
                "is_heavy_rain": False, "is_extreme_event": heatwave,
            })
    return pd.DataFrame(rows)


def test_prepare_chunk_resolves_climate_conflicts_deterministically():
    grouped, conflicts = prepare_chunk(_market_rows())

    assert len(grouped) == 1
    assert conflicts == 1
    assert grouped.iloc[0]["temperature"] == 30
    assert bool(grouped.iloc[0]["is_heatwave"]) is True
    assert grouped.iloc[0]["modal_price"] == 105


def test_prepare_chunk_preserves_original_market_rows_without_climate():
    grouped, conflicts = prepare_chunk(_market_rows(with_climate=False))

    assert len(grouped) == 1
    assert conflicts == 0
    assert pd.isna(grouped.iloc[0]["temperature"])
