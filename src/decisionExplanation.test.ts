import { describe, expect, it } from "vitest";
import { explainDecision } from "./decisionExplanation";
import type { DecisionResponse } from "./decisionExplanation";

describe("explainDecision", () => {
  // ────────────────────────────────────────────────
  // ACCEPTED decisions
  // ────────────────────────────────────────────────

  it("builds an accepted response only when the API supplied a finite forecast", () => {
    const result = explainDecision({ decision: "ACCEPTED", prediction: 1789.53, failureRisk: 0.1, reliability: 0.9, reasonCodes: ["RELIABILITY_AT_OR_ABOVE_THRESHOLD"] });
    expect(result.headline).toBe("Prediction accepted");
    expect(result.summary).toContain("accepted the prediction");
    expect(result.details).toContain("This forecast is an estimate of the future modal price, not a guarantee of the actual market price.");
    expect(result.showForecast).toBe(true);
    expect(result.evidence[0]).toEqual({ label: "Failure-risk score", value: "0.1000", available: true });
  });

  it("shows the actual acceptance rule code with the reliability value", () => {
    const result = explainDecision({ decision: "ACCEPTED", prediction: 500, reliability: 0.82, reasonCodes: ["RELIABILITY_AT_OR_ABOVE_THRESHOLD"] });
    const ruleDetail = result.details.find((d) => d.includes("RELIABILITY_AT_OR_ABOVE_THRESHOLD"));
    expect(ruleDetail).toBeDefined();
    expect(ruleDetail).toContain("0.8200");
  });

  it("reports limitation when acceptance code exists but reliability is missing", () => {
    const result = explainDecision({ decision: "ACCEPTED", prediction: 500, reasonCodes: ["RELIABILITY_AT_OR_ABOVE_THRESHOLD"] });
    const ruleDetail = result.details.find((d) => d.includes("RELIABILITY_AT_OR_ABOVE_THRESHOLD"));
    expect(ruleDetail).toContain("not available to verify");
  });

  it("reports when no acceptance rule code was returned", () => {
    const result = explainDecision({ decision: "ACCEPTED", prediction: 500 });
    expect(result.details.some((d) => d.includes("No acceptance rule code"))).toBe(true);
  });

  it("shows elevated signals alongside acceptance with triggering evidence", () => {
    const result = explainDecision({
      decision: "ACCEPTED", prediction: 500, reliability: 0.72, failureRisk: 0.28,
      reasonCodes: ["RELIABILITY_AT_OR_ABOVE_THRESHOLD", "MISSING_INFORMATION_ELEVATED"],
      reasons: ["Important external context is unavailable"],
      signals: { modelUncertainty: 0.2, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.45, contextRisk: 0.1 },
    });
    expect(result.showForecast).toBe(true);
    expect(result.details.some((d) => d.includes("elevated signals"))).toBe(true);
    // Must show the actual signal value and threshold
    expect(result.details.some((d) => d.includes("0.4500") && d.includes("0.40"))).toBe(true);
  });

  it("withholds invalid accepted forecasts and labels absent API fields as unavailable", () => {
    const result = explainDecision({ decision: "ACCEPTED", prediction: null });
    expect(result.showForecast).toBe(false);
    expect(result.details.join(" ")).toContain("did not contain a valid forecast value");
    expect(result.evidence.every((item) => !item.available)).toBe(true);
  });

  // ────────────────────────────────────────────────
  // ABSTAINED decisions — reason verification
  // ────────────────────────────────────────────────

  it("uses 'elevated estimated risk' only for a reason supported by its returned signal", () => {
    const result = explainDecision({
      decision: "ABSTAINED", prediction: null,
      reliability: 0.18, failureRisk: 0.82,
      signals: { modelUncertainty: 0.1, historicalFailureRisk: 0.8, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 },
      reasons: ["Similar historical cases showed high failure rates"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD", "HISTORICAL_FAILURE_RISK_ELEVATED"],
    });
    expect(result.summary).toContain("withheld the prediction");
    expect(result.details).toContain("The returned decision evidence supports elevated estimated risk.");
    // Signal value evidence must be present
    expect(result.details.some((d) => d.includes("0.8000") && d.includes("0.50"))).toBe(true);
    expect(result.showForecast).toBe(false);
  });

  it("marks a known reason as 'associated' (not triggered) when signal is below threshold", () => {
    const result = explainDecision({
      decision: "ABSTAINED", prediction: null,
      signals: { modelUncertainty: 0.3, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 },
      reasons: ["Model uncertainty is elevated"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD"],
    });
    expect(result.summary).toContain("withheld the prediction");
    // Should NOT claim "elevated estimated risk" since signal (0.3) < threshold (0.6)
    expect(result.details).not.toContain("The returned decision evidence supports elevated estimated risk.");
    // Should show the signal value and note it's below the threshold
    expect(result.details.some((d) => d.includes("0.3000") && d.includes("below triggering level"))).toBe(true);
  });

  it("handles the case where a reason is known but signal is missing", () => {
    const result = explainDecision({
      decision: "ABSTAINED", prediction: null,
      reasons: ["Model uncertainty is elevated"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD"],
    });
    expect(result.details.some((d) => d.includes("signal value not returned"))).toBe(true);
  });

  it("shows abstention rule with actual reliability value", () => {
    const result = explainDecision({
      decision: "ABSTAINED", prediction: null,
      reliability: 0.25, failureRisk: 0.75,
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD", "MODEL_UNCERTAINTY_ELEVATED"],
      reasons: ["Model uncertainty is elevated"],
      signals: { modelUncertainty: 0.8, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 },
    });
    const ruleDetail = result.details.find((d) => d.includes("RELIABILITY_BELOW_THRESHOLD"));
    expect(ruleDetail).toBeDefined();
    expect(ruleDetail).toContain("0.2500");
  });

  it("withholds a contradictory abstained forecast", () => {
    expect(explainDecision({
      decision: "ABSTAINED", prediction: 500,
      signals: { modelUncertainty: 0.1, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.7 },
      reasons: ["Contextual risk is elevated"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD", "CONTEXT_RISK_ELEVATED"],
    }).showForecast).toBe(false);
  });

  it("honestly reports unrecognized reason codes", () => {
    const result = explainDecision({
      decision: "ABSTAINED", prediction: null,
      reasons: ["UNRECOGNIZED_CODE"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD"],
    });
    expect(result.details.some((d) => d.includes("Unrecognized reason") && d.includes("UNRECOGNIZED_CODE"))).toBe(true);
  });

  it("honestly reports when no reasons are returned", () => {
    const result = explainDecision({ decision: "ABSTAINED", prediction: null, reasonCodes: ["RELIABILITY_BELOW_THRESHOLD"] });
    expect(result.details).toContain("No specific reason or supporting evidence was returned by the API.");
  });

  it("does not crash on legacy non-array reasons values", () => {
    const response = { decision: "ABSTAINED" as const, prediction: null, reasons: '["Model uncertainty is elevated"]' };
    expect(explainDecision(response).details.some((d) => d.includes("Model uncertainty is elevated."))).toBe(true);
    expect(explainDecision({ ...response, reasons: "not-json" }).details).toContain("No specific reason or supporting evidence was returned by the API.");
  });

  // ────────────────────────────────────────────────
  // Multiple signals — all triggering reasons shown
  // ────────────────────────────────────────────────

  it("shows all triggering reasons when multiple signals exceed thresholds", () => {
    const result = explainDecision({
      decision: "ABSTAINED", prediction: null,
      reliability: 0.1, failureRisk: 0.9,
      signals: { modelUncertainty: 0.8, historicalFailureRisk: 0.7, noveltyScore: 0.9, driftScore: 0.6, missingInformation: 0.5, contextRisk: 0.7 },
      reasons: [
        "Model uncertainty is elevated",
        "Similar historical cases showed high failure rates",
        "Current context is unusual relative to training data",
        "Recent behavior indicates distribution drift",
        "Important external context is unavailable",
        "Contextual risk is elevated",
      ],
      reasonCodes: [
        "RELIABILITY_BELOW_THRESHOLD",
        "MODEL_UNCERTAINTY_ELEVATED",
        "HISTORICAL_FAILURE_RISK_ELEVATED",
        "NOVELTY_SCORE_ELEVATED",
        "DRIFT_SCORE_ELEVATED",
        "MISSING_INFORMATION_ELEVATED",
        "CONTEXT_RISK_ELEVATED",
      ],
    });
    expect(result.details).toContain("The returned decision evidence supports elevated estimated risk.");
    // Each triggering reason should appear with its signal value
    expect(result.details.some((d) => d.includes("0.8000") && d.includes("Model uncertainty"))).toBe(true);
    expect(result.details.some((d) => d.includes("0.7000") && d.includes("historical"))).toBe(true);
    expect(result.details.some((d) => d.includes("0.9000") && d.includes("unusual relative"))).toBe(true);
    expect(result.details.some((d) => d.includes("0.6000") && d.includes("distribution drift"))).toBe(true);
    expect(result.details.some((d) => d.includes("0.5000") && d.includes("external context"))).toBe(true);
    expect(result.details.some((d) => d.includes("0.7000") && d.includes("Contextual risk"))).toBe(true);
  });

  // ────────────────────────────────────────────────
  // Same reason for same rule
  // ────────────────────────────────────────────────

  it("produces the same reason text for different predictions when the same rule triggers", () => {
    const base: Omit<DecisionResponse, "prediction"> = {
      decision: "ABSTAINED",
      reliability: 0.2, failureRisk: 0.8,
      signals: { modelUncertainty: 0.8, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 },
      reasons: ["Model uncertainty is elevated"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD", "MODEL_UNCERTAINTY_ELEVATED"],
    };
    const r1 = explainDecision({ ...base, prediction: null });
    const r2 = explainDecision({ ...base, prediction: null });
    // Identical triggering conditions → identical detail text
    expect(r1.details).toEqual(r2.details);
  });

  it("produces different reason text when different rules trigger", () => {
    const r1 = explainDecision({
      decision: "ABSTAINED", prediction: null, reliability: 0.2, failureRisk: 0.8,
      signals: { modelUncertainty: 0.8, historicalFailureRisk: 0.1, noveltyScore: 0.1, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 },
      reasons: ["Model uncertainty is elevated"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD", "MODEL_UNCERTAINTY_ELEVATED"],
    });
    const r2 = explainDecision({
      decision: "ABSTAINED", prediction: null, reliability: 0.2, failureRisk: 0.8,
      signals: { modelUncertainty: 0.1, historicalFailureRisk: 0.1, noveltyScore: 0.9, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 },
      reasons: ["Current context is unusual relative to training data"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD", "NOVELTY_SCORE_ELEVATED"],
    });
    // Different triggering conditions → different detail text
    expect(r1.details).not.toEqual(r2.details);
  });

  // ────────────────────────────────────────────────
  // OUT_OF_SCOPE
  // ────────────────────────────────────────────────

  it("shows the actual API scope reason and withholds contradictory out-of-scope forecasts", () => {
    const result = explainDecision({
      decision: "OUT_OF_SCOPE", prediction: 500,
      error: "The selected context has insufficient historical observations.",
      reasonCodes: ["INSUFFICIENT_HISTORICAL_OBSERVATIONS"],
    });
    expect(result.headline).toBe("Request outside the loaded model's supported scope");
    expect(result.details).toContain("The selected context has insufficient historical observations.");
    expect(result.details.some((d) => d.includes("INSUFFICIENT_HISTORICAL_OBSERVATIONS"))).toBe(true);
    expect(result.showForecast).toBe(false);
  });

  it("preserves MODEL_SCOPE_REJECTED reason code for commodity mismatch", () => {
    const result = explainDecision({
      decision: "OUT_OF_SCOPE", prediction: null,
      error: "The requested context is outside the loaded model's supported scope.",
      reasonCodes: ["MODEL_SCOPE_REJECTED"],
    });
    expect(result.details.some((d) => d.includes("MODEL_SCOPE_REJECTED"))).toBe(true);
    expect(result.details).toContain("The requested context is outside the loaded model's supported scope.");
  });

  it("honestly reports missing scope-validation detail", () => {
    const result = explainDecision({ decision: "OUT_OF_SCOPE", prediction: null });
    expect(result.details).toContain("No scope-validation detail was returned by the API.");
    expect(result.details.some((d) => d.includes("No validation rule code"))).toBe(true);
  });

  // ────────────────────────────────────────────────
  // End-to-end: reason codes preserved through pipeline
  // ────────────────────────────────────────────────

  it("preserves all reason codes from ML service through to displayed explanation", () => {
    // Simulates what the API returns after the ML service → Node backend pipeline
    const apiResponse: DecisionResponse = {
      decision: "ABSTAINED", prediction: null,
      reliability: 0.15, failureRisk: 0.85,
      signals: { modelUncertainty: 0.7, historicalFailureRisk: 0.6, noveltyScore: 0.8, driftScore: 0.1, missingInformation: 0.1, contextRisk: 0.1 },
      reasons: ["Model uncertainty is elevated", "Similar historical cases showed high failure rates", "Current context is unusual relative to training data"],
      reasonCodes: ["RELIABILITY_BELOW_THRESHOLD", "MODEL_UNCERTAINTY_ELEVATED", "HISTORICAL_FAILURE_RISK_ELEVATED", "NOVELTY_SCORE_ELEVATED"],
    };
    const result = explainDecision(apiResponse);

    // Verify the abstention rule is shown
    expect(result.details.some((d) => d.includes("RELIABILITY_BELOW_THRESHOLD"))).toBe(true);

    // Verify each signal-specific reason is shown with its value
    expect(result.details.some((d) => d.includes("0.7000") && d.includes("Model uncertainty"))).toBe(true);
    expect(result.details.some((d) => d.includes("0.6000") && d.includes("historical"))).toBe(true);
    expect(result.details.some((d) => d.includes("0.8000") && d.includes("unusual relative"))).toBe(true);
  });
});
