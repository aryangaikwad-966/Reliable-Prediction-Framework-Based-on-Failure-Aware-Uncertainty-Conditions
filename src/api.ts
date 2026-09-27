import axios from "axios";
import type { DashboardData, EvaluationMetrics, FailureCase, Prediction } from "./types";

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || "/api" });

export async function getDashboard(): Promise<DashboardData> {
  return (await api.get("/dashboard")).data;
}

export async function getPredictions(): Promise<Prediction[]> {
  return (await api.get("/predictions")).data.data;
}

export async function createPrediction(input: {
  commodity: string;
  market: string;
  variety: string;
  horizon: number;
}): Promise<Prediction> {
  return (await api.post("/predictions", input)).data;
}

export async function getFailures(): Promise<FailureCase[]> {
  return (await api.get("/failures")).data.data;
}

export async function getEvaluation(): Promise<EvaluationMetrics> {
  return (await api.get("/evaluation")).data;
}

export async function getMetadata(): Promise<{ commodities: string[]; markets: string[]; varieties: string[] }> {
  return (await api.get("/metadata")).data;
}

export async function getFailureMemoryContext(commodity: string, market: string, variety?: string): Promise<{
  similarFailures: FailureCase[];
  historicalFailureRate: number;
  count: number;
}> {
  const params = new URLSearchParams({ commodity, market });
  if (variety) params.append("variety", variety);
  return (await api.get(`/failure-memory/context?${params}`)).data;
}

export async function submitOutcome(predictionId: string, actual: number): Promise<FailureCase> {
  return (await api.post("/outcomes", { predictionId, actual })).data;
}