from app.core import Signals, failure_risk, novelty_score, rolling_drift_score, selective_decision


def test_risk_is_bounded():
    signals = Signals(1, 1, 1, 1, 1, 1, 1, 1)
    assert failure_risk(signals) == 1.0


def test_abstention_withholds_prediction():
    result = selective_decision(500, Signals(1, 1, 1, 1, 1, 1))
    assert result["decision"] == "ABSTAINED"
    assert result["prediction"] is None
    assert "RELIABILITY_BELOW_THRESHOLD" in result["reason_codes"]
    assert "MODEL_UNCERTAINTY_ELEVATED" in result["reason_codes"]


def test_acceptance_reports_its_actual_reliability_rule():
    result = selective_decision(500, Signals(0, 0, 0, 0, 0, 0))
    assert result["decision"] == "ACCEPTED"
    assert result["reason_codes"] == ["RELIABILITY_AT_OR_ABOVE_THRESHOLD"]


def test_novelty_and_drift_are_computable():
    assert 0 <= novelty_score([10, 12], [10, 10], [1, 2]) <= 1
    assert rolling_drift_score([10, 12], [2, 2]) > 0


# --- Prediction-specific reason code tests ---


def test_per_signal_reason_codes_emitted():
    """Each signal above its threshold should emit its specific reason code."""
    result = selective_decision(500, Signals(
        model_uncertainty=0.8,
        historical_failure_risk=0.7,
        novelty_score=0.9,
        drift_score=0.6,
        missing_information=0.5,
        context_risk=0.7,
    ))
    assert "MODEL_UNCERTAINTY_ELEVATED" in result["reason_codes"]
    assert "HISTORICAL_FAILURE_RISK_ELEVATED" in result["reason_codes"]
    assert "NOVELTY_SCORE_ELEVATED" in result["reason_codes"]
    assert "DRIFT_SCORE_ELEVATED" in result["reason_codes"]
    assert "MISSING_INFORMATION_ELEVATED" in result["reason_codes"]
    assert "CONTEXT_RISK_ELEVATED" in result["reason_codes"]


def test_only_triggered_signal_codes_emitted():
    """Only signals above their threshold should appear in reason_codes."""
    result = selective_decision(500, Signals(
        model_uncertainty=0.7,  # >= 0.60 → triggered
        historical_failure_risk=0.1,  # < 0.50 → not triggered
        novelty_score=0.1,
        drift_score=0.1,
        missing_information=0.1,
        context_risk=0.1,
    ))
    assert "MODEL_UNCERTAINTY_ELEVATED" in result["reason_codes"]
    assert "HISTORICAL_FAILURE_RISK_ELEVATED" not in result["reason_codes"]
    assert "NOVELTY_SCORE_ELEVATED" not in result["reason_codes"]
    assert "DRIFT_SCORE_ELEVATED" not in result["reason_codes"]
    assert "MISSING_INFORMATION_ELEVATED" not in result["reason_codes"]
    assert "CONTEXT_RISK_ELEVATED" not in result["reason_codes"]


def test_reason_codes_and_reasons_aligned():
    """reason_codes (excluding the primary threshold code) should be the same
    count as reasons, and both should refer to the same signals."""
    result = selective_decision(500, Signals(
        model_uncertainty=0.8,
        historical_failure_risk=0.6,
        novelty_score=0.1,
        drift_score=0.1,
        missing_information=0.1,
        context_risk=0.1,
    ))
    signal_codes = [c for c in result["reason_codes"]
                    if c not in ("RELIABILITY_AT_OR_ABOVE_THRESHOLD", "RELIABILITY_BELOW_THRESHOLD")]
    assert len(signal_codes) == len(result["reasons"])


def test_same_signals_same_reason_codes():
    """The same signal values should produce the same reason codes regardless
    of the base prediction value."""
    signals = Signals(0.7, 0.6, 0.3, 0.2, 0.1, 0.1)
    r1 = selective_decision(500, signals)
    r2 = selective_decision(600, signals)
    assert r1["reason_codes"] == r2["reason_codes"]
    assert r1["reasons"] == r2["reasons"]


def test_different_signals_different_reason_codes():
    """Different triggering conditions should produce different reason codes."""
    r1 = selective_decision(500, Signals(0.8, 0.1, 0.1, 0.1, 0.1, 0.1))
    r2 = selective_decision(500, Signals(0.1, 0.1, 0.8, 0.1, 0.1, 0.1))
    assert r1["reason_codes"] != r2["reason_codes"]
    assert r1["reasons"] != r2["reasons"]


def test_signals_in_response():
    """The response should include the actual signal values for evidence."""
    signals = Signals(0.25, 0.15, 0.30, 0.10, 0.0, 0.0)
    result = selective_decision(500, signals)
    assert result["signals"]["model_uncertainty"] == 0.25
    assert result["signals"]["historical_failure_risk"] == 0.15
    assert result["signals"]["novelty_score"] == 0.30
    assert result["signals"]["drift_score"] == 0.10
    assert result["signals"]["missing_information"] == 0.0
    assert result["signals"]["context_risk"] == 0.0


def test_threshold_boundary_behavior():
    """Signal exactly at the threshold should trigger the reason code."""
    # model_uncertainty threshold is 0.60
    result_at = selective_decision(500, Signals(0.60, 0, 0, 0, 0, 0))
    assert "MODEL_UNCERTAINTY_ELEVATED" in result_at["reason_codes"]
    # Just below threshold
    result_below = selective_decision(500, Signals(0.59, 0, 0, 0, 0, 0))
    assert "MODEL_UNCERTAINTY_ELEVATED" not in result_below["reason_codes"]
