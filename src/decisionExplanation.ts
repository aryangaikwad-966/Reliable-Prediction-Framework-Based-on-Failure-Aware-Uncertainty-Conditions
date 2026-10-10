import type { Decision } from "./types";

type ReliabilitySignals = { modelUncertainty: number; historicalFailureRisk: number; noveltyScore: number; driftScore: number; missingInformation: number; contextRisk: number };

export type DecisionResponse = { decision: Decision; prediction: number | null | undefined; failureRisk?: number; reliability?: number; reasons?: unknown; reasonCodes?: unknown; error?: string; signals?: Partial<ReliabilitySignals> };
export type EvidenceItem = { label: string; value: string; available: boolean };
export type DecisionExplanation = { headline: string; summary: string; details: string[]; evidence: EvidenceItem[]; nextSteps: string[]; showForecast: boolean };

/**
 * Signal-specific decision rules — mirrors the thresholds and reason codes
 * used by the FastAPI engine (ml-service/app/core.py `selective_decision`)
 * and the Node engine (server/src/research.ts `SIGNAL_RULES`).
 *
 * All three layers MUST use the same constants.
 */
type ReasonDefinition = { text: string; signal: keyof ReliabilitySignals; minimum: number; code: string };
const verifiedReasons: Record<string, ReasonDefinition> = {
  "Model uncertainty is elevated":                        { text: "Model uncertainty is elevated.",                        signal: "modelUncertainty",      minimum: 0.6,  code: "MODEL_UNCERTAINTY_ELEVATED" },
  "Similar historical cases showed high failure rates":   { text: "Similar historical cases showed high failure rates.",   signal: "historicalFailureRisk",  minimum: 0.5,  code: "HISTORICAL_FAILURE_RISK_ELEVATED" },
  "Current context is unusual relative to training data": { text: "Current context is unusual relative to training data.", signal: "noveltyScore",           minimum: 0.65, code: "NOVELTY_SCORE_ELEVATED" },
  "Recent behavior indicates distribution drift":         { text: "Recent behavior indicates distribution drift.",         signal: "driftScore",             minimum: 0.55, code: "DRIFT_SCORE_ELEVATED" },
  "Important external context is unavailable":            { text: "Important external context is unavailable.",            signal: "missingInformation",     minimum: 0.4,  code: "MISSING_INFORMATION_ELEVATED" },
  "Contextual risk is elevated":                          { text: "Contextual risk is elevated.",                          signal: "contextRisk",            minimum: 0.55, code: "CONTEXT_RISK_ELEVATED" },
};

/** Canonical reason-code-to-definition map (for code-first lookups). */
const codeToDefinition: Record<string, ReasonDefinition> = {};
for (const def of Object.values(verifiedReasons)) codeToDefinition[def.code] = def;

const signalLabels: Record<keyof ReliabilitySignals, string> = { modelUncertainty: "Model uncertainty signal", historicalFailureRisk: "Historical failure-risk signal", noveltyScore: "Novelty signal", driftScore: "Drift signal", missingInformation: "Missing-information signal", contextRisk: "Context-risk signal" };
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

/**
 * Classifies an API reason into one of three categories:
 *
 * - **"triggered"**: The reason text is recognized AND the corresponding
 *   signal value meets or exceeds the decision-rule threshold.  This is a
 *   reason that *directly triggered* the decision.
 *
 * - **"associated"**: The reason text is recognized but the signal value is
 *   either missing or below the threshold.  The evidence is *associated*
 *   with the decision but did not directly trigger it according to the
 *   rule we can verify.
 *
 * - **"unverifiable"**: The reason text is not recognized in our rule table,
 *   so we cannot verify it.
 */
type ReasonVerdict = { verdict: "triggered" | "associated" | "unverifiable"; text: string; signalLabel?: string; signalValue?: string; threshold?: string };

function classifyReason(reason: string, signals: Partial<ReliabilitySignals> | undefined): ReasonVerdict {
  const definition = verifiedReasons[reason];
  if (!definition) return { verdict: "unverifiable", text: reason };
  const signalValue = signals?.[definition.signal];
  const signalLabel = signalLabels[definition.signal];
  if (isScore(signalValue) && signalValue >= definition.minimum) {
    return { verdict: "triggered", text: definition.text, signalLabel, signalValue: scoreText(signalValue), threshold: definition.minimum.toFixed(2) };
  }
  return { verdict: "associated", text: definition.text, signalLabel, signalValue: isScore(signalValue) ? scoreText(signalValue) : undefined, threshold: definition.minimum.toFixed(2) };
}

function formatReasonVerdict(rv: ReasonVerdict): string {
  if (rv.verdict === "triggered") {
    return `${rv.text} (${rv.signalLabel}: ${rv.signalValue} ≥ ${rv.threshold} threshold)`;
  }
  if (rv.verdict === "associated") {
    if (rv.signalValue) return `${rv.text} (${rv.signalLabel}: ${rv.signalValue}; threshold ${rv.threshold} — signal below triggering level)`;
    return `${rv.text} (signal value not returned by the API; cannot verify against ${rv.threshold} threshold)`;
  }
  return `Unrecognized reason: "${rv.text}" (cannot verify — not in the decision-rule table)`;
}

