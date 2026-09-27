# Replit run notes

This project uses its existing React/Vite + Express + Python service structure.

## Main preview

Run `npm run dev`. Vite listens on `0.0.0.0:5000` and proxies `/api` to the Node API on port `3001`. The project is configured for Replit's proxied host in `vite.config.ts`.

## Environment

Copy `.env.example` to `.env` for local development. `DEMO_MODE=true` is intentional until PostgreSQL has been initialized and the APMC dataset has been ingested. Never put credentials into frontend variables.

## Real data

Place the APMC CSV in `data/`, run `db/schema.sql` against PostgreSQL, ingest with `ml-service/training/ingest.py`, and train with `ml-service/training/train.py`. Only then should live model evidence be treated as measured.