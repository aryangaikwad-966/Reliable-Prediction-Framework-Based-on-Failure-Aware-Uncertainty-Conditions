"""
Tests for Anomaly Detection Modules
===================================

Tests for climate, market-data, feature distribution, and prediction-error anomaly detection.
"""

import pytest
import numpy as np
import pandas as pd
from training.anomaly_detection import (
    ClimateAnomalyDetector,
    MarketDataAnomalyDetector,
    FeatureDistributionAnomalyDetector,
    PredictionErrorAnomalyDetector,
    AnomalyAggregator,
    AnomalyResult,
)


class TestClimateAnomalyDetector:
    """Test climate anomaly detection."""
    
    def test_detect_normal_weather(self):
        """Detection with normal weather conditions."""
        detector = ClimateAnomalyDetector()
        weather = {
            "date": "2025-03-15",
            "latitude": 20.0,
            "longitude": 78.0,
            "temperature": 28.0,
            "rainfall": 5.0,
            "humidity": 0.6,
            "wind_speed": 5.0,
            "is_heatwave": False,
            "is_coldwave": False,
            "is_heavy_rain": False,
        }
        result = detector.detect(weather)
        assert result.anomaly_type == "climate"
        assert result.score < 0.5  # Normal weather should have low score
        assert result.severity in ["LOW", "MODERATE"]
    
    def test_detect_heatwave(self):
        """Detection with heatwave conditions."""
        detector = ClimateAnomalyDetector()
        weather = {
            "date": "2025-05-15",
            "latitude": 20.0,
            "longitude": 78.0,
            "temperature": 45.0,
            "rainfall": 0.0,
            "humidity": 0.3,
            "wind_speed": 3.0,
            "is_heatwave": True,
            "is_coldwave": False,
            "is_heavy_rain": False,
        }
        result = detector.detect(weather)
        assert result.is_anomaly
        assert result.score >= 0.5
        assert "heatwave" in result.reason.lower() or "temperature" in result.reason.lower()
    
    def test_detect_heavy_rain(self):
        """Detection with heavy rainfall."""
        detector = ClimateAnomalyDetector()
        weather = {
            "date": "2025-07-15",
            "latitude": 20.0,
            "longitude": 78.0,
            "temperature": 28.0,
            "rainfall": 150.0,
            "humidity": 0.9,
            "wind_speed": 8.0,
            "is_heatwave": False,
            "is_coldwave": False,
            "is_heavy_rain": True,
        }
        result = detector.detect(weather)
        assert result.is_anomaly
        assert result.score >= 0.5
    
    def test_with_historical_baseline(self):
        """Detection with historical baseline."""
        # Create historical data with matching lengths
        n = 365
        historical = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=n),
            "latitude": [20.0] * n,
            "longitude": [78.0] * n,
            "temperature": np.random.normal(28, 5, n),
            "rainfall": np.random.exponential(20, n),
            "humidity": np.random.normal(0.6, 0.1, n),
            "wind_speed": np.random.gamma(2, 2.5, n),
        })
        
        detector = ClimateAnomalyDetector(historical)
        weather = {
            "date": "2025-03-15",
            "latitude": 20.0,
            "longitude": 78.0,
            "temperature": 28.0,
            "rainfall": 5.0,
            "humidity": 0.6,
            "wind_speed": 5.0,
            "is_heatwave": False,
            "is_coldwave": False,
            "is_heavy_rain": False,
        }
        result = detector.detect(weather)
        assert result.anomaly_type == "climate"
        assert 0 <= result.score <= 1


class TestMarketDataAnomalyDetector:
    """Test market data anomaly detection."""
    
    def test_detect_normal_prices(self):
        """Detection with normal prices."""
        detector = MarketDataAnomalyDetector()
        data = {"modal_price": 1500.0, "arrivals_tonnes": 50.0}
        result = detector.detect(data, "Onion")
        assert result.anomaly_type == "market_data"
        assert result.score < 0.5
    
    def test_detect_extreme_price(self):
        """Detection with extreme price."""
        detector = MarketDataAnomalyDetector()
        data = {"modal_price": 100000.0, "arrivals_tonnes": 50.0}
        result = detector.detect(data, "Onion")
        assert result.is_anomaly
        assert result.score >= 0.5
        assert "price" in result.reason.lower()
    
    def test_detect_quality_flags(self):
        """Detection with quality flag anomalies."""
        detector = MarketDataAnomalyDetector()
        data = {"modal_price": 1500.0, "arrivals_tonnes": 50.0}
        quality_flags = {
            "quality_invalid_price": True,
            "quality_conflicting_duplicate": False,
        }
        result = detector.detect(data, "Onion", quality_flags)
        assert result.is_anomaly
        assert "quality" in result.reason.lower()
    
    def test_with_historical_baseline(self):
        """Detection with historical baseline."""
        historical = pd.DataFrame({
            "commodity": ["Onion"] * 100,
            "modal_price": np.random.normal(1500, 300, 100),
            "arrivals_tonnes": np.random.exponential(50, 100),
        })
        
        detector = MarketDataAnomalyDetector(historical)
        data = {"modal_price": 1500.0, "arrivals_tonnes": 50.0}
        result = detector.detect(data, "Onion")
        assert result.anomaly_type == "market_data"


