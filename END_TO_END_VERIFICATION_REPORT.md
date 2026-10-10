# End-to-End Verification Report

Run on 2026-10-11 (local workspace; no Docker).

| Check | Command / method | Result |
|---|---|---|
| Type safety | `npm run typecheck` | Passed |
| Frontend build | `npm run build` | Passed |
| Node unit tests | `npm test` | 22 tests passed |
| Python decision tests | `cd ml-service && ../.venv/bin/python -m pytest app/test_core.py -q` | 3 passed |
| Database availability | `pg_isready`, bounded `psql` aggregates | PostgreSQL reachable; 5,412,487 market rows, 26,492 imported predictions/outcomes |
| Health path | `GET /api/health` | Express, PostgreSQL, FastAPI, and model artifact reported ready |
| Supported decision path | `POST /api/predictions` for `Tomato/Abohar/Tomato` | 201, `ACCEPTED`, forecast 1789.53 Rs/Quintal |
| Abstention path | `POST /api/predictions` for `Tomato/Khatra/Tomato` | 201, `ABSTAINED`, `prediction: null`, historical-risk reason |
| Out-of-scope path | `POST /api/predictions` for unsupported combination | 422, `OUT_OF_SCOPE`, `prediction: null` |
| History pagination | `GET /api/predictions?limit=2&decision=ABSTAINED` | 2 returned, total 6,689 |
| Offline artifact | `GET /api/research-results` | Verified checked-in ablation JSON returned |
| Outcome integrity | Created accepted prediction, `POST /api/outcomes`, queried `prediction_outcomes` | 201 and exactly one linked outcome; repeat returned 409 |

Browser verification was attempted through the available in-app browser integration, but no browser instance was available in this session. No browser screenshot or UI-click claim is made; the running services and all listed API paths were verified directly.
