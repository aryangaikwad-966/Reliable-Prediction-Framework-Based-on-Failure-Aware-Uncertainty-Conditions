from app.core import Signals, failure_risk, novelty_score, rolling_drift_score, selective_decision


def test_risk_is_bounded():
    signals = Signals(1, 1, 1, 1, 1, 1)
    assert failure_risk(signals) == 1.0


def test_abstention_withholds_prediction():
    result = selective_decision(500, Signals(1, 1, 1, 1, 1, 1))
    assert result["decision"] == "ABSTAINED"
    assert result["prediction"] is None


def test_novelty_and_drift_are_computable():
    assert 0 <= novelty_score([10, 12], [10, 10], [1, 2]) <= 1
    assert rolling_drift_score([10, 12], [2, 2]) > 0