export type Decision = "ACCEPTED" | "ABSTAINED" | "OUT_OF_SCOPE";

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

export interface ServiceHealth {
  ok: boolean;
  service: string;
  database: { connected: boolean; mode: "LIVE" | "DEMO" };
  mlService: { url: string; reachable: boolean; ready: boolean; modelAvailable: boolean; error?: string };
  demoMode: boolean;
}

export interface PredictionPage {
  data: Prediction[];
  pagination: { limit: number; offset: number; total: number };
}

export interface ResearchResults {
  status: "VERIFIED_ARTIFACT";
  source: string;
  target: string;
  split: string;
  data: Record<string, unknown>;
}

export interface Metadata {
  commodities: string[];
  markets: string[];
  varieties: string[];
  combinations: Array<{ commodity: string; market: string; variety: string; rows: number }>;
}

export interface ReliabilityItem {
  id: string;
  reliability: number;
  failureRisk: number;
  decision: Decision;
}

export interface UncertaintyItem {
  id: string;
  modelUncertainty: number;
  historicalFailureRisk: number;
  noveltyScore: number;
  driftScore: number;
  missingInformation: number;
  contextRisk: number;
}

export interface DriftData {
  status: string;
  score: number | null;
  affectedFeatures: string[];
  reason?: string;
  detectionDate?: string;
  methodology?: string;
}

export interface Experiment {
  id?: number;
  name: string;
  status: string;
  startedAt?: string;
  completedAt?: string;
  metrics?: Record<string, number> | null;
  coverage?: number | null;
  selectiveRisk?: number | null;
  failureDetectionRate?: number | null;
  calibration?: unknown;
}

export interface DataSummary {
  recordCount: number | null;
  dateRange: { from: string; to: string } | null;
}
