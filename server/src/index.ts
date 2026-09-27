import "dotenv/config";
import cors from "cors";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { checkDatabase, getDatabaseSummary, listFailures, listPredictions, saveFailure, savePrediction } from "./db";
import { buildDemoPrediction, buildDecision, buildDemoPrediction as demoPrediction, classifyFailure, DEFAULT_FAILURE_THRESHOLD, DEFAULT_RELIABILITY_THRESHOLD, demoFailures, demoPredictions, summarizePredictions, evaluateRegression } from "./research";
import type { FailureRecord } from "./research";

const app = express();
const port = Number(process.env.PORT ?? 3001);
const demoMode = process.env.DEMO_MODE !== "false";
app.use(cors());
app.use(express.json({ limit: "1mb" }));

const predictionSchema = z.object({
  commodity: z.string().min(1).max(80),
  market: z.string().min(1).max(120),
  variety: z.string().min(1).max(120),
  horizon: z.number().int().min(1).max(90),
});

const outcomeSchema = z.object({ predictionId: z.string().min(1), actual: z.number().finite().nonnegative() });

async function allPredictions() {
  const stored = await listPredictions();
  return stored.length ? stored : demoMode ? demoPredictions : [];
}

async function allFailures() {
  const stored = await listFailures();
  return stored.length ? stored : demoMode ? demoFailures : [];
}

app.get("/api/health", async (_req, res) => {
  const database = await checkDatabase();
  res.json({ ok: true, service: "node-api", database, mlService: process.env.ML_SERVICE_URL ?? "http://127.0.0.1:8000", demoMode });
});

app.get("/api/metadata", (_req, res) => {
  res.json({ commodities: ["Tomato", "Onion", "Potato", "Wheat"], markets: ["Lasalgaon", "Pune", "Nashik", "Kolar"], varieties: ["Local", "Hybrid", "Red", "FAQ"] });
});

app.get("/api/dashboard", async (_req, res, next) => {
  try {
    const items = await allPredictions();
    const summary = summarizePredictions(items);
    const database = await checkDatabase();
    const storedData = await getDatabaseSummary();

    // Calculate real risk-coverage curve if we have predictions with outcomes
    let riskCoverage: Array<{ coverage: number; risk: number }> = [];
    if (pool && items.length > 0) {
      const predictionsWithOutcomes = await pool.query(`
        SELECT p.prediction, p.base_prediction, p.failure_risk, o.actual
        FROM predictions p
        JOIN prediction_outcomes o ON p.id = o.prediction_id
        WHERE p.decision = 'ACCEPTED' AND p.prediction IS NOT NULL
        ORDER BY p.created_at DESC
        LIMIT 1000
      `);

      if (predictionsWithOutcomes.rows.length > 0) {
        const sorted = predictionsWithOutcomes.rows
          .map((row: any) => ({
            prediction: parseFloat(row.prediction),
            actual: parseFloat(row.actual),
            failureRisk: parseFloat(row.failure_risk)
          }))
          .sort((a, b) => a.failureRisk - b.failureRisk);

        for (let i = 1; i <= sorted.length; i++) {
          const subset = sorted.slice(0, i);
          const errors = subset.map(p => Math.abs(p.actual - p.prediction));
          const risk = errors.reduce((sum, e) => sum + e, 0) / errors.length;
          riskCoverage.push({
            coverage: Number((i / sorted.length).toFixed(2)),
            risk: Number(risk.toFixed(4))
          });
        }
      }
    }

    // Fallback to demo data if no real curve
    if (riskCoverage.length === 0 && items.length > 0) {
      riskCoverage = items.slice().sort((a, b) => a.failureRisk - b.failureRisk).map((item, index, list) => ({ coverage: Number(((index + 1) / list.length).toFixed(2)), risk: item.failureRisk }));
    }

    res.json({
      mode: demoMode || !database.connected ? "DEMO" : "LIVE",
      status: demoMode
        ? "DEMO_MODE is enabled. PostgreSQL is connected, but demo decisions are not experimental evidence."
        : database.connected
          ? "PostgreSQL connected. Values are sourced from stored predictions and outcomes."
          : "Live mode requires a reachable PostgreSQL database.",
      summary,
      predictions: items,
      riskCoverage,
      reliabilityDistribution: summary.reliabilityDistribution,
      forecastActual: [],
      data: storedData,
    });
  } catch (error) { next(error); }
});

app.get("/api/predictions", async (_req, res, next) => { try { res.json({ data: await allPredictions() }); } catch (error) { next(error); } });
app.get("/api/predictions/:id", async (req, res, next) => { try { const item = (await allPredictions()).find((prediction) => prediction.id === req.params.id); if (!item) return res.status(404).json({ error: "Prediction not found" }); return res.json(item); } catch (error) { return next(error); } });

