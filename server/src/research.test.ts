import { describe, expect, it } from "vitest";
import { buildDecision, calculateRisk, classifyFailure, evaluateRegression, SIGNAL_RULES } from "./research";

describe("failure-aware decision engine", () => {
  it("maps weighted signals to bounded risk", () => {
    expect(calculateRisk({ modelUncertainty: 1, historicalFailureRisk: 1, noveltyScore: 1, driftScore: 1, missingInformation: 1, contextRisk: 1 })).toBe(1);
    expect(calculateRisk({ modelUncertainty: 0, historicalFailureRisk: 0, noveltyScore: 0, driftScore: 0, missingInformation: 0, contextRisk: 0 })).toBe(0);
  });

  it("withholds the prediction when reliability is below the threshold", () => {
    const result = buildDecision(500, { modelUncertainty: 1, historicalFailureRisk: 1, noveltyScore: 1, driftScore: 1, missingInformation: 1, contextRisk: 1 }, { reliabilityThreshold: 0.7 });
    expect(result.decision).toBe("ABSTAINED");
    expect(result.prediction).toBeNull();
    expect(result.reasons.length).toBeGreaterThan(0);
  });

  it("classifies configurable relative-error severity", () => {
    expect(classifyFailure(5, 0.06)).toBe("NORMAL");
    expect(classifyFailure(50, 0.3)).toBe("SIGNIFICANT");
    expect(classifyFailure(100, 0.7)).toBe("HIGH");
  });

  it("calculates regression metrics only for aligned observations", () => {
    const metrics = evaluateRegression([10, 20], [12, 18]);
    expect(metrics.mae).toBe(2);
    expect(metrics.rmse).toBe(2);
    expect(metrics.r2).toBeCloseTo(0.84);
    expect(evaluateRegression([], [])).toEqual({ mae: null, rmse: null, mape: null, r2: null });
  });
});

describe("reason codes from decision engine", () => {
  it("emits RELIABILITY_AT_OR_ABOVE_THRESHOLD for accepted decisions with no elevated signals", () => {
    const result = buildDecision(500, { modelUncertainty: 0, historicalFailureRisk: 0, noveltyScore: 0, driftScore: 0, missingInformation: 0, contextRisk: 0 });
    expect(result.decision).toBe("ACCEPTED");
    expect(result.reasonCodes).toEqual(["RELIABILITY_AT_OR_ABOVE_THRESHOLD"]);
    expect(result.reasons).toEqual([]);
  });

  it("emits RELIABILITY_BELOW_THRESHOLD for abstained decisions", () => {
    const result = buildDecision(500, { modelUncertainty: 1, historicalFailureRisk: 1, noveltyScore: 1, driftScore: 1, missingInformation: 1, contextRisk: 1 });
    expect(result.decision).toBe("ABSTAINED");
    expect(result.reasonCodes[0]).toBe("RELIABILITY_BELOW_THRESHOLD");
  });

  it("emits per-signal reason codes when signals exceed thresholds", () => {
    const result = buildDecision(500, { modelUncertainty: 0.8, historicalFailureRisk: 0.7, noveltyScore: 0.9, driftScore: 0.6, missingInformation: 0.5, contextRisk: 0.7 }, { reliabilityThreshold: 0.7 });
    expect(result.reasonCodes).toContain("MODEL_UNCERTAINTY_ELEVATED");
    expect(result.reasonCodes).toContain("HISTORICAL_FAILURE_RISK_ELEVATED");
    expect(result.reasonCodes).toContain("NOVELTY_SCORE_ELEVATED");
    expect(result.reasonCodes).toContain("DRIFT_SCORE_ELEVATED");
    expect(result.reasonCodes).toContain("MISSING_INFORMATION_ELEVATED");
    expect(result.reasonCodes).toContain("CONTEXT_RISK_ELEVATED");
    expect(result.reasons).toContain("Model uncertainty is elevated");
    expect(result.reasons).toContain("Similar historical cases showed high failure rates");
    expect(result.reasons).toContain("Current context is unusual relative to training data");
    expect(result.reasons).toContain("Recent behavior indicates distribution drift");
    expect(result.reasons).toContain("Important external context is unavailable");
    expect(result.reasons).toContain("Contextual risk is elevated");
  });

  it("emits only the reason codes for signals that actually trigger", () => {
    const result = buildDecision(500, { modelUncertainty: 0.7, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 });
    // modelUncertainty = 0.7 >= 0.60 → triggered
    expect(result.reasonCodes).toContain("MODEL_UNCERTAINTY_ELEVATED");
    // Others are below their thresholds
    expect(result.reasonCodes).not.toContain("HISTORICAL_FAILURE_RISK_ELEVATED");
    expect(result.reasonCodes).not.toContain("NOVELTY_SCORE_ELEVATED");
    expect(result.reasonCodes).not.toContain("DRIFT_SCORE_ELEVATED");
    expect(result.reasonCodes).not.toContain("MISSING_INFORMATION_ELEVATED");
    expect(result.reasonCodes).not.toContain("CONTEXT_RISK_ELEVATED");
  });

  it("reason codes and reasons arrays stay aligned", () => {
    const result = buildDecision(500, { modelUncertainty: 0.8, historicalFailureRisk: 0.6, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 });
    // 2 signal reasons + 1 primary decision code
    const signalCodes = result.reasonCodes.filter((c) => c !== "RELIABILITY_AT_OR_ABOVE_THRESHOLD" && c !== "RELIABILITY_BELOW_THRESHOLD");
    expect(signalCodes.length).toBe(result.reasons.length);
  });

  it("SIGNAL_RULES thresholds match the Python engine thresholds", () => {
    // These thresholds must stay in sync with ml-service/app/core.py selective_decision
    const expected: Record<string, number> = {
      MODEL_UNCERTAINTY_ELEVATED: 0.60,
      HISTORICAL_FAILURE_RISK_ELEVATED: 0.50,
      NOVELTY_SCORE_ELEVATED: 0.65,
      DRIFT_SCORE_ELEVATED: 0.55,
      MISSING_INFORMATION_ELEVATED: 0.40,
      CONTEXT_RISK_ELEVATED: 0.55,
    };
    for (const rule of SIGNAL_RULES) {
      expect(rule.minimum).toBe(expected[rule.code]);
    }
  });

  it("produces the same reason codes for the same inputs", () => {
    const signals = { modelUncertainty: 0.7, historicalFailureRisk: 0.6, noveltyScore: 0.3, driftScore: 0.2, missingInformation: 0.1, contextRisk: 0.1 };
    const r1 = buildDecision(500, signals);
    const r2 = buildDecision(600, signals);
    // Same signal values → same reason codes (but different prediction amounts)
    expect(r1.reasonCodes).toEqual(r2.reasonCodes);
    expect(r1.reasons).toEqual(r2.reasons);
  });

  it("produces different reason codes when different signals trigger", () => {
    const r1 = buildDecision(500, { modelUncertainty: 0.8, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 });
    const r2 = buildDecision(500, { modelUncertainty: 0.1, historicalFailureRisk: 0.1, noveltyScore: 0.8, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 });
    expect(r1.reasonCodes).not.toEqual(r2.reasonCodes);
    expect(r1.reasons).not.toEqual(r2.reasons);
  });
});