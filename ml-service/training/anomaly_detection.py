"""
Anomaly Detection Modules for Failure-Aware Prediction
======================================================

Implements four types of anomaly detection:
1. Climate anomalies (temperature, rainfall, humidity, extreme weather)
2. Market-data anomalies (prices, arrivals, data quality)
3. Feature/distribution anomalies (novelty, drift)
4. Prediction-error anomalies (historical failures)

Each module returns structured anomaly information with scores and evidence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AnomalyResult:
    """Structured result from anomaly detection."""
    anomaly_type: str
    is_anomaly: bool
    score: float  # 0-1, higher = more anomalous
    severity: str  # "LOW", "MODERATE", "HIGH", "CRITICAL"
    evidence: Dict
    reason: str


class ClimateAnomalyDetector:
    """
    Detects climate anomalies based on historical baselines and extreme indicators.
    
    Uses seasonal baselines and robust statistics to identify unusual weather.
    """
    
    def __init__(self, historical_baseline: Optional[pd.DataFrame] = None):
        """
        Initialize with historical climate data for baseline computation.
        
        Args:
            historical_baseline: DataFrame with columns: date, latitude, longitude,
                               temperature, rainfall, humidity, wind_speed
        """
        self.baseline = historical_baseline
        self.baseline_stats = {}
        
        if historical_baseline is not None:
            self._compute_baselines()
    
    def _compute_baselines(self):
        """Compute seasonal baselines from historical data."""
        if self.baseline is None or len(self.baseline) == 0:
            return
        
        # Group by month and latitude zone for seasonal baselines
        self.baseline["month"] = pd.to_datetime(self.baseline["date"]).dt.month
        self.baseline["lat_zone"] = pd.cut(
            self.baseline["latitude"], 
            bins=[0, 15, 20, 90], 
            labels=["south", "central", "north"]
        )
        
        for (month, zone), group in self.baseline.groupby(["month", "lat_zone"]):
            key = f"{month}_{zone}"
            self.baseline_stats[key] = {
                "temp_mean": group["temperature"].mean(),
                "temp_std": group["temperature"].std(),
                "rain_p95": group["rainfall"].quantile(0.95),
                "rain_p99": group["rainfall"].quantile(0.99),
                "humidity_mean": group["humidity"].mean(),
                "humidity_std": group["humidity"].std(),
            }
    
    def detect(
        self,
        current_weather: Dict,
        use_defaults: bool = True
    ) -> AnomalyResult:
        """
        Detect climate anomalies for current weather conditions.
        
        Args:
            current_weather: Dict with temperature, rainfall, humidity, wind_speed,
                           date, latitude, and extreme flags
            use_defaults: If True, use reasonable defaults when no baseline available
        
        Returns:
            AnomalyResult with climate anomaly information
        """
        date = pd.to_datetime(current_weather["date"])
        month = date.month
        lat = current_weather["latitude"]
        
        # Determine latitude zone
        if lat > 20:
            zone = "north"
        elif lat > 15:
            zone = "central"
        else:
            zone = "south"
        
        key = f"{month}_{zone}"
        stats = self.baseline_stats.get(key)
        
        # Compute anomaly scores
        scores = []
        evidence = {}
        
        # Temperature anomaly
        temp = current_weather["temperature"]
        if stats and stats["temp_std"] > 0:
            temp_z = abs(temp - stats["temp_mean"]) / stats["temp_std"]
            temp_anomaly = min(temp_z / 3.0, 1.0)  # Cap at 3 sigma
        else:
            # Use default ranges
            temp_anomaly = 0.0
            if temp < 10 or temp > 45:
                temp_anomaly = 0.8
        
        scores.append(temp_anomaly)
        evidence["temperature_z_score"] = temp_z if stats else None
        evidence["temperature_anomaly_score"] = temp_anomaly
        
        # Rainfall anomaly
        rain = current_weather["rainfall"]
        if stats:
            rain_anomaly = 0.0
            if rain > stats["rain_p95"]:
                rain_anomaly = 0.5
            if rain > stats["rain_p99"]:
                rain_anomaly = 1.0
        else:
            # Use default threshold
            rain_anomaly = 1.0 if rain > 100 else (0.5 if rain > 50 else 0.0)
        
        scores.append(rain_anomaly)
        evidence["rainfall_anomaly_score"] = rain_anomaly
        
        # Humidity anomaly
        humidity = current_weather["humidity"]
        if stats and stats["humidity_std"] > 0:
            humid_z = abs(humidity - stats["humidity_mean"]) / stats["humidity_std"]
            humid_anomaly = min(humid_z / 2.5, 1.0)
        else:
            humid_anomaly = 0.0
            if humidity < 0.2 or humidity > 0.95:
                humid_anomaly = 0.6
        
        scores.append(humid_anomaly)
        evidence["humidity_anomaly_score"] = humid_anomaly
        
        # Extreme weather flags
        extreme_flags = []
        if current_weather.get("is_heatwave", False):
            extreme_flags.append("heatwave")
            scores.append(0.9)
        if current_weather.get("is_coldwave", False):
            extreme_flags.append("coldwave")
            scores.append(0.8)
        if current_weather.get("is_heavy_rain", False):
            extreme_flags.append("heavy_rain")
            scores.append(0.85)
        
        evidence["extreme_flags"] = extreme_flags
        
        # Overall climate anomaly score
        if scores:
            overall_score = max(scores)  # Most severe anomaly
        else:
            overall_score = 0.0
        
        # Determine severity
        if overall_score >= 0.9:
            severity = "CRITICAL"
        elif overall_score >= 0.7:
            severity = "HIGH"
        elif overall_score >= 0.5:
            severity = "MODERATE"
        else:
            severity = "LOW"
        
        # Generate reason
        reasons = []
        if temp_anomaly >= 0.5:
            reasons.append(f"Unusual temperature ({temp:.1f}°C)")
        if rain_anomaly >= 0.5:
            reasons.append(f"High rainfall ({rain:.1f}mm)")
        if humid_anomaly >= 0.5:
            reasons.append(f"Unusual humidity ({humidity:.1%})")
        if extreme_flags:
            reasons.append(f"Extreme weather: {', '.join(extreme_flags)}")
        
        reason = "; ".join(reasons) if reasons else "Normal weather conditions"
        
        return AnomalyResult(
            anomaly_type="climate",
            is_anomaly=overall_score >= 0.5,
            score=overall_score,
            severity=severity,
            evidence=evidence,
            reason=reason
        )


class MarketDataAnomalyDetector:
    """
    Detects anomalies in market data: prices, arrivals, and data quality issues.
    """
    
    def __init__(self, historical_data: Optional[pd.DataFrame] = None):
        """
        Initialize with historical market data for baseline computation.
        
        Args:
            historical_data: DataFrame with modal_price, arrivals_tonnes, etc.
        """
        self.historical = historical_data
        self.price_stats = {}
        self.arrival_stats = {}
        
        if historical_data is not None:
            self._compute_baselines()
    
    def _compute_baselines(self):
        """Compute baselines from historical market data."""
        if self.historical is None or len(self.historical) == 0:
            return
        
        # Price statistics by commodity
        for commodity, group in self.historical.groupby("commodity"):
            self.price_stats[commodity] = {
                "mean": group["modal_price"].mean(),
                "std": group["modal_price"].std(),
                "p05": group["modal_price"].quantile(0.05),
                "p95": group["modal_price"].quantile(0.95),
            }
        
        # Arrival statistics
        self.arrival_stats = {
            "mean": self.historical["arrivals_tonnes"].mean(),
            "std": self.historical["arrivals_tonnes"].std(),
            "p95": self.historical["arrivals_tonnes"].quantile(0.95),
        }
    
    def detect(
        self,
        current_data: Dict,
        commodity: str,
        quality_flags: Optional[Dict] = None
    ) -> AnomalyResult:
        """
        Detect market data anomalies.
        
        Args:
            current_data: Dict with modal_price, arrivals_tonnes
            commodity: Commodity name
            quality_flags: Optional dict with quality flags from enrichment
        
        Returns:
            AnomalyResult with market anomaly information
        """
        scores = []
        evidence = {}
        
        # Price anomaly
        price = current_data.get("modal_price")
        if price and price > 0:
            stats = self.price_stats.get(commodity)
            if stats and stats["std"] > 0:
                price_z = abs(price - stats["mean"]) / stats["std"]
                price_anomaly = min(price_z / 3.0, 1.0)
            else:
                # Use reasonable bounds for Indian APMC prices
                price_anomaly = 0.0
                if price < 100 or price > 50000:
                    price_anomaly = 0.9
                elif price < 500 or price > 20000:
                    price_anomaly = 0.5
            
            scores.append(price_anomaly)
            evidence["price_anomaly_score"] = price_anomaly
            evidence["price_value"] = price
        
        # Arrival anomaly
        arrivals = current_data.get("arrivals_tonnes")
        if arrivals is not None and arrivals >= 0:
            stats = self.arrival_stats
            if stats and stats["std"] > 0:
                arrival_z = abs(arrivals - stats["mean"]) / stats["std"]
                arrival_anomaly = min(arrival_z / 3.0, 1.0)
            else:
                arrival_anomaly = 0.0
                if arrivals > 10000:
                    arrival_anomaly = 0.6
            
            scores.append(arrival_anomaly)
            evidence["arrival_anomaly_score"] = arrival_anomaly
            evidence["arrival_value"] = arrivals
        
        # Quality flag anomalies
        quality_anomalies = []
        if quality_flags:
            if quality_flags.get("quality_invalid_price", False):
                quality_anomalies.append("invalid_price")
                scores.append(0.9)
            if quality_flags.get("quality_invalid_arrivals", False):
                quality_anomalies.append("invalid_arrivals")
                scores.append(0.8)
            if quality_flags.get("quality_conflicting_duplicate", False):
                quality_anomalies.append("conflicting_duplicate")
                scores.append(0.7)
            if quality_flags.get("quality_missing_critical_input", False):
                quality_anomalies.append("missing_input")
                scores.append(0.6)
        
        evidence["quality_anomalies"] = quality_anomalies
        
        # Overall score
        overall_score = max(scores) if scores else 0.0
        
        # Severity
        if overall_score >= 0.9:
            severity = "CRITICAL"
        elif overall_score >= 0.7:
            severity = "HIGH"
        elif overall_score >= 0.5:
            severity = "MODERATE"
        else:
            severity = "LOW"
        
        # Reason
        reasons = []
        if price_anomaly >= 0.5:
            reasons.append(f"Unusual price ({price:.0f} Rs/Quintal)")
        if arrival_anomaly >= 0.5:
            reasons.append(f"Unusual arrivals ({arrivals:.1f} Tonnes)")
        if quality_anomalies:
            reasons.append(f"Data quality issues: {', '.join(quality_anomalies)}")
        
        reason = "; ".join(reasons) if reasons else "Normal market data"
        
        return AnomalyResult(
            anomaly_type="market_data",
            is_anomaly=overall_score >= 0.5,
            score=overall_score,
            severity=severity,
            evidence=evidence,
            reason=reason
        )


class FeatureDistributionAnomalyDetector:
    """
    Detects novelty and distribution shift in feature space.
    """
    
    def __init__(self, training_features: pd.DataFrame):
        """
        Initialize with training feature data.
        
        Args:
            training_features: DataFrame with feature columns only
        """
        self.training_mean = training_features.mean()
        self.training_std = training_features.std().replace(0, 1)
        self.training_features = training_features
    
    def detect(
        self,
        current_features: np.ndarray,
        feature_names: List[str]
    ) -> AnomalyResult:
        """
        Detect feature distribution anomalies (novelty/OOD).
        
        Args:
            current_features: Array of current feature values
            feature_names: List of feature names matching training columns
        
        Returns:
            AnomalyResult with novelty information
        """
        # Convert to Series for easier computation
        current_series = pd.Series(current_features, index=feature_names)
        
        # Align with training features
        aligned_mean = self.training_mean[current_series.index]
        aligned_std = self.training_std[current_series.index]
        
        # Compute standardized distances
        z_scores = np.abs((current_series - aligned_mean) / aligned_std)
        
        # Novelty score: mean standardized distance
        novelty_score = z_scores.mean()
        # Normalize to 0-1
        novelty_score_normalized = min(novelty_score / 3.0, 1.0)
        
        # Individual feature anomalies
        feature_anomalies = z_scores[z_scores > 2.0].to_dict()
        
        evidence = {
            "novelty_score": float(novelty_score),
            "max_z_score": float(z_scores.max()),
            "anomalous_features": {k: float(v) for k, v in feature_anomalies.items()},
            "feature_count": len(feature_names),
        }
        
        # Severity
        if novelty_score_normalized >= 0.8:
            severity = "CRITICAL"
        elif novelty_score_normalized >= 0.6:
            severity = "HIGH"
        elif novelty_score_normalized >= 0.4:
            severity = "MODERATE"
        else:
            severity = "LOW"
        
        # Reason
        if len(feature_anomalies) > 0:
            top_anomalies = sorted(feature_anomalies.items(), key=lambda x: x[1], reverse=True)[:3]
            reason = f"Unusual feature values: {', '.join([f'{k} (z={v:.1f})' for k, v in top_anomalies])}"
        else:
            reason = "Normal feature distribution"
        
        return AnomalyResult(
            anomaly_type="feature_distribution",
            is_anomaly=novelty_score_normalized >= 0.4,
            score=novelty_score_normalized,
            severity=severity,
            evidence=evidence,
            reason=reason
        )


class PredictionErrorAnomalyDetector:
    """
    Detects historical prediction errors and associates with conditions.
    """
    
    def __init__(self, failure_memory: Optional[pd.DataFrame] = None):
        """
        Initialize with failure memory from historical predictions.
        
        Args:
            failure_memory: DataFrame with prediction outcomes and errors
        """
        self.failure_memory = failure_memory
        self.failure_rate = 0.0
        self.error_distribution = {}
        
        if failure_memory is not None and len(failure_memory) > 0:
            self._compute_statistics()
    
    def _compute_statistics(self):
        """Compute failure statistics from memory."""
        if self.failure_memory is None:
            return
        
        total = len(self.failure_memory)
        failures = self.failure_memory[self.failure_memory["absolute_error"] > 300].shape[0]
        self.failure_rate = failures / total if total > 0 else 0.0
        
        # Error distribution by market
        if "market_code" in self.failure_memory.columns:
            self.error_distribution = self.failure_memory.groupby("market_code")["absolute_error"].mean().to_dict()
    
    def detect(
        self,
        market_code: str,
        historical_context: Optional[Dict] = None
    ) -> AnomalyResult:
        """
        Detect if current context is associated with high historical failure risk.
        
        Args:
            market_code: Market identifier
            historical_context: Optional additional context
        
        Returns:
            AnomalyResult with historical failure risk information
        """
        # Get market-specific failure rate
        market_error = self.error_distribution.get(market_code, 0)
        
        # Normalize to 0-1 score (assuming 300 Rs/Quintal is high error)
        error_score = min(market_error / 300.0, 1.0)
        
        # Combine with global failure rate
        combined_score = 0.7 * error_score + 0.3 * self.failure_rate
        
        evidence = {
            "market_code": market_code,
            "market_mean_error": float(market_error),
            "global_failure_rate": float(self.failure_rate),
            "error_score": float(error_score),
        }
        
        # Severity
        if combined_score >= 0.7:
            severity = "HIGH"
        elif combined_score >= 0.5:
            severity = "MODERATE"
        else:
            severity = "LOW"
        
        # Reason
        if combined_score >= 0.5:
            reason = f"High historical error rate for this market ({market_error:.0f} Rs/Quintal mean error)"
        else:
            reason = "Normal historical performance"
        
        return AnomalyResult(
            anomaly_type="prediction_error",
            is_anomaly=combined_score >= 0.5,
            score=combined_score,
            severity=severity,
            evidence=evidence,
            reason=reason
        )


class AnomalyAggregator:
    """
    Aggregates multiple anomaly types into a combined risk assessment.
    """
    
    def __init__(self):
        self.detectors = {}
    
    def register_detector(self, name: str, detector):
        """Register an anomaly detector."""
        self.detectors[name] = detector
    
    def detect_all(self, context: Dict) -> Dict[str, AnomalyResult]:
        """
        Run all registered detectors and return results.
        
        Args:
            context: Dict with all necessary data for detectors
        
        Returns:
            Dict mapping detector names to AnomalyResults
        """
        results = {}
        for name, detector in self.detectors.items():
            try:
                # Each detector has its own interface
                if isinstance(detector, ClimateAnomalyDetector):
                    results[name] = detector.detect(context.get("weather", {}))
                elif isinstance(detector, MarketDataAnomalyDetector):
                    results[name] = detector.detect(
                        context.get("market_data", {}),
                        context.get("commodity", ""),
                        context.get("quality_flags")
                    )
                elif isinstance(detector, FeatureDistributionAnomalyDetector):
                    results[name] = detector.detect(
                        context.get("features", np.array([])),
                        context.get("feature_names", [])
                    )
                elif isinstance(detector, PredictionErrorAnomalyDetector):
                    results[name] = detector.detect(
                        context.get("market_code", ""),
                        context.get("historical_context")
                    )
                else:
                    # Generic detector with detect method
                    if hasattr(detector, 'detect'):
                        results[name] = detector.detect(context)
                    else:
                        results[name] = AnomalyResult(
                            anomaly_type=name,
                            is_anomaly=False,
                            score=0.0,
                            severity="LOW",
                            evidence={},
                            reason="Detector has no detect method"
                        )
            except Exception as e:
                # Return error result without crashing
                results[name] = AnomalyResult(
                    anomaly_type=name,
                    is_anomaly=False,
                    score=0.0,
                    severity="LOW",
                    evidence={"error": str(e)},
                    reason=f"Detection failed: {str(e)}"
                )
        
        return results
    
    def get_combined_score(self, results: Dict[str, AnomalyResult]) -> float:
        """
        Compute combined anomaly score from all detectors.
        
        Args:
            results: Dict of AnomalyResults
        
        Returns:
            Combined score 0-1
        """
        if not results:
            return 0.0
        
        scores = [r.score for r in results.values()]
        # Use max for risk assessment (worst case)
        return max(scores)
    
    def get_severity_summary(self, results: Dict[str, AnomalyResult]) -> Dict[str, int]:
        """
        Count anomalies by severity level.
        
        Args:
            results: Dict of AnomalyResults
        
        Returns:
            Dict with counts for each severity level
        """
        summary = {"LOW": 0, "MODERATE": 0, "HIGH": 0, "CRITICAL": 0}
        for result in results.values():
            if result.is_anomaly:
                summary[result.severity] += 1
        return summary