app.post("/api/predictions", async (req, res, next) => {
  try {
    const input = predictionSchema.parse(req.body);
    let result;
    const mlUrl = process.env.ML_SERVICE_URL;
    if (!demoMode && mlUrl) {
      try {
        // First, get features from ML service
        const featuresResponse = await fetch(`${mlUrl}/features`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(input),
          signal: AbortSignal.timeout(10_000)
        });
        if (!featuresResponse.ok) {
          const errorText = await featuresResponse.text();
          throw new Error(`ML service features endpoint returned ${featuresResponse.status}: ${errorText}`);
        }
        const featuresData = await featuresResponse.json() as { features: Record<string, number> };

        // Then, predict with features
        const predictResponse = await fetch(`${mlUrl}/predict`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ ...input, features: featuresData.features }),
          signal: AbortSignal.timeout(10_000)
        });
        if (!predictResponse.ok) throw new Error(`ML service predict endpoint returned ${predictResponse.status}`);
        const value = await predictResponse.json() as { base_prediction: number; signals: Record<string, number> };
        result = buildDecision(value.base_prediction, value.signals as never, { context: input, isDemo: false });
      } catch (error) {
        console.error("ML service error:", error);
        return res.status(503).json({ error: "The live ML service is unavailable. Start FastAPI or enable DEMO_MODE for explicitly labelled demo decisions." });
      }
    } else {
      result = demoPrediction(input);
    }
    await savePrediction(result);
    return res.status(201).json(result);
  } catch (error) { return next(error); }
});

app.get("/api/failures", async (_req, res, next) => { try { res.json({ data: await allFailures() }); } catch (error) { next(error); } });
app.get("/api/failures/:id", async (req, res, next) => { try { const item = (await allFailures()).find((failure) => failure.id === req.params.id); if (!item) return res.status(404).json({ error: "Failure case not found" }); return res.json(item); } catch (error) { return next(error); } });
app.get("/api/uncertainty", async (_req, res) => res.json({ status: "available", methodology: "Weighted signals derived from actual feature distance, model behavior, historical cases, drift, and missing context.", data: (await allPredictions()).map((item) => ({ id: item.id, ...item.signals })) }));
app.get("/api/reliability", async (_req, res) => res.json({ threshold: DEFAULT_RELIABILITY_THRESHOLD, data: (await allPredictions()).map((item) => ({ id: item.id, reliability: item.reliability, failureRisk: item.failureRisk, decision: item.decision })) }));
app.get("/api/drift", async (_req, res, next) => {
  try {
    if (!pool) {
      return res.json({ status: "NOT_RUN", score: null, affectedFeatures: [], reason: "Database connection required for drift detection." });
    }

    // Get recent prediction errors
    const recentResult = await pool.query(`
      SELECT p.prediction, o.actual, p.created_at
      FROM predictions p
      JOIN prediction_outcomes o ON p.id = o.prediction_id
      WHERE p.created_at > NOW() - INTERVAL '30 days'
      ORDER BY p.created_at DESC
      LIMIT 100
    `);

    // Get historical errors
    const historicalResult = await pool.query(`
      SELECT p.prediction, o.actual, p.created_at
      FROM predictions p
      JOIN prediction_outcomes o ON p.id = o.prediction_id
      WHERE p.created_at <= NOW() - INTERVAL '30 days'
      ORDER BY p.created_at DESC
      LIMIT 100
    `);

    if (recentResult.rows.length < 10 || historicalResult.rows.length < 10) {
      return res.json({
        status: "NOT_RUN",
        score: null,
        affectedFeatures: [],
        reason: "Insufficient prediction outcomes for drift detection (need at least 10 recent and 10 historical)."
      });
    }

    const recentErrors = recentResult.rows.map((row: any) => Math.abs(parseFloat(row.actual) - parseFloat(row.prediction)));
    const historicalErrors = historicalResult.rows.map((row: any) => Math.abs(parseFloat(row.actual) - parseFloat(row.prediction)));

    // Calculate drift score
    const recentMean = recentErrors.reduce((sum: number, e: number) => sum + e, 0) / recentErrors.length;
    const historicalMean = historicalErrors.reduce((sum: number, e: number) => sum + e, 0) / historicalErrors.length;
    const driftScore = Math.max(0, Math.min(1, (recentMean - historicalMean) / Math.max(historicalMean, 1)));

    const status = driftScore > 0.3 ? "DRIFT_DETECTED" : "STABLE";

    return res.json({
      status,
      score: Number(driftScore.toFixed(4)),
      affectedFeatures: ["prediction_error"],
      detectionDate: new Date().toISOString(),
      methodology: "Rolling error comparison between recent (30 days) and historical prediction outcomes"
    });
  } catch (error) { return next(error); }
});
app.get("/api/events", (_req, res) => res.json({ status: "NOT_AVAILABLE", message: "External event data not currently integrated.", events: [] }));

