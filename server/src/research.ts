export type Decision = "ACCEPTED" | "ABSTAINED";
export type Severity = "NORMAL" | "MODERATE" | "SIGNIFICANT" | "HIGH";

export interface ReliabilitySignals {
  modelUncertainty: number;
  historicalFailureRisk: number;
  noveltyScore: number;
  driftScore: number;
  missingInformation: number;
  contextRisk: number;
}

export interface PredictionRecord {
  id: string;
  commodity: string;
  market: string;
  variety: string;
  horizon: number;
  prediction: number | null;
  basePrediction: number;
  reliability: number;
  failureRisk: number;
  decision: Decision;
  createdAt: string;
  isDemo: boolean;
  signals: ReliabilitySignals;
  reasons: string[];
}

export interface FailureRecord {
  id: string;
  predictionId: string;
  date: string;
  commodity: string;
  market: string;
  variety: string;
  prediction: number | null;
  actual: number;
  absoluteError: number;
  relativeError: number;
  severity: Severity;
  reliability: number;
  noveltyScore: number;
  driftScore: number;
  context: Record<string, string | number | boolean | null>;
}

export const DEFAULT_RELIABILITY_THRESHOLD = 0.7;
export const DEFAULT_FAILURE_THRESHOLD = 0.25;

function clamp(value: number) {
  return Math.max(0, Math.min(1, value));
}

export function calculateRisk(signals: ReliabilitySignals) {
  const weights: ReliabilitySignals = {
    modelUncertainty: 0.24,
    historicalFailureRisk: 0.22,
    noveltyScore: 0.18,
    driftScore: 0.16,
    missingInformation: 0.1,
    contextRisk: 0.1,
  };
  const risk = Object.keys(weights).reduce((total, key) => {
    const name = key as keyof ReliabilitySignals;
    return total + weights[name] * clamp(signals[name]);
  }, 0);
  return Number(clamp(risk).toFixed(10));
}

export function buildDecision(
  basePrediction: number,
  signals: ReliabilitySignals,
  options: { reliabilityThreshold?: number; isDemo?: boolean; context?: Pick<PredictionRecord, "commodity" | "market" | "variety" | "horizon"> },
): PredictionRecord {
  const failureRisk = calculateRisk(signals);
  const reliability = 1 - failureRisk;
  const decision: Decision = reliability >= (options.reliabilityThreshold ?? DEFAULT_RELIABILITY_THRESHOLD) ? "ACCEPTED" : "ABSTAINED";
  const reasons: string[] = [];
  if (signals.modelUncertainty >= 0.6) reasons.push("Model uncertainty is elevated");
  if (signals.historicalFailureRisk >= 0.5) reasons.push("Similar historical cases showed high failure rates");
  if (signals.noveltyScore >= 0.65) reasons.push("Current context is unusual relative to training data");
  if (signals.driftScore >= 0.55) reasons.push("Recent behavior indicates distribution drift");
  if (signals.missingInformation >= 0.4) reasons.push("Important external context is unavailable");
  if (signals.contextRisk >= 0.55) reasons.push("Contextual risk is elevated");
  const base = options.context ?? { commodity: "Tomato", market: "Lasalgaon", variety: "Local", horizon: 7 };
  return {
    id: `pred_${Date.now()}_${Math.floor(basePrediction)}`,
    ...base,
    prediction: decision === "ABSTAINED" ? null : Number(basePrediction.toFixed(2)),
    basePrediction: Number(basePrediction.toFixed(2)),
    reliability: Number(reliability.toFixed(4)),
    failureRisk: Number(failureRisk.toFixed(4)),
    decision,
    createdAt: new Date().toISOString(),
    isDemo: options.isDemo ?? false,
    signals,
    reasons,
  };
}

function stableHash(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  return hash;
}

export function buildDemoPrediction(input: { commodity: string; market: string; variety: string; horizon: number }): PredictionRecord {
  const hash = stableHash(`${input.commodity}|${input.market}|${input.variety}|${input.horizon}`);
  const basePrediction = 360 + (hash % 260);
  const signals: ReliabilitySignals = {
    modelUncertainty: 0.18 + ((hash >>> 2) % 34) / 100,
    historicalFailureRisk: 0.08 + ((hash >>> 5) % 31) / 100,
    noveltyScore: 0.12 + ((hash >>> 8) % 40) / 100,
    driftScore: 0.08 + ((hash >>> 11) % 30) / 100,
    missingInformation: 0.28,
    contextRisk: 0.14 + ((hash >>> 14) % 28) / 100,
  };
  return buildDecision(basePrediction, signals, { isDemo: true, context: input });
}

