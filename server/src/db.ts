import pg from "pg";
import type { FailureRecord, PredictionRecord } from "./research";

const { Pool } = pg;
const connectionString = process.env.DATABASE_URL || "postgresql://aryangaikwad@localhost:5432/reliable_prediction";
export const dbEnabled = Boolean(connectionString);
export const pool = connectionString ? new Pool({ connectionString, max: 5, ssl: process.env.NODE_ENV === "production" ? { rejectUnauthorized: false } : undefined }) : null;

const predictions: PredictionRecord[] = [];
const failures: FailureRecord[] = [];

export function normalizeSignals(value: unknown) {
  const signals = (value ?? {}) as Record<string, number>;
  return {
    modelUncertainty: signals.modelUncertainty ?? signals.model_uncertainty ?? 0,
    historicalFailureRisk: signals.historicalFailureRisk ?? signals.historical_failure_risk ?? 0,
    noveltyScore: signals.noveltyScore ?? signals.novelty_score ?? 0,
    driftScore: signals.driftScore ?? signals.drift_score ?? 0,
    missingInformation: signals.missingInformation ?? signals.missing_information ?? 0,
    contextRisk: signals.contextRisk ?? signals.context_risk ?? 0,
  };
}

/** Stored imports may contain JSON text while live writes store JSON arrays. */
export function normalizeReasons(value: unknown): string[] {
  if (value && typeof value === "object" && !Array.isArray(value)) return normalizeReasons((value as { messages?: unknown }).messages);
  if (Array.isArray(value)) return value.filter((reason): reason is string => typeof reason === "string");
  if (typeof value !== "string") return [];
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((reason): reason is string => typeof reason === "string") : [];
  } catch {
    return [];
  }
}

export function normalizeReasonCodes(value: unknown): string[] {
  if (value && typeof value === "object" && !Array.isArray(value)) return normalizeReasonCodes((value as { codes?: unknown }).codes);
  if (Array.isArray(value)) return value.filter((code): code is string => typeof code === "string");
  if (typeof value !== "string") return [];
  try { return normalizeReasonCodes(JSON.parse(value)); } catch { return []; }
}

export async function checkDatabase() {
  if (!pool) return { connected: false, mode: "DEMO" as const };
  try {
    await pool.query("select 1");
    return { connected: true, mode: "LIVE" as const };
  } catch {
    return { connected: false, mode: "DEMO" as const };
  }
}

export async function listPredictions() {
  if (!pool) return [...predictions];
  const result = await pool.query("select id, commodity, market, variety, horizon, prediction, base_prediction as \"basePrediction\", reliability, failure_risk as \"failureRisk\", decision, created_at as \"createdAt\", is_demo as \"isDemo\", signals, reasons from predictions order by created_at desc limit 100");
  return result.rows.map((row) => ({
    ...row,
    prediction: row.prediction == null ? null : Number(row.prediction),
    basePrediction: Number(row.basePrediction),
    reliability: Number(row.reliability),
    failureRisk: Number(row.failureRisk),
    signals: normalizeSignals(row.signals),
    reasons: normalizeReasons(row.reasons),
    reasonCodes: normalizeReasonCodes(row.reasons),
  })) as PredictionRecord[];
}

export async function listPredictionsPage(options: { limit: number; offset: number; decision?: string }) {
  if (!pool) {
    const rows = predictions.filter((item) => !options.decision || item.decision === options.decision);
    return { data: rows.slice(options.offset, options.offset + options.limit), total: rows.length };
  }
  const values: Array<number | string> = [];
  const filters: string[] = [];
  if (options.decision) {
    values.push(options.decision);
    filters.push(`decision = $${values.length}`);
  }
  values.push(options.limit, options.offset);
  const where = filters.length ? `where ${filters.join(" and ")}` : "";
  const result = await pool.query(
    `select id, commodity, market, variety, horizon, prediction, base_prediction as "basePrediction", reliability, failure_risk as "failureRisk", decision, created_at as "createdAt", is_demo as "isDemo", signals, reasons,
      count(*) over()::int as total
     from predictions ${where} order by created_at desc limit $${values.length - 1} offset $${values.length}`,
    values,
  );
  return {
    data: result.rows.map(({ total: _total, ...row }) => ({
      ...row,
      prediction: row.prediction == null ? null : Number(row.prediction),
      basePrediction: Number(row.basePrediction),
      reliability: Number(row.reliability),
      failureRisk: Number(row.failureRisk),
      signals: normalizeSignals(row.signals),
      reasons: normalizeReasons(row.reasons),
      reasonCodes: normalizeReasonCodes(row.reasons),
    })) as PredictionRecord[],
    total: result.rows[0]?.total ?? 0,
  };
}

