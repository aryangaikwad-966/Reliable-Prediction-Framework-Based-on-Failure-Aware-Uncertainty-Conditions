import axios from "axios";
import type { DashboardData, DataSummary, DriftData, EvaluationMetrics, Experiment, FailureCase, Metadata, Prediction, ReliabilityItem, ServiceHealth, UncertaintyItem } from "./types";

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

export async function getMetadata(): Promise<Metadata> {
  return (await api.get("/metadata")).data;
}

export async function getHealth(): Promise<ServiceHealth> {
  return (await api.get("/health")).data;
}

export async function getReliability(): Promise<{ threshold: number; data: ReliabilityItem[] }> {
  return (await api.get("/reliability")).data;
}

export async function getUncertainty(): Promise<{ status: string; methodology: string; data: UncertaintyItem[] }> {
  return (await api.get("/uncertainty")).data;
}

export async function getDrift(): Promise<DriftData> {
  return (await api.get("/drift")).data;
}

export async function getEvents(): Promise<{ status: string; message: string; events: unknown[] }> {
  return (await api.get("/events")).data;
}

export async function getExperiments(): Promise<{ data: Experiment[] }> {
  return (await api.get("/experiments")).data;
}

export async function getDataSummary(): Promise<DataSummary> {
  return (await api.get("/data")).data;
}

export async function createExperiment(name: string, configuration: Record<string, unknown>): Promise<{ id: number; status: string }> {
  return (await api.post("/experiments", { name, configuration })).data;
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