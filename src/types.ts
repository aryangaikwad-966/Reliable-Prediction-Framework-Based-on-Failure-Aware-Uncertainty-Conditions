export type Decision = "ACCEPTED" | "ABSTAINED";

export interface Prediction {
  id: string;
  commodity: string;
  market: string;
  variety: string;
  horizon: number;
  prediction: number | null;
  reliability: number;
  failureRisk: number;
  decision: Decision;
  createdAt: string;
  isDemo?: boolean;
  signals: {
    modelUncertainty: number;
    historicalFailureRisk: number;
    noveltyScore: number;
    driftScore: number;
    missingInformation: number;
    contextRisk: number;
  };
  reasons: string[];
}

export interface DashboardData {
  mode: "DEMO" | "LIVE";
  status: string;
  summary: {
    totalPredictions: number;
    accepted: number;
    abstained: number;
    averageReliability: number | null;
    failureDetectionRate: number | null;
    selectiveMae: number | null;
  };
  predictions: Prediction[];
  riskCoverage: Array<{ coverage: number; risk: number }>;
  reliabilityDistribution: Array<{ bucket: string; count: number }>;
  forecastActual: Array<{ date: string; forecast: number | null; actual: number | null }>;
}

export interface FailureCase {
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
  severity: "NORMAL" | "MODERATE" | "SIGNIFICANT" | "HIGH";
  reliability: number;
  noveltyScore: number;
  driftScore: number;
  context: Record<string, string | number | boolean | null>;
}

export interface EvaluationMetrics {
  status: "NOT_RUN" | "MEASURED";
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  r2: number | null;
  coverage: number | null;
  selectiveRisk: number | null;
  abstentionRate: number | null;
  failureDetectionRate: number | null;
  aurc: number | null;
}