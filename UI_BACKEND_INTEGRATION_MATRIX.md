# UI–Backend Integration Matrix

| UI area | Action / handler | API and source | Response/UI state | Failure state | Test status |
|---|---|---|---|---|---|
| Overview | Initial load, Refresh | `GET /api/dashboard`; PostgreSQL `predictions`, `prediction_outcomes`, `market_data` | Stored summary and recent decisions | Global retry banner | Verified by live API |
| Make prediction | `createPrediction` | `POST /api/predictions` → `POST /features`, `POST /predict` on FastAPI → `predictions` | Real decision, null when abstained, signals/reasons | 400 validation, 422 out-of-scope, 503 ML unavailable | Live supported, abstained, and out-of-scope checks |
| Prediction history | `getPredictions(offset, decision)` | `GET /api/predictions?limit&offset&decision`; `predictions` | Paged/filterable audit table | Truthful unavailable state | Live API verified |
| Reliability / uncertainty | Route queries | `GET /api/evaluation`, `/api/reliability`, `/api/uncertainty` | Persisted outcomes/signals | `NOT_RUN` where no outcome set exists | API verified |
| Failure memory | Route query | `GET /api/failures`; `failure_memory` | Recorded outcome cases | Empty/unavailable state | API verified |
| Outcome recording | `submitOutcome` | `POST /api/outcomes`; `prediction_outcomes` then `failure_memory` | Confirmed outcome and severity | 404 unknown, 409 duplicate | Live write/read verified |
| Model evaluation | Route query | `GET /api/research-results`; checked-in `ablation_results.json` | Explicitly labelled offline test table | Artifact-unavailable state | Live API verified |
| Dataset explorer | Route query | `GET /api/data`; bounded `market_data` aggregate | Row count/date range only | Loading/unavailable values | Live DB queried |
| System health | Route query | `GET /api/health` → PostgreSQL check + FastAPI `/health` | Separates reachability and readiness | Partial/unavailable badges | Live API verified |

Notes: FastAPI owns feature generation, model inference, novelty scoring, and the current historical failure-risk lookup. Express validates scope, orchestrates calls, and persists decisions. The browser never calculates model values. The database contains imported evaluation records; offline metrics are kept visually distinct from operational aggregate metrics.
