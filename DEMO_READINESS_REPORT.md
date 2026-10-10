# Demo Readiness Report

**Audit date:** 2026-10-11  
**Overall status:** **READY WITH LIMITATIONS**

The live stack, model artifact, PostgreSQL database, and three API decision
states were exercised against real project data. The API flow is demonstrable.
Rendered-browser inspection was not possible in this environment; see
limitations and the manual checklist below.

## 1. What was inspected

- React/Vite frontend: `src/main.tsx`, `src/App.tsx`, `src/api.ts`, routes via
  React Router, Vite proxy `/api -> 127.0.0.1:3001`.
- Express API: `server/src/index.ts`; persistence adapter:
  `server/src/db.ts`.
- FastAPI ML service: `ml-service/app/main.py`, `core.py`, and schemas.
- PostgreSQL schema: `db/schema.sql`; ingestion script: `populate_db.py`.
- Artifacts: `ml-service/models/latest.joblib` and
  `20260928175151-tomato.json`.
- Research/data artifacts: `experiment_pipeline.py`, `ablation_study.py`,
  `failure_memory_schema.csv`, `evaluation_results.json`,
  `ablation_results.json`, and the supplied audit/enrichment reports.

`LOCAL_SETUP.md` was not present.

## 2. Live services verified

| Component | Actual endpoint/port | Status | Evidence |
|---|---|---|---|
| React/Vite | `http://127.0.0.1:5173` | Running | HTTP 200 for `/` and `/predictions` fallback |
| Express API | `http://127.0.0.1:3001/api/health` | Running | `ok: true`, PostgreSQL `LIVE` |
| FastAPI ML | `http://127.0.0.1:8000/health` | Running | model available and database configured |
| PostgreSQL | local port 5432 | Running | `pg_isready` accepted connections; API connected |
| Model artifact | `ml-service/models/latest.joblib` | Loaded | FastAPI returned valid feature-based forecasts |

The database contained 5,412,487 `market_data` rows, 26,504 predictions,
26,492 outcomes, and 26,492 failure-memory records after audit cleanup. No
audit-created prediction rows remain.

## 3. End-to-end decision-state tests

All requests below passed through the actual Node API, which calls FastAPI and
persists a prediction before returning its decision. Audit-only rows were
deleted after their persistence checks.

| State | Request | HTTP/result | Verified response evidence |
|---|---|---|---|
| PREDICT (`ACCEPTED`) | `Tomato / Charra / Deshi / 7` | 201 | `prediction: 1452.19`, `reliability: 0.9026`, `failureRisk: 0.0974`, decision `ACCEPTED` |
| ABSTAIN (`ABSTAINED`) | `Tomato / Puwaha / Hybrid / 7` | 201 | `prediction: null`, `basePrediction: 2076.2`, `reliability: 0.6877`, `failureRisk: 0.3123`; reason: similar historical cases had high failure rates |
| OUT_OF_SCOPE | `Quantum potato / Mars / None / 7` | 422 | `decision: OUT_OF_SCOPE`, `prediction: null`, `availableRows: 0`; the ML route was not called |

The ABSTAIN row was queried from PostgreSQL before cleanup. It retained a null
prediction, `ABSTAINED` decision, numerical risk/reliability, serialized
signals, and the explanatory reason. This was a genuine calculated decision,
not a UI-only state.

Additional negative tests passed:

- Natural-language-shaped unsupported input (`solve 2+2`) returned the same
  OUT_OF_SCOPE representation.
- A valid database-backed but unsupported model request (`Onion / Puranpur /
  Red / 7`) returned HTTP 422 `OUT_OF_SCOPE`, null prediction, and the model
  scope explanation; it created no prediction row.
- Missing horizon and horizon `91` returned application validation HTTP 400.
- FastAPI with missing required model features returned HTTP 422.
- FastAPI with no historical rows returned HTTP 422, not an internal error.
- Posting an outcome for an unknown prediction returned HTTP 404.

## 4. Data and failure-memory verification

### Passed

- The enriched CSV was independently queried with DuckDB: all 5,421,343 rows
  had `target_date_h7d = report_date + 7 days`; 4,234,837 had a target.
- `DATA_VALIDATION_REPORT.md` documents series isolation by market code,
  commodity, variety, and price unit; it also documents supported/unsupported
  unit flags and zero target-date mismatches.
- Both experiment scripts define `target_modal_price_h7d` separately from
  feature lists. Features are `feat_*` (plus current permitted inputs in the
  ablation); the target is not a prediction-time feature.
- The experiment code uses chronological train/validation/test splits and
  trains residual/failure estimators on later out-of-sample training segments.
- Every historical `failure_memory` record has a corresponding outcome
  (`failure_without_outcome = 0`) and no outcome timestamp predates its linked
  prediction (`outcome_before_prediction = 0`).
- Severity mappings in the imported database are `NORMAL`, `MODERATE`, and
  `HIGH` (3,522 / 5,856 / 17,114 records respectively); they satisfy the
  schema constraint.

### Fixed during audit

The evaluation import stores source market codes in `failure_memory`, while
the live UI submits market names. FastAPI now resolves the selected
commodity/market/variety to its market code before calculating historical
failure risk. It also filters records to outcomes on or before the selected
series' latest observation date. This restored real failure-memory retrieval
and avoids using later outcomes for that historical as-of series state.

### Important limitation

`failure_memory_schema.csv` records `outcome_observed_at` using the pipeline
run time, not a historical observation time. The live retrieval safeguard uses
the genuine `event_date` (target/outcome date), but the run-time field itself
should not be used as historical availability evidence in future research
claims.

