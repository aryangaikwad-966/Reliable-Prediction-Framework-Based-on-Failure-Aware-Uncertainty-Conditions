# API

All application routes are under `/api`. Errors return JSON and do not expose stack traces.

## Health

`GET /api/health` returns Node status, database connection state, configured ML URL, and demo mode.

## Predictions

`POST /api/predictions`

```json
{"commodity":"Tomato","market":"Lasalgaon","variety":"Local","horizon":7}
```

Response contains `prediction`, `reliability`, `failureRisk`, `decision`, `signals`, and `reasons`. When `decision` is `ABSTAINED`, `prediction` is always `null`.

`GET /api/predictions` returns the most recent 100 decisions. `GET /api/predictions/:id` retrieves one decision.

## Outcomes and memory

`POST /api/outcomes`

```json
{"predictionId":"pred_...","actual":742}
```

The server computes absolute error, relative error, configurable severity, and stores the contextual case. `POST /api/failure-memory/update` is an alias for compatibility with the research workflow.

`GET /api/failures` and `GET /api/failures/:id` read the adaptive contextual failure memory.

## Research modules

- `GET /api/reliability` — decision-level risk/reliability
- `GET /api/uncertainty` — component signals
- `GET /api/drift` — measured or `NOT_RUN`
- `GET /api/events` — explicitly `NOT_AVAILABLE` until an external source is integrated
- `GET /api/evaluation` — measured metrics or `NOT_RUN`
- `GET /api/experiments` — ablation registry
- `GET /api/data` — server-side dataset summary/pagination contract

## Models

- `POST /api/models/train` — returns the training handoff status
- `GET /api/models` — model registry
- `GET /api/models/:id` — a versioned model record