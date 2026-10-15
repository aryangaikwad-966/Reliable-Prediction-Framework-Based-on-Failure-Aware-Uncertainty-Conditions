import { describe, expect, it } from "vitest";
import { normalizeReasonCodes, normalizeReasons, normalizeSignals } from "./db";

describe("stored prediction signal compatibility", () => {
  it("normalizes evaluation-import snake_case signals for the UI contract", () => {
    expect(normalizeSignals({ model_uncertainty: 0.4, historical_failure_risk: 0.2, novelty_score: 0.1, drift_score: 0.3, missing_information: 0.05, context_risk: 0.2 })).toEqual({
      modelUncertainty: 0.4,
      historicalFailureRisk: 0.2,
      noveltyScore: 0.1,
      driftScore: 0.3,
      missingInformation: 0.05,
      contextRisk: 0.2,
      climateAnomaly: 0,
      marketDataAnomaly: 0,
    });
  });

  it("normalizes legacy stored reason arrays before returning them to the UI", () => {
    expect(normalizeReasons('["Model uncertainty is elevated"]')).toEqual(["Model uncertainty is elevated"]);
    expect(normalizeReasons("not-json")).toEqual([]);
  });

  it("preserves explicitly unavailable signals instead of converting them to zero", () => {
    expect(normalizeSignals({ historical_failure_risk: null, climate_anomaly: null })).toMatchObject({
      historicalFailureRisk: null,
      climateAnomaly: null,
    });
  });

  it("preserves current reason messages and codes in the stored decision evidence", () => {
    const stored = { messages: ["Model uncertainty is elevated"], codes: ["RELIABILITY_BELOW_THRESHOLD", "MODEL_UNCERTAINTY_ELEVATED"] };
    expect(normalizeReasons(stored)).toEqual(["Model uncertainty is elevated"]);
    expect(normalizeReasonCodes(stored)).toEqual(["RELIABILITY_BELOW_THRESHOLD", "MODEL_UNCERTAINTY_ELEVATED"]);
  });
});