## 5. Research metrics and reproducibility

The saved `ablation_results.json` exactly supports the reported ablation
figures (rounded):

| Method | Saved result |
|---|---:|
| Test samples | 26,492 |
| Persistence MAE | 418.83 Rs/Quintal |
| XGBoost MAE | 886.35 Rs/Quintal |
| Uncertainty-only MAE / coverage | 792.91 / 77.6% |
| Failure-memory MAE / coverage | 870.52 / 81.2% |
| Combined MAE / coverage | 807.10 / 76.5% |
| Persistence at combined mask | 380.37 Rs/Quintal |

`evaluation_results.json` is a distinct saved experiment and reports Base MAE
925.63, Selective MAE 851.28, coverage 74.75%, and threshold 2022.33. It must
not be presented as the ablation table above.

The multi-gigabyte training/ablation scripts were not rerun in this live-demo
audit: rerunning would retrain models and overwrite saved evaluation outputs,
which was outside scope. Their saved outputs and code paths were inspected.
The deployed model metadata is also a separate artifact (Tomato, horizon 7,
artifact MAE 689.28); do not claim it is the exact model behind every saved
ablation metric without a versioned training linkage.

The documented limitation remains: combined selective MAE (807.10) did not
outperform uncertainty-only abstention (792.91).

## 6. Defects fixed and regressions

1. **ML startup configuration:** FastAPI did not load the root `.env`, so a
   documented fresh `npm run dev:ml` could miss its database/model settings.
   It now loads the existing root configuration and uses a project-relative
   model default.
2. **Failure-memory lookup:** Market-name requests could never match imported
   code-based failure records. Correct series-code and as-of-date lookup added.
3. **ABSTAIN persistence:** A non-empty `reasons` array was sent to `jsonb` as
   a PostgreSQL array literal and caused HTTP 500. Signals and reasons are now
   explicitly JSON serialized.
4. **Numeric API contract:** PostgreSQL numerics are normalized to numbers at
   the database boundary. Dashboard average reliability now returns `0.6607`
   rather than `null`.
5. **Validation and test reliability:** FastAPI preserves intentional 422
   validation responses; risk arithmetic rounds its boundary deterministically;
   `test:all` now points at the actual Python test file; the stale TypeScript
   clamping assertion was corrected to reflect weighted risk semantics.
6. **Startup display:** `start.sh` now reports frontend port 5173, matching the
   actual npm script.
7. **Model scope:** The loaded artifact is Tomato-specific, while metadata
   exposes a wider database catalog. FastAPI now rejects a different commodity,
   and Express returns the locked OUT_OF_SCOPE response instead of producing a
   misleading Tomato-model forecast.

Regression results:

- `npm run typecheck` — passed.
- `npm run test:all` — 22 Vitest tests and 3 pytest tests passed.
- `npm run build` — passed. Vite emitted a non-blocking >500 kB bundle warning.
- Final Node/FastAPI health checks and the three-state API flow — passed.

## 7. Startup and recovery

From the repository root, with PostgreSQL running and a configured `.env`:

```bash
npm run dev
npm run dev:ml
```

- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:3001/api/health`
- ML health: `http://localhost:8000/health`
- Database initialization, if genuinely needed: `npm run db:setup`

`./start.sh` can start the frontend/backend/ML pair after checking PostgreSQL,
but do not run it while those services are already running.

Recovery during a presentation:

1. Refresh `/api/health` and `/health` to identify the stopped component.
2. Restart only the failed process with the command above; do not repopulate
   the database or retrain a model.
3. Confirm both health responses, then use the three verified requests in this
   report.
4. If the UI cannot be restored, present the saved genuine evaluation files
   and the API responses—not fabricated screenshots or demo-mode results.

## 8. Live-demo checklist

- [ ] Start PostgreSQL, `npm run dev`, and `npm run dev:ml`.
- [ ] Confirm both health URLs say connected/model available.
- [ ] Open `http://localhost:5173`, navigate to **Predictions**.
- [ ] Demonstrate PREDICT: Tomato / Charra / Deshi / 7 days.
- [ ] Demonstrate ABSTAIN: Tomato / Puwaha / Hybrid / 7 days; confirm **Price
  withheld** and the historical-failure explanation.
- [ ] Demonstrate OUT_OF_SCOPE through the API or an unsupported combination;
  confirm null prediction and no fabricated forecast.
- [ ] Disclose that the ablation artifacts favor uncertainty-only over the
  combined method and that external events are not integrated.

## 9. Not verified / limitations to disclose

- **Not visually verified:** Browser automation was unavailable (`No browser is
  available`), so I could not inspect rendered DOM, browser console, loading
  animation, error styling, page refresh interaction, or navigation clicks.
  HTTP route fallback was verified for `/` and `/predictions`; perform the
  checklist above in a local browser before the presentation.
- **Not simulated:** A live database outage was not induced, to avoid
  interrupting the working demo database. The FastAPI unavailable-service path
  was inspected in source but not executed against a stopped service.
- **Not rerun:** Full enrichment/training/ablation reproduction, because it
  would be an unnecessary multi-gigabyte retraining run and can overwrite
  saved outputs.
- **UI contract caveat:** OUT_OF_SCOPE is API-verified. The UI source has an
  OUT_OF_SCOPE rendering branch, but it cannot be selected through the normal
  database-backed dropdowns; use an API client for that part of the demo.
- **Scope:** The live metadata dropdown exposes all database commodities, but
  the loaded model is Tomato-specific. Non-Tomato selections now fail safely as
  OUT_OF_SCOPE; use the verified Tomato examples for forecasting.
