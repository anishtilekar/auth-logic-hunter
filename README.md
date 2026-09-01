# Neurosymbolic Auth-Logic Hunter

AI-powered tool that finds multi-step and race-condition authorization/business-logic bugs and proves each finding mathematically with Z3, instead of reporting an LLM's guess.

Full build plan, phase status, and architecture decisions: **[PROJECT_PLAN.md](PROJECT_PLAN.md)** — read that first in any new session.

## Quickstart (localhost)

Backend + database:

```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY
docker compose -f docker/docker-compose.yml up -d
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://localhost:5173 (proxies `/api/*` to the backend on `:8000`).

## Repo layout

```
/backend    FastAPI + pipeline (Python, uv)
/frontend   React + Vite + TypeScript dashboard
/targets    Benchmark/target apps (crAPI, seeded race-condition service)
/docker     docker-compose.yml
```

## Checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run mypy src
cd frontend && npm run lint && npm run build
```