export async function savePrediction(item: PredictionRecord) {
  predictions.unshift(item);
  if (pool) {
    await pool.query(
      `insert into predictions (id, commodity, market, variety, horizon, prediction, base_prediction, reliability, failure_risk, decision, is_demo, signals, reasons)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       on conflict (id) do nothing`,
      [item.id, item.commodity, item.market, item.variety, item.horizon, item.prediction, item.basePrediction, item.reliability, item.failureRisk, item.decision, item.isDemo, JSON.stringify(item.signals), JSON.stringify({ messages: item.reasons, codes: item.reasonCodes })],
    );
  }
  return item;
}

export async function listFailures() {
  if (!pool) return [...failures];
  const result = await pool.query("select id, prediction_id as \"predictionId\", event_date as date, commodity, market, variety, prediction, actual, absolute_error as \"absoluteError\", relative_error as \"relativeError\", severity, reliability, novelty_score as \"noveltyScore\", drift_score as \"driftScore\", context from failure_memory order by event_date desc limit 100");
  return result.rows.map((row) => ({
    ...row,
    prediction: row.prediction == null ? null : Number(row.prediction),
    actual: Number(row.actual),
    absoluteError: Number(row.absoluteError),
    relativeError: Number(row.relativeError),
    reliability: Number(row.reliability),
    noveltyScore: Number(row.noveltyScore),
    driftScore: Number(row.driftScore),
  })) as FailureRecord[];
}

export async function saveFailure(item: FailureRecord) {
  failures.unshift(item);
  if (pool) {
    await pool.query(
      `insert into failure_memory (id, prediction_id, event_date, commodity, market, variety, prediction, actual, absolute_error, relative_error, severity, reliability, novelty_score, drift_score, context)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
       on conflict (id) do nothing`,
      [item.id, item.predictionId, item.date, item.commodity, item.market, item.variety, item.prediction, item.actual, item.absoluteError, item.relativeError, item.severity, item.reliability, item.noveltyScore, item.driftScore, item.context],
    );
  }
  return item;
}

export async function saveOutcome(predictionId: string, actual: number, observedAt = new Date()) {
  if (!pool) return { predictionId, actual, observedAt: observedAt.toISOString() };
  // The database clock establishes the observation time and rejects an
  // impossible record for a prediction created in the future.
  const result = await pool.query(
    `insert into prediction_outcomes (prediction_id, actual, observed_at)
     select id, $2, now() from predictions where id = $1 and created_at <= now()
     on conflict (prediction_id) do nothing
     returning prediction_id as "predictionId", actual, observed_at as "observedAt"`,
    [predictionId, actual],
  );
  if (!result.rows[0]) {
    const exists = await pool.query("select 1 from predictions where id = $1", [predictionId]);
    const error = new Error(exists.rows[0] ? "An outcome is already recorded for this prediction." : "Prediction does not exist or has a future creation time.") as Error & { code?: string };
    error.code = exists.rows[0] ? "OUTCOME_ALREADY_RECORDED" : "PREDICTION_NOT_AVAILABLE";
    throw error;
  }
  return result.rows[0];
}

export async function getDatabaseSummary() {
  if (!pool) return { recordCount: null, dateRange: null, climateIntegrated: false };
  const result = await pool.query("select count(*)::int as count, min(report_date) as min_date, max(report_date) as max_date from market_data");
  const row = result.rows[0];
  // Climate data is in the enriched CSV but not imported into market_data table
  // The climate features are only used in training/inference when explicitly enabled
  const climateIntegrated = false;
  return {
    recordCount: row?.count ?? 0,
    dateRange: row?.min_date && row?.max_date ? { from: row.min_date, to: row.max_date } : null,
    climateIntegrated,
    climateSource: "SYNTHETIC",
    climateCoverage: null
  };
}

export function clearMemory() {
  predictions.length = 0;
  failures.length = 0;
}