class TestFeatureDistributionAnomalyDetector:
    """Test feature distribution anomaly detection."""
    
    def test_detect_normal_features(self):
        """Detection with normal feature distribution."""
        training = pd.DataFrame({
            "feat_1": np.random.normal(0, 1, 1000),
            "feat_2": np.random.normal(0, 1, 1000),
            "feat_3": np.random.normal(0, 1, 1000),
        })
        
        detector = FeatureDistributionAnomalyDetector(training)
        current = np.array([0.0, 0.0, 0.0])
        result = detector.detect(current, ["feat_1", "feat_2", "feat_3"])
        
        assert result.anomaly_type == "feature_distribution"
        assert result.score < 0.5  # Normal features should have low novelty
    
    def test_detect_anomalous_features(self):
        """Detection with anomalous features."""
        training = pd.DataFrame({
            "feat_1": np.random.normal(0, 1, 1000),
            "feat_2": np.random.normal(0, 1, 1000),
            "feat_3": np.random.normal(0, 1, 1000),
        })
        
        detector = FeatureDistributionAnomalyDetector(training)
        current = np.array([5.0, 5.0, 5.0])  # Far from training distribution
        result = detector.detect(current, ["feat_1", "feat_2", "feat_3"])
        
        assert result.is_anomaly
        assert result.score >= 0.4


class TestPredictionErrorAnomalyDetector:
    """Test prediction error anomaly detection."""
    
    def test_detect_normal_performance(self):
        """Detection with normal historical performance."""
        detector = PredictionErrorAnomalyDetector()
        result = detector.detect("market_123")
        assert result.anomaly_type == "prediction_error"
        assert result.score < 0.5  # No history means low risk
    
    def test_detect_high_error_market(self):
        """Detection with high historical error."""
        failure_memory = pd.DataFrame({
            "market_code": ["market_123"] * 50,
            "absolute_error": np.random.normal(500, 100, 50),  # High errors
        })
        
        detector = PredictionErrorAnomalyDetector(failure_memory)
        result = detector.detect("market_123")
        
        assert result.anomaly_type == "prediction_error"
        assert result.evidence["market_mean_error"] > 0


class TestAnomalyAggregator:
    """Test anomaly aggregation."""
    
    def test_aggregate_multiple_detectors(self):
        """Test aggregating results from multiple detectors."""
        aggregator = AnomalyAggregator()
        
        # Register detectors with correct types
        climate_detector = ClimateAnomalyDetector()
        market_detector = MarketDataAnomalyDetector()
        
        aggregator.register_detector("climate", climate_detector)
        aggregator.register_detector("market", market_detector)
        
        context = {
            "weather": {
                "date": "2025-03-15",
                "latitude": 20.0,
                "longitude": 78.0,
                "temperature": 28.0,
                "rainfall": 5.0,
                "humidity": 0.6,
                "wind_speed": 5.0,
                "is_heatwave": False,
                "is_coldwave": False,
                "is_heavy_rain": False,
            },
            "market_data": {"modal_price": 1500.0, "arrivals_tonnes": 50.0},
            "commodity": "Onion",
        }
        
        results = aggregator.detect_all(context)
        
        assert "climate" in results
        assert "market" in results
        assert len(results) == 2
    
    def test_combined_score(self):
        """Test combined score calculation."""
        aggregator = AnomalyAggregator()
        
        results = {
            "detector1": AnomalyResult("mock", True, 0.8, "HIGH", {}, "High anomaly"),
            "detector2": AnomalyResult("mock", False, 0.3, "LOW", {}, "Low anomaly"),
        }
        
        combined = aggregator.get_combined_score(results)
        assert combined == 0.8  # Should take max
    
    def test_severity_summary(self):
        """Test severity summary."""
        aggregator = AnomalyAggregator()
        
        results = {
            "detector1": AnomalyResult("mock", True, 0.8, "HIGH", {}, "High"),
            "detector2": AnomalyResult("mock", True, 0.9, "CRITICAL", {}, "Critical"),
            "detector3": AnomalyResult("mock", False, 0.3, "LOW", {}, "Low"),
        }
        
        summary = aggregator.get_severity_summary(results)
        assert summary["HIGH"] == 1
        assert summary["CRITICAL"] == 1
        assert summary["LOW"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
