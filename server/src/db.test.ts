import { describe, expect, it } from "vitest";
import { normalizeSignals } from "./db";

describe("stored prediction signal compatibility", () => {
  it("normalizes evaluation-import snake_case signals for the UI contract", () => {
    expect(normalizeSignals({ model_uncertainty: 0.4, historical_failure_risk: 0.2, novelty_score: 0.1, drift_score: 0.3, missing_information: 0.05, context_risk: 0.2 })).toEqual({
      modelUncertainty: 0.4,
      historicalFailureRisk: 0.2,
      noveltyScore: 0.1,
      driftScore: 0.3,
      missingInformation: 0.05,
      contextRisk: 0.2,
    });
  });
});