app.get("/api/evaluation", async (_req, res, next) => {
  try {
    if (!pool) {
      return res.json({ status: "NOT_RUN", mae: null, rmse: null, mape: null, r2: null, coverage: null, selectiveRisk: null, abstentionRate: null, failureDetectionRate: null, aurc: null });
    }

    // Get predictions with outcomes
    const result = await pool.query(`
      SELECT p.prediction, p.base_prediction, p.decision, p.reliability, p.failure_risk, o.actual
      FROM predictions p
      JOIN prediction_outcomes o ON p.id = o.prediction_id
      WHERE p.decision = 'ACCEPTED' AND p.prediction IS NOT NULL
      ORDER BY p.created_at DESC
      LIMIT 1000
    `);

    if (result.rows.length === 0) {
      return res.json({ status: "NOT_RUN", mae: null, rmse: null, mape: null, r2: null, coverage: null, selectiveRisk: null, abstentionRate: null, failureDetectionRate: null, aurc: null });
    }

    const predictions = result.rows.map((row: any) => ({
      prediction: parseFloat(row.prediction),
      actual: parseFloat(row.actual),
      reliability: parseFloat(row.reliability),
      failureRisk: parseFloat(row.failure_risk)
    }));

    // Calculate regression metrics
    const actuals = predictions.map(p => p.actual);
    const preds = predictions.map(p => p.prediction);
    const metrics = evaluateRegression(actuals, preds);

    // Calculate selective risk (error on accepted predictions)
    const errors = actuals.map((a, i) => Math.abs(a - preds[i]));
    const selectiveRisk = errors.reduce((sum, e) => sum + e, 0) / errors.length;

    // Get total predictions for coverage and abstention rate
    const totalResult = await pool.query("SELECT COUNT(*) as total, SUM(CASE WHEN decision = 'ACCEPTED' THEN 1 ELSE 0 END) as accepted FROM predictions");
    const total = parseInt(totalResult.rows[0].total);
    const accepted = parseInt(totalResult.rows[0].accepted);
    const coverage = total > 0 ? accepted / total : null;
    const abstentionRate = total > 0 ? (total - accepted) / total : null;

    // Calculate failure detection rate (from failure_memory)
    const failureResult = await pool.query("SELECT COUNT(*) as failures FROM failure_memory");
    const failures = parseInt(failureResult.rows[0].failures);
    const failureDetectionRate = total > 0 ? failures / total : null;

    // Calculate AURC (Area Under Risk-Coverage curve)
    const sortedByRisk = [...predictions].sort((a, b) => a.failureRisk - b.failureRisk);
    let aurc = 0;
    for (let i = 1; i <= sortedByRisk.length; i++) {
      const subset = sortedByRisk.slice(0, i);
      const subsetErrors = subset.map((p, idx) => Math.abs(p.actual - p.prediction));
      const subsetRisk = subsetErrors.reduce((sum, e) => sum + e, 0) / subsetErrors.length;
      aurc += subsetRisk;
    }
    aurc = aurc / sortedByRisk.length;

    return res.json({
      status: "MEASURED",
      mae: metrics.mae,
      rmse: metrics.rmse,
      mape: metrics.mape,
      r2: metrics.r2,
      coverage,
      selectiveRisk,
      abstentionRate,
      failureDetectionRate,
      aurc
    });
  } catch (error) { return next(error); }
});
app.get("/api/experiments", async (_req, res, next) => {
  try {
    if (!pool) {
      return res.json({ data: ["BASE", "UNCERTAINTY", "FAILURE_MEMORY", "MEMORY_OOD", "FULL_FRAMEWORK"].map((name) => ({ name, status: "NOT_RUN", metrics: null })) });
    }

    // Get experiment results from database
    const result = await pool.query(`
      SELECT e.id, e.name, e.status, e.started_at, e.completed_at,
             er.metrics, er.coverage, er.selective_risk, er.failure_detection_rate, er.calibration
      FROM experiments e
      LEFT JOIN experiment_results er ON e.id = er.experiment_id
      ORDER BY e.id
    `);

    if (result.rows.length === 0) {
      return res.json({ data: ["BASE", "UNCERTAINTY", "FAILURE_MEMORY", "MEMORY_OOD", "FULL_FRAMEWORK"].map((name) => ({ name, status: "NOT_RUN", metrics: null })) });
    }

    const experiments = result.rows.map((row: any) => ({
      id: row.id,
      name: row.name,
      status: row.status,
      startedAt: row.started_at,
      completedAt: row.completed_at,
      metrics: row.metrics,
      coverage: row.coverage,
      selectiveRisk: row.selective_risk,
      failureDetectionRate: row.failure_detection_rate,
      calibration: row.calibration
    }));

    return res.json({ data: experiments });
  } catch (error) { return next(error); }
});

