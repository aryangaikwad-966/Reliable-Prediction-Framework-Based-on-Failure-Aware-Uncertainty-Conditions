import { describe, expect, it } from "vitest";
import { explainDecision } from "./decisionExplanation";

describe("explainDecision", () => {
  it("builds an accepted response only when the API supplied a finite forecast", () => {
    const result = explainDecision({ decision: "ACCEPTED", prediction: 1789.53, failureRisk: 0.1, reliability: 0.9 });
    expect(result.headline).toBe("Prediction accepted"); expect(result.summary).toContain("accepted the prediction"); expect(result.details).toContain("This forecast is an estimate of the future modal price, not a guarantee of the actual market price."); expect(result.showForecast).toBe(true);
    expect(result.evidence[0]).toEqual({ label: "Failure-risk score", value: "0.1000", available: true });
  });
  it("withholds invalid accepted forecasts and labels absent API fields as unavailable", () => {
    const result = explainDecision({ decision: "ACCEPTED", prediction: null });
    expect(result.showForecast).toBe(false); expect(result.details.join(" ")).toContain("did not contain a valid forecast value"); expect(result.evidence.every((item) => !item.available)).toBe(true);
  });
  it("uses elevated estimated risk only for a reason supported by its returned signal", () => {
    const result = explainDecision({ decision: "ABSTAINED", prediction: null, signals: { historicalFailureRisk: 0.8 }, reasons: ["Similar historical cases showed high failure rates"] });
    expect(result.summary).toContain("withheld the prediction"); expect(result.details).toContain("The returned decision evidence supports elevated estimated risk."); expect(result.details).toContain("Similar historical cases showed high failure rates."); expect(result.showForecast).toBe(false);
  });
  it("uses a verified reason, not an unsupported elevated-risk claim, when signals are missing", () => {
    const result = explainDecision({ decision: "ABSTAINED", prediction: null, reasons: ["Model uncertainty is elevated"] });
    expect(result.summary).toContain("withheld the prediction"); expect(result.details).toContain("Model uncertainty is elevated."); expect(result.details).not.toContain("The returned decision evidence supports elevated estimated risk.");
  });
  it("withholds a contradictory abstained forecast", () => {
    expect(explainDecision({ decision: "ABSTAINED", prediction: 500, signals: { contextRisk: 0.7 }, reasons: ["Contextual risk is elevated"] }).showForecast).toBe(false);
  });
  it("uses a neutral fallback for unknown reason codes", () => {
    const result = explainDecision({ decision: "ABSTAINED", prediction: null, reasons: ["UNRECOGNIZED_CODE"] });
    expect(result.summary).toContain("withheld the prediction"); expect(result.details).toContain("No specific reason code or supporting evidence was returned by the API.");
  });
  it("does not crash on legacy non-array reasons values", () => {
    const response = { decision: "ABSTAINED" as const, prediction: null, reasons: '["Model uncertainty is elevated"]' };
    expect(explainDecision(response).details).toContain("Model uncertainty is elevated.");
    expect(explainDecision({ ...response, reasons: "not-json" }).details).toContain("No specific reason code or supporting evidence was returned by the API.");
  });
  it("shows the actual API scope reason and withholds contradictory out-of-scope forecasts", () => {
    const result = explainDecision({ decision: "OUT_OF_SCOPE", prediction: 500, error: "The selected context has insufficient historical observations." });
    expect(result.headline).toBe("Request outside the loaded model’s supported scope"); expect(result.details).toContain("The selected context has insufficient historical observations."); expect(result.showForecast).toBe(false);
  });
});
