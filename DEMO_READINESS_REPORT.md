# Demo Readiness Report

## Launch

```bash
npm install
pip install -r ml-service/requirements.txt
psql "$DATABASE_URL" -f db/schema.sql
npm run dev:ml
npm run dev
```

Open `http://localhost:5173`; Express is `http://localhost:3001`; FastAPI is `http://localhost:8000`.

## Five-minute demo

1. Open Overview and state that records and outcomes are persisted separately from offline research artifacts.
2. Open System Health; show PostgreSQL and FastAPI/model readiness.
3. Make a supported request: `Tomato / Abohar / Tomato / 7 days` (verified accepted in this environment).
4. Make an abstention request: `Tomato / Khatra / Tomato / 7 days` (verified `ABSTAINED`, null forecast).
5. Submit an unsupported context via the API validation path (the form prevents unsupported combinations); it returns `OUT_OF_SCOPE`, not an abstention.
6. Open Prediction History and filter decisions.
7. Open Model Evaluation and explain `OFFLINE TEST`: combined selective MAE 807.10 vs persistence 418.83 on 26,492 test rows. Do not claim the proposed model beats persistence.

## Limitations

- The current FastAPI model supports Tomato only; model scope is enforced upstream.
- External weather, crop-damage, and policy data are not integrated.
- The browser integration was unavailable during this verification, so no UI screenshot is included.
- Imported database records are historical evaluation imports, not a stream of current production traffic.
