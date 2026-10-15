"""
Integration tests for anomaly detection in prediction flow
========================================================

Tests that ClimateAnomalyDetector and MarketDataAnomalyDetector are
properly integrated into the live prediction endpoint.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import joblib
import numpy as np
from pathlib import Path


class TestPredictionAnomalyIntegration:
    """Test anomaly detection integration in predictions."""
    
    @pytest.fixture
    def mock_artifact(self):
        """Create a mock model artifact."""
        return {
            "model": MagicMock(predict=lambda x: np.array([1500.0])),
            "features": ["lag_1", "lag_2", "lag_3", "rolling_mean_7", "rolling_mean_14"],
            "feature_means": [1000.0, 1000.0, 1000.0, 1000.0, 1000.0],
            "feature_scales": [500.0, 500.0, 500.0, 500.0, 500.0],
            "model_uncertainty": 0.25,
            "drift_score": 0.0,
            "metadata": {"commodity": "Onion"},
        }
    
    @pytest.fixture
    def client(self, mock_artifact):
        """Create test client with mocked model."""
        from app.main import app
        
        with patch('joblib.load', return_value=mock_artifact):
            with patch('app.main.DATABASE_URL', None):  # Disable DB for tests
                with TestClient(app) as test_client:
                    yield test_client
    
    def test_normal_conditions_no_climate(self, client):
        """Test prediction with normal conditions and no climate data."""
        response = client.post("/predict", json={
            "commodity": "Onion",
            "market": "Abohar",
            "variety": "Onion",
            "horizon": 7,
            "features": {
                "lag_1": 1500.0,
                "lag_2": 1450.0,
                "lag_3": 1400.0,
                "arrival_lag_1": 50.0,
                "rolling_mean_7": 1480.0,
                "rolling_mean_14": 1460.0,
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify decision structure
        assert "decision" in data
        assert "signals" in data
        assert "anomaly_detection" in data
        
        # Verify climate is marked as unavailable
        assert data["anomaly_detection"]["climate_available"] is False
        assert data["anomaly_detection"]["climate_anomaly"] is None
        
        # Verify market data anomaly was computed
        assert data["anomaly_detection"]["market_data_anomaly"] is not None
        assert "score" in data["anomaly_detection"]["market_data_anomaly"]
        assert "reason" in data["anomaly_detection"]["market_data_anomaly"]
        
        # Normal price should have low anomaly score
        assert data["anomaly_detection"]["market_data_anomaly"]["score"] < 0.5
    
    def test_anomalous_price(self, client):
        """Test prediction with anomalous (extreme) price."""
        response = client.post("/predict", json={
            "commodity": "Onion",
            "market": "Abohar",
            "variety": "Onion",
            "horizon": 7,
            "features": {
                "lag_1": 100000.0,  # Extreme price
                "lag_2": 1450.0,
                "lag_3": 1400.0,
                "arrival_lag_1": 50.0,
                "rolling_mean_7": 1480.0,
                "rolling_mean_14": 1460.0,
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify market data anomaly is high
        assert data["anomaly_detection"]["market_data_anomaly"]["score"] >= 0.5
        assert "price" in data["anomaly_detection"]["market_data_anomaly"]["reason"].lower()
    
    def test_with_climate_data_normal(self, client):
        """Test prediction with normal climate data."""
        response = client.post("/predict", json={
            "commodity": "Onion",
            "market": "Abohar",
            "variety": "Onion",
            "horizon": 7,
            "features": {
                "lag_1": 1500.0,
                "lag_2": 1450.0,
                "lag_3": 1400.0,
                "arrival_lag_1": 50.0,
                "rolling_mean_7": 1480.0,
                "rolling_mean_14": 1460.0,
                "temperature": 28.0,  # Normal temperature
                "rainfall": 5.0,  # Normal rainfall
                "humidity": 0.6,  # Normal humidity
                "wind_speed": 5.0,
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify climate is marked as available
        assert data["anomaly_detection"]["climate_available"] is True
        assert data["anomaly_detection"]["climate_anomaly"] is not None
        
        # Normal weather should have low anomaly score
        assert data["anomaly_detection"]["climate_anomaly"]["score"] < 0.5
        assert data["anomaly_detection"]["climate_anomaly"]["severity"] in ["LOW", "MODERATE"]
    
    def test_with_climate_data_heatwave(self, client):
        """Test prediction with heatwave conditions."""
        response = client.post("/predict", json={
            "commodity": "Onion",
            "market": "Abohar",
            "variety": "Onion",
            "horizon": 7,
            "features": {
                "lag_1": 1500.0,
                "lag_2": 1450.0,
                "lag_3": 1400.0,
                "arrival_lag_1": 50.0,
                "rolling_mean_7": 1480.0,
                "rolling_mean_14": 1460.0,
                "temperature": 45.0,  # Extreme heat
                "rainfall": 0.0,
                "humidity": 0.3,
                "wind_speed": 3.0,
                "is_heatwave": True,
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify climate anomaly is high
        assert data["anomaly_detection"]["climate_available"] is True
        assert data["anomaly_detection"]["climate_anomaly"]["score"] >= 0.5
        assert data["anomaly_detection"]["climate_anomaly"]["severity"] in ["HIGH", "CRITICAL"]
        assert "heatwave" in data["anomaly_detection"]["climate_anomaly"]["reason"].lower() or "temperature" in data["anomaly_detection"]["climate_anomaly"]["reason"].lower()
    
    def test_with_climate_data_heavy_rain(self, client):
        """Test prediction with heavy rainfall."""
        response = client.post("/predict", json={
            "commodity": "Onion",
            "market": "Abohar",
            "variety": "Onion",
            "horizon": 7,
            "features": {
                "lag_1": 1500.0,
                "lag_2": 1450.0,
                "lag_3": 1400.0,
                "arrival_lag_1": 50.0,
                "rolling_mean_7": 1480.0,
                "rolling_mean_14": 1460.0,
                "temperature": 28.0,
                "rainfall": 150.0,  # Heavy rain
                "humidity": 0.9,
                "wind_speed": 8.0,
                "is_heavy_rain": True,
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify climate anomaly is elevated
        assert data["anomaly_detection"]["climate_available"] is True
        assert data["anomaly_detection"]["climate_anomaly"]["score"] >= 0.5
    
    def test_partial_climate_data(self, client):
        """Test prediction with partial climate data (should not trigger detector)."""
        response = client.post("/predict", json={
            "commodity": "Onion",
            "market": "Abohar",
            "variety": "Onion",
            "horizon": 7,
            "features": {
                "lag_1": 1500.0,
                "lag_2": 1450.0,
                "lag_3": 1400.0,
                "arrival_lag_1": 50.0,
                "rolling_mean_7": 1480.0,
                "rolling_mean_14": 1460.0,
                "temperature": 28.0,  # Only temperature, missing rain/humidity
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Partial climate data should not trigger detector
        assert data["anomaly_detection"]["climate_available"] is False
        assert data["anomaly_detection"]["climate_anomaly"] is None
    
    def test_anomaly_signals_influence_decision(self, client):
        """Test that high anomaly scores can influence the decision."""
        response = client.post("/predict", json={
            "commodity": "Onion",
            "market": "Abohar",
            "variety": "Onion",
            "horizon": 7,
            "features": {
                "lag_1": 100000.0,  # Extreme price
                "lag_2": 1450.0,
                "lag_3": 1400.0,
                "arrival_lag_1": 50.0,
                "rolling_mean_7": 1480.0,
                "rolling_mean_14": 1460.0,
                "temperature": 45.0,  # Extreme heat
                "rainfall": 150.0,  # Heavy rain
                "humidity": 0.9,
                "wind_speed": 8.0,
                "is_heatwave": True,
                "is_heavy_rain": True,
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify both anomalies are detected
        assert data["anomaly_detection"]["climate_available"] is True
        assert data["anomaly_detection"]["climate_anomaly"]["score"] >= 0.5
        assert data["anomaly_detection"]["market_data_anomaly"]["score"] >= 0.5
        
        # Verify signals include anomaly scores
        assert data["signals"]["climate_anomaly"] >= 0.5
        assert data["signals"]["market_data_anomaly"] >= 0.5
        
        # Verify decision reasons include anomalies if threshold exceeded
        if data["signals"]["climate_anomaly"] >= 0.5:
            assert any("climate" in reason.lower() for reason in data.get("reasons", []))

    def test_invalid_climate_data_is_not_evaluated_as_normal(self, client):
        response = client.post("/predict", json={
            "commodity": "Onion", "market": "Abohar", "variety": "Onion", "horizon": 7,
            "features": {
                "lag_1": 1500.0, "lag_2": 1450.0, "lag_3": 1400.0,
                "rolling_mean_7": 1480.0, "rolling_mean_14": 1460.0,
                "arrival_lag_1": 50.0, "temperature": 28.0, "rainfall": -1.0, "humidity": 0.6,
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["anomaly_detection"]["climate_status"] == "invalid_or_incomplete"
        assert data["anomaly_detection"]["climate_anomaly"] is None
        assert data["signals"]["climate_anomaly"] is None

    def test_invalid_market_arrivals_are_reported(self, client):
        response = client.post("/predict", json={
            "commodity": "Onion", "market": "Abohar", "variety": "Onion", "horizon": 7,
            "features": {
                "lag_1": 1500.0, "lag_2": 1450.0, "lag_3": 1400.0,
                "rolling_mean_7": 1480.0, "rolling_mean_14": 1460.0,
                "arrival_lag_1": -1.0,
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["anomaly_detection"]["market_data_status"] == "evaluated"
        assert data["anomaly_detection"]["market_data_anomaly"]["score"] >= 0.5
        assert "invalid_arrivals" in data["anomaly_detection"]["market_data_anomaly"]["reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
