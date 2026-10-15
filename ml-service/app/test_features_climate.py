from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _rows(climate: bool):
    rows = []
    start = date(2025, 1, 1)
    for index in range(35):
        current = start + timedelta(days=index)
        values = (28.0, 5.0, 0.6, 4.0, False, False, False) if climate else (None,) * 7
        rows.append((current, "Abohar", "Onion", "Onion", 100.0 + index, 10.0, *values))
    return rows


def _client_with_rows(rows):
    from app.main import app

    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.__enter__.return_value = connection
    return app, connection


def test_features_reports_climate_available_when_database_values_are_complete():
    app, connection = _client_with_rows(_rows(climate=True))
    with patch("app.main.DATABASE_URL", "postgresql://test"), patch("app.main.psycopg.connect", return_value=connection):
        response = TestClient(app).post("/features", json={
            "commodity": "Onion", "market": "Abohar", "variety": "Onion", "horizon": 7, "features": {}
        })
    assert response.status_code == 200
    assert response.json()["climate_available"] is True
    assert response.json()["climate_status"] == "evaluated"
    assert response.json()["features"]["temperature"] == 28.0


def test_features_reports_climate_unavailable_without_database_values():
    app, connection = _client_with_rows(_rows(climate=False))
    with patch("app.main.DATABASE_URL", "postgresql://test"), patch("app.main.psycopg.connect", return_value=connection):
        response = TestClient(app).post("/features", json={
            "commodity": "Onion", "market": "Abohar", "variety": "Onion", "horizon": 7, "features": {}
        })
    assert response.status_code == 200
    assert response.json()["climate_available"] is False
    assert response.json()["climate_status"] == "not_evaluated"
    assert "temperature" not in response.json()["features"]