app.post("/api/experiments", async (req, res, next) => {
  try {
    const { name, configuration } = req.body;

    if (!pool) {
      return res.status(503).json({ error: "Database connection required for experiments" });
    }

    // Create experiment record
    const result = await pool.query(
      "INSERT INTO experiments (name, configuration, status, started_at) VALUES ($1, $2, 'RUNNING', NOW()) RETURNING id",
      [name, JSON.stringify(configuration)]
    );

    const experimentId = result.rows[0].id;

    // Return immediate response (experiment runs asynchronously)
    return res.status(202).json({
      status: "QUEUED",
      experimentId,
      message: "Experiment queued. Run the training script with the experiment configuration to execute."
    });
  } catch (error) { return next(error); }
});
app.get("/api/data", async (_req, res) => res.json({ ...(await getDatabaseSummary()), pagination: { page: 1, pageSize: 50, total: null }, records: [] }));

app.get("/api/failure-memory/context", async (req, res, next) => {
  try {
    const { commodity, market, variety } = req.query;
    if (!commodity || !market) {
      return res.status(400).json({ error: "commodity and market are required" });
    }

    if (!pool) {
      return res.json({ similarFailures: [], historicalFailureRate: 0, message: "Database connection required" });
    }

    // Get similar historical failures
    const result = await pool.query(`
      SELECT id, commodity, market, variety, absolute_error, relative_error, severity, reliability, event_date
      FROM failure_memory
      WHERE commodity = $1 AND market = $2
      ORDER BY event_date DESC
      LIMIT 20
    `, [commodity, market]);

    const similarFailures = result.rows;

    // Calculate historical failure rate
    const failureRate = similarFailures.length > 0
      ? similarFailures.filter((f: any) => f.severity !== "NORMAL").length / similarFailures.length
      : 0;

    return res.json({
      similarFailures,
      historicalFailureRate: Number(failureRate.toFixed(4)),
      count: similarFailures.length
    });
  } catch (error) { return next(error); }
});

app.post("/api/outcomes", async (req, res, next) => {
  try {
    const input = outcomeSchema.parse(req.body);
    const prediction = (await allPredictions()).find((item) => item.id === input.predictionId);
    if (!prediction) return res.status(404).json({ error: "Prediction not found" });
    const base = prediction.prediction ?? prediction.basePrediction;
    const absoluteError = Math.abs(input.actual - base);
    const relativeError = input.actual === 0 ? absoluteError : absoluteError / Math.abs(input.actual);
    const failure: FailureRecord = { id: `failure_${Date.now()}`, predictionId: prediction.id, date: new Date().toISOString(), commodity: prediction.commodity, market: prediction.market, variety: prediction.variety, prediction: prediction.prediction, actual: input.actual, absoluteError: Number(absoluteError.toFixed(4)), relativeError: Number(relativeError.toFixed(4)), severity: classifyFailure(absoluteError, relativeError), reliability: prediction.reliability, noveltyScore: prediction.signals.noveltyScore, driftScore: prediction.signals.driftScore, context: { origin: "observed_outcome", threshold: DEFAULT_FAILURE_THRESHOLD } };
    await saveFailure(failure);
    return res.status(201).json(failure);
  } catch (error) { return next(error); }
});
app.post("/api/failure-memory/update", (req, res, next) => { req.url = "/api/outcomes"; return app._router.handle(req, res, next); });
app.post("/api/models/train", async (_req, res) => res.status(202).json({ status: "QUEUED", message: "Run ml-service/training/train.py with the APMC CSV to train a versioned XGBoost model." }));
app.get("/api/models", (_req, res) => res.json({ data: [], status: "NOT_TRAINED" }));
app.get("/api/models/:id", (_req, res) => res.status(404).json({ error: "No trained model has been recorded." }));

app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  if (error instanceof z.ZodError) return res.status(400).json({ error: "Invalid request", details: error.issues.map((issue) => issue.message) });
  console.error(error);
  return res.status(500).json({ error: "The request could not be completed." });
});

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const distPath = path.join(root, "..", "..", "dist");
app.use(express.static(distPath));
app.get("*", (req, res, next) => req.path.startsWith("/api")
  ? next()
  : res.sendFile(path.join(distPath, "index.html"), (error) => {
    if (error) res.status(404).send("Frontend build not found. Run npm run dev for development.");
  }));

app.listen(port, "0.0.0.0", () => console.log(`Node API listening on 0.0.0.0:${port} (${demoMode ? "demo mode" : "live mode"})`));

export default app;