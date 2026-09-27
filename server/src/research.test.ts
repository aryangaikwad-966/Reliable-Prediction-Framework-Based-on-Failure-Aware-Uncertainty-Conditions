import { describe, expect, it } from "vitest";
import { buildDecision, calculateRisk, classifyFailure, evaluateRegression } from "./research";

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