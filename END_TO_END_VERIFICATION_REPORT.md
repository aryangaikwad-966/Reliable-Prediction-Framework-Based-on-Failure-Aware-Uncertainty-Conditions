# End-to-End Verification Report

Run on 2026-10-11 (local workspace; no Docker).

| Check | Command / method | Result |
|---|---|---|
| Type safety | `npm run typecheck` | Passed |
| Frontend build | `npm run build` | Passed |
| Node unit tests | `npm test` | 32 tests passed, including detailed frontend decision-response templates and legacy/malformed stored-reason normalization |
| Python decision tests | `cd ml-service && python3 -m pytest app/test_core.py -q` | 3 passed |
| Database availability | `pg_isready`, bounded `psql` aggregates | PostgreSQL reachable; 5,412,487 market rows, 26,492 imported predictions/outcomes |
| Health path | `GET /api/health` | Express, PostgreSQL, FastAPI, and model artifact reported ready |
| ML response contract | Live `POST /features` then `POST /predict` for `Onion/Abohar/Onion` | Returned `base_prediction`, `prediction`, `failure_probability`, `reliability`, `decision`, `reasons`, and the six documented signals. No separate reason-code or explanation field was returned. |
| Supported decision path | `POST /api/predictions` for `Onion/Abohar/Onion` | 201, `ACCEPTED`, forecast 1185.639404296875 Rs/Quintal; ML decision/signals/values preserved by the gateway |
| Abstention path | `GET /api/predictions?limit=3&decision=ABSTAINED` | Stored API record: `ABSTAINED`, `prediction: null`, verified historical-risk reason and signal returned |
| Out-of-scope path | `POST /api/predictions` for unsupported combination | 422, `OUT_OF_SCOPE`, `prediction: null`, actual scope-validation `error` returned |
| History pagination | `GET /api/predictions?limit=2&decision=ABSTAINED` | 2 returned, total 6,689 |
| Offline artifact | `GET /api/research-results` | Verified checked-in ablation JSON returned |
| Outcome integrity | Created accepted prediction, `POST /api/outcomes`, queried `prediction_outcomes` | 201 and exactly one linked outcome; repeat returned 409 |

| UI decision-response build | `npm run typecheck`, `npm run build` | Passed; UI uses centralized accepted/abstained/out-of-scope templates, preserves API evidence, withholds invalid/non-accepted forecasts, and marks missing fields unavailable |

Browser verification was attempted through the available in-app browser integration after starting the Vite UI, Node API, and FastAPI service, but no browser instance was available in this session. No browser screenshot or UI-click claim is made; the running services and the listed API paths were verified directly.
