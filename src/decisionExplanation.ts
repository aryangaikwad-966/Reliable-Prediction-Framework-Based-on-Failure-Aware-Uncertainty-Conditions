import type { Decision } from "./types";

type ReliabilitySignals = { modelUncertainty: number; historicalFailureRisk: number; noveltyScore: number; driftScore: number; missingInformation: number; contextRisk: number };

export type DecisionResponse = { decision: Decision; prediction: number | null | undefined; failureRisk?: number; reliability?: number; reasons?: unknown; reasonCodes?: unknown; error?: string; signals?: Partial<ReliabilitySignals> };
export type EvidenceItem = { label: string; value: string; available: boolean };
export type DecisionExplanation = { headline: string; summary: string; details: string[]; evidence: EvidenceItem[]; nextSteps: string[]; showForecast: boolean };

type ReasonDefinition = { text: string; signal: keyof ReliabilitySignals; minimum: number };
const verifiedReasons: Record<string, ReasonDefinition> = {
  "Model uncertainty is elevated": { text: "Model uncertainty is elevated.", signal: "modelUncertainty", minimum: 0.6 },
  "Similar historical cases showed high failure rates": { text: "Similar historical cases showed high failure rates.", signal: "historicalFailureRisk", minimum: 0.5 },
  "Current context is unusual relative to training data": { text: "Current context is unusual relative to training data.", signal: "noveltyScore", minimum: 0.65 },
  "Recent behavior indicates distribution drift": { text: "Recent behavior indicates distribution drift.", signal: "driftScore", minimum: 0.55 },
  "Important external context is unavailable": { text: "Important external context is unavailable.", signal: "missingInformation", minimum: 0.4 },
  "Contextual risk is elevated": { text: "Contextual risk is elevated.", signal: "contextRisk", minimum: 0.55 },
};
const signalLabels: Record<keyof ReliabilitySignals, string> = { modelUncertainty: "Model uncertainty signal", historicalFailureRisk: "Historical failure-risk signal", noveltyScore: "Novelty signal", driftScore: "Drift signal", missingInformation: "Missing-information signal", contextRisk: "Context-risk signal" };
const neutralWithheld = "The system withheld this prediction based on its reliability checks.";
const unavailable = "Not returned by the API";
const templates = {
  accepted: {
    summary: "The system has evaluated the available historical data and the submitted input and accepted the prediction under its current decision process.",
    evidence: "The forecast is provided below, together with the available failure-risk score, computed signals, and relevant decision evidence. These values describe the information returned by the system and should be interpreted according to their definitions and limitations.",
    limitation: "This forecast is an estimate of the future modal price, not a guarantee of the actual market price.",
  },
  abstained: {
    summary: "The system evaluated the submitted input but has withheld the prediction because the current decision process did not accept it.",
    evidence: "The available failure-risk score, computed signals, and reason codes are shown below to help explain this decision. Where the system has not returned a specific reason or supporting evidence, that limitation is stated explicitly rather than replaced with an assumed explanation.",
    noForecast: "No forecast is provided for this request because the system has withheld the prediction.",
  },
  outOfScope: {
    summary: "This request is outside the supported scope of the loaded prediction system. The system cannot provide a forecast for this request.",
    nextStep: "Please provide an input supported by the application's current validation rules if you want to request an agricultural price prediction.",
  },
};

function isScore(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1; }
function scoreText(value: number) { return value.toFixed(4); }

function responseEvidence(response: DecisionResponse): EvidenceItem[] {
  const evidence: EvidenceItem[] = [
    { label: "Failure-risk score", value: isScore(response.failureRisk) ? scoreText(response.failureRisk) : unavailable, available: isScore(response.failureRisk) },
    { label: "Reliability value", value: isScore(response.reliability) ? scoreText(response.reliability) : unavailable, available: isScore(response.reliability) },
  ];
  (Object.keys(signalLabels) as Array<keyof ReliabilitySignals>).forEach((key) => {
    const value = response.signals?.[key];
    evidence.push({ label: signalLabels[key], value: isScore(value) ? scoreText(value) : unavailable, available: isScore(value) });
  });
  return evidence;
}

function reasonList(reasons: unknown): string[] {
  if (Array.isArray(reasons)) return reasons.filter((reason): reason is string => typeof reason === "string");
  if (typeof reasons !== "string") return [];
  try {
    const parsed: unknown = JSON.parse(reasons);
    return Array.isArray(parsed) ? parsed.filter((reason): reason is string => typeof reason === "string") : [];
  } catch {
    return [];
  }
}
function codeList(codes: unknown): string[] { return reasonList(codes); }

function supportedReasons(response: DecisionResponse) {
  return reasonList(response.reasons).flatMap((reason) => {
    const definition = verifiedReasons[reason];
    const signal = definition && response.signals?.[definition.signal];
    return definition && isScore(signal) && signal >= definition.minimum ? [definition.text] : [];
  });
}
function knownReasons(response: DecisionResponse) { return reasonList(response.reasons).flatMap((reason) => verifiedReasons[reason] ? [verifiedReasons[reason].text] : []); }

/** Converts API data into display copy only; it never recalculates model values or decisions. */
export function explainDecision(response: DecisionResponse): DecisionExplanation {
  const evidence = responseEvidence(response);
  const validForecast = response.decision === "ACCEPTED" && typeof response.prediction === "number" && Number.isFinite(response.prediction);
  if (response.decision === "ACCEPTED") {
    const reasons = knownReasons(response);
    const codes = codeList(response.reasonCodes);
    return {
    headline: "Prediction accepted", summary: templates.accepted.summary,
    details: [templates.accepted.evidence, templates.accepted.limitation, ...(codes.length ? [`Decision rule codes: ${codes.join(", ")}.`] : ["No decision rule code was returned by the API."]), ...(reasons.length ? reasons : ["No specific decision reason was returned by the API."]), ...(!validForecast ? ["The accepted response did not contain a valid forecast value, so no forecast is displayed."] : [])],
    evidence, nextSteps: validForecast ? ["Review the forecast together with the returned evidence and recorded decision."] : ["No forecast is displayed because the API did not return a valid forecast value."], showForecast: validForecast,
  };
  }
  if (response.decision === "OUT_OF_SCOPE") {
    const scopeReason = typeof response.error === "string" && response.error.trim() ? response.error.trim() : "No scope-validation detail was returned by the API.";
    const codes = codeList(response.reasonCodes);
    return { headline: "Request outside the loaded model’s supported scope", summary: templates.outOfScope.summary, details: ["The validation details below explain why the submitted request was rejected.", ...(codes.length ? [`Validation rule codes: ${codes.join(", ")}.`] : ["No validation rule code was returned by the API."]), scopeReason], evidence, nextSteps: [templates.outOfScope.nextStep], showForecast: false };
  }
  const supported = supportedReasons(response);
  const known = knownReasons(response);
  const codes = codeList(response.reasonCodes);
  return {
    headline: "Prediction withheld", summary: templates.abstained.summary,
    details: [templates.abstained.evidence, ...(codes.length ? [`Decision rule codes: ${codes.join(", ")}.`] : ["No decision rule code was returned by the API."]), ...(supported.length ? ["The returned decision evidence supports elevated estimated risk.", ...supported] : known.length ? known : ["No specific reason or supporting evidence was returned by the API."]), templates.abstained.noForecast], evidence,
    nextSteps: ["No forecast is displayed for an abstained decision. Review the returned evidence before submitting another supported request."], showForecast: false,
  };
}