/**
 * Build an acceptance-specific explanation line from reason codes.
 * For accepted predictions, we explain the acceptance rule *and* any
 * elevated-signal warnings that the engine returned alongside it.
 */
function acceptanceRuleExplanation(codes: string[], signals: Partial<ReliabilitySignals> | undefined, reliability: unknown): string {
  const hasThresholdCode = codes.includes("RELIABILITY_AT_OR_ABOVE_THRESHOLD");
  if (hasThresholdCode && isScore(reliability)) {
    return `Acceptance rule: reliability (${scoreText(reliability)}) is at or above the configured threshold (RELIABILITY_AT_OR_ABOVE_THRESHOLD).`;
  }
  if (hasThresholdCode) {
    return "Acceptance rule: RELIABILITY_AT_OR_ABOVE_THRESHOLD (reliability value not available to verify).";
  }
  return "No acceptance rule code was returned by the API.";
}

/** Converts API data into display copy only; it never recalculates model values or decisions. */
export function explainDecision(response: DecisionResponse): DecisionExplanation {
  const evidence = responseEvidence(response);
  const validForecast = response.decision === "ACCEPTED" && typeof response.prediction === "number" && Number.isFinite(response.prediction);
  const reasons = reasonList(response.reasons);
  const codes = codeList(response.reasonCodes);

  // ----- ACCEPTED -----
  if (response.decision === "ACCEPTED") {
    const acceptRule = acceptanceRuleExplanation(codes, response.signals, response.reliability);
    const verdicts = reasons.map((r) => classifyReason(r, response.signals));
    const triggered = verdicts.filter((v) => v.verdict === "triggered");
    const associated = verdicts.filter((v) => v.verdict === "associated");
    const unverifiable = verdicts.filter((v) => v.verdict === "unverifiable");

    const detailLines: string[] = [templates.accepted.evidence, templates.accepted.limitation, acceptRule];
    if (triggered.length) {
      detailLines.push("The following elevated signals were returned alongside the acceptance:");
      triggered.forEach((v) => detailLines.push(formatReasonVerdict(v)));
    }
    if (associated.length) {
      associated.forEach((v) => detailLines.push(formatReasonVerdict(v)));
    }
    if (unverifiable.length) {
      unverifiable.forEach((v) => detailLines.push(formatReasonVerdict(v)));
    }
    if (!reasons.length && codes.length <= 1) {
      detailLines.push("No additional signal-specific reason was returned by the API.");
    }
    if (!validForecast) {
      detailLines.push("The accepted response did not contain a valid forecast value, so no forecast is displayed.");
    }
    return {
      headline: "Prediction accepted", summary: templates.accepted.summary, details: detailLines, evidence,
      nextSteps: validForecast ? ["Review the forecast together with the returned evidence and recorded decision."] : ["No forecast is displayed because the API did not return a valid forecast value."],
      showForecast: validForecast,
    };
  }

  // ----- OUT_OF_SCOPE -----
  if (response.decision === "OUT_OF_SCOPE") {
    const scopeReason = typeof response.error === "string" && response.error.trim() ? response.error.trim() : "No scope-validation detail was returned by the API.";
    return {
      headline: "Request outside the loaded model's supported scope", summary: templates.outOfScope.summary,
      details: [
        "The validation details below explain why the submitted request was rejected.",
        ...(codes.length ? [`Validation rule codes: ${codes.join(", ")}.`] : ["No validation rule code was returned by the API."]),
        scopeReason,
      ],
      evidence, nextSteps: [templates.outOfScope.nextStep], showForecast: false,
    };
  }

  // ----- ABSTAINED -----
  const abstainRule = codes.includes("RELIABILITY_BELOW_THRESHOLD")
    ? (isScore(response.reliability)
      ? `Abstention rule: reliability (${scoreText(response.reliability!)}) is below the configured threshold (RELIABILITY_BELOW_THRESHOLD).`
      : "Abstention rule: RELIABILITY_BELOW_THRESHOLD (reliability value not available to verify).")
    : (codes.length ? `Decision rule codes: ${codes.join(", ")}.` : "No decision rule code was returned by the API.");

  const verdicts = reasons.map((r) => classifyReason(r, response.signals));
  const triggered = verdicts.filter((v) => v.verdict === "triggered");
  const associated = verdicts.filter((v) => v.verdict === "associated");
  const unverifiable = verdicts.filter((v) => v.verdict === "unverifiable");

  const detailLines: string[] = [templates.abstained.evidence, abstainRule];
  if (triggered.length) {
    detailLines.push("The returned decision evidence supports elevated estimated risk.");
    triggered.forEach((v) => detailLines.push(formatReasonVerdict(v)));
  }
  if (associated.length) {
    associated.forEach((v) => detailLines.push(formatReasonVerdict(v)));
  }
  if (unverifiable.length) {
    unverifiable.forEach((v) => detailLines.push(formatReasonVerdict(v)));
  }
  if (!verdicts.length) {
    detailLines.push("No specific reason or supporting evidence was returned by the API.");
  }
  detailLines.push(templates.abstained.noForecast);

  return {
    headline: "Prediction withheld", summary: templates.abstained.summary, details: detailLines, evidence,
    nextSteps: ["No forecast is displayed for an abstained decision. Review the returned evidence before submitting another supported request."],
    showForecast: false,
  };
}