export function classifyFailure(
  absoluteError: number,
  relativeError: number,
  thresholds = { moderate: 0.1, significant: 0.25, high: 0.5 },
): Severity {
  if (relativeError >= thresholds.high) return "HIGH";
  if (relativeError >= thresholds.significant) return "SIGNIFICANT";
  if (relativeError >= thresholds.moderate) return "MODERATE";
  if (absoluteError <= 0) return "NORMAL";
  return "NORMAL";
}

export function summarizePredictions(predictions: PredictionRecord[]) {
  const totalPredictions = predictions.length;
  const accepted = predictions.filter((item) => item.decision === "ACCEPTED").length;
  const reliability = predictions.length ? predictions.reduce((sum, item) => sum + item.reliability, 0) / predictions.length : null;
  const buckets = ["0–20%", "20–40%", "40–60%", "60–80%", "80–100%"];
  const reliabilityDistribution = buckets.map((bucket, index) => {
    const lower = index / 5;
    const upper = (index + 1) / 5;
    return { bucket, count: predictions.filter((item) => item.reliability >= lower && item.reliability <= upper).length };
  });
  return {
    totalPredictions,
    accepted,
    abstained: totalPredictions - accepted,
    averageReliability: reliability == null ? null : Number(reliability.toFixed(4)),
    failureDetectionRate: null,
    selectiveMae: null,
    reliabilityDistribution,
  };
}

export function evaluateRegression(actual: number[], predicted: number[]) {
  if (!actual.length || actual.length !== predicted.length) {
    return { mae: null, rmse: null, mape: null, r2: null };
  }
  const errors = actual.map((value, index) => value - predicted[index]);
  const mae = errors.reduce((sum, value) => sum + Math.abs(value), 0) / errors.length;
  const rmse = Math.sqrt(errors.reduce((sum, value) => sum + value ** 2, 0) / errors.length);
  const mape = actual.reduce((sum, value, index) => sum + (value ? Math.abs(errors[index] / value) : 0), 0) / actual.length;
  const mean = actual.reduce((sum, value) => sum + value, 0) / actual.length;
  const ssTot = actual.reduce((sum, value) => sum + (value - mean) ** 2, 0);
  const ssRes = errors.reduce((sum, value) => sum + value ** 2, 0);
  return { mae, rmse, mape, r2: ssTot ? 1 - ssRes / ssTot : null };
}

export const demoPredictions: PredictionRecord[] = [
  buildDecision(516, { modelUncertainty: 0.19, historicalFailureRisk: 0.1, noveltyScore: 0.16, driftScore: 0.1, missingInformation: 0.28, contextRisk: 0.16 }, { isDemo: true, context: { commodity: "Tomato", market: "Lasalgaon", variety: "Local", horizon: 7 } }),
  buildDecision(482, { modelUncertainty: 0.31, historicalFailureRisk: 0.18, noveltyScore: 0.22, driftScore: 0.14, missingInformation: 0.28, contextRisk: 0.2 }, { isDemo: true, context: { commodity: "Tomato", market: "Pune", variety: "Local", horizon: 7 } }),
  buildDecision(608, { modelUncertainty: 0.69, historicalFailureRisk: 0.66, noveltyScore: 0.72, driftScore: 0.62, missingInformation: 0.28, contextRisk: 0.54 }, { isDemo: true, context: { commodity: "Onion", market: "Nashik", variety: "Red", horizon: 7 } }),
  buildDecision(405, { modelUncertainty: 0.46, historicalFailureRisk: 0.32, noveltyScore: 0.3, driftScore: 0.24, missingInformation: 0.28, contextRisk: 0.24 }, { isDemo: true, context: { commodity: "Tomato", market: "Kolar", variety: "Hybrid", horizon: 7 } }),
];

export const demoFailures: FailureRecord[] = [
  { id: "failure_demo_1", predictionId: demoPredictions[2].id, date: "2025-10-18T00:00:00.000Z", commodity: "Onion", market: "Nashik", variety: "Red", prediction: null, actual: 742, absoluteError: 134, relativeError: 0.22, severity: "MODERATE", reliability: demoPredictions[2].reliability, noveltyScore: 0.72, driftScore: 0.62, context: { externalEvents: "NOT AVAILABLE", source: "DEMO" } },
];