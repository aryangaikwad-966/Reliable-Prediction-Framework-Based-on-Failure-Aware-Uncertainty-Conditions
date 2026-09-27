import pg from "pg";
import type { FailureRecord, PredictionRecord } from "./research";

const { Pool } = pg;
const connectionString = process.env.DATABASE_URL;
export const dbEnabled = Boolean(connectionString);
const pool = connectionString ? new Pool({ connectionString, max: 5, ssl: process.env.NODE_ENV === "production" ? { rejectUnauthorized: false } : undefined }) : null;

const predictions: PredictionRecord[] = [];
const failures: FailureRecord[] = [];

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
  return result.rows as PredictionRecord[];
}

export async function savePrediction(item: PredictionRecord) {
  predictions.unshift(item);
  if (pool) {
    await pool.query(
      `insert into predictions (id, commodity, market, variety, horizon, prediction, base_prediction, reliability, failure_risk, decision, is_demo, signals, reasons)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       on conflict (id) do nothing`,
      [item.id, item.commodity, item.market, item.variety, item.horizon, item.prediction, item.basePrediction, item.reliability, item.failureRisk, item.decision, item.isDemo, item.signals, item.reasons],
    );
  }
  return item;
}

export async function listFailures() {
  if (!pool) return [...failures];
  const result = await pool.query("select id, prediction_id as \"predictionId\", event_date as date, commodity, market, variety, prediction, actual, absolute_error as \"absoluteError\", relative_error as \"relativeError\", severity, reliability, novelty_score as \"noveltyScore\", drift_score as \"driftScore\", context from failure_memory order by event_date desc limit 100");
  return result.rows as FailureRecord[];
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

export async function getDatabaseSummary() {
  if (!pool) return { recordCount: null, dateRange: null };
  const result = await pool.query("select count(*)::int as count, min(report_date) as min_date, max(report_date) as max_date from market_data");
  const row = result.rows[0];
  return { recordCount: row?.count ?? 0, dateRange: row?.min_date && row?.max_date ? { from: row.min_date, to: row.max_date } : null };
}

export function clearMemory() {
  predictions.length = 0;
  failures.length = 0;
}