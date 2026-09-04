# Neurosymbolic Auth-Logic Hunter

Finds multi-step and race-condition authorization / business-logic bugs in web APIs, proves each one with Z3, and then reproduces it against the running app — instead of reporting an LLM's guess.

A finding only reaches you with three things attached: the attack chain, the SMT proof that the chain can violate a stated invariant, and the live HTTP evidence that it actually did. Chains the solver refutes, or that the app turns out to enforce, are kept and shown as `info` rather than quietly dropped.

Full build plan, phase status, and architecture decisions: **[PROJECT_PLAN.md](PROJECT_PLAN.md)** — read that first in any new session.

## How it works

| Stage | What it does |
|---|---|
| 1 · State model | Parses the target's OpenAPI spec into resources/endpoints/transitions, and scans its source for ownership checks and check-then-act (raceable) patterns |
| 2 · Invariants | An LLM proposes the security rules that *should* hold — ownership, role, single-use — with a confidence and a rationale citing the evidence |
| 3 · Hypotheses | An LLM proposes multi-step attack chains, including concurrent (race) chains, that would violate them |
| 4 · Encoder | Binds each chain to the model and encodes it as SMT constraints, searching every interleaving for races |
| 5 · Solver | Z3 decides it: `sat` yields a concrete witness, `unsat` an unsat core. Refuted chains feed back into stage 3 |
| 6 · Replay | Fires each proven witness at the live app and reports `confirmed` / `refuted` / `inconclusive` with per-request evidence |

## Quickstart (localhost)

**Prerequisites:** Docker Desktop, Node 22+, [uv](https://docs.astral.sh/uv/), and JDK 17 + Maven (only for the seeded race target).

**1. Configure.** Copy `.env.example` to `.env` and set a key for the tier you want. `LLM_ENV=dev` (the default) uses OpenRouter's free GLM 5.2 and needs only `OPENROUTER_API_KEY`.

```bash
cp .env.example .env
```

**2. Start Postgres.**

```bash
docker compose -f docker/docker-compose.yml up -d postgres
```

> **Windows:** if Docker Desktop fails to start with `starting services: initializing ... Engine: listening on unix://...: remove ...: The file cannot be accessed by the system`, run `powershell -ExecutionPolicy Bypass -File scripts/start-docker.ps1`. That error is a stale-socket bug in Docker Desktop, and "Reset to factory defaults" does **not** fix it — the script does. See the comments at the top of the script for the details.

**3. Run the backend.**

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --app-dir src --port 8000
```

**4. Run the dashboard** (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — it proxies `/api/*` to the backend on `:8000`.

### Start a run

From the dashboard's **New run**, or directly:

```bash
curl -X POST localhost:8000/runs -H "Content-Type: application/json" -d '{"target_name":"crapi"}'
```

Pass `"replay": true` to also fire each proven witness at the live target (off by default — it sends real requests and needs the target running).

Each completed run has a self-contained, printable HTML report at `/runs/<id>/report`, linked from the run page.

### Targets

**crAPI** (the primary benchmark, vendored as a submodule) — start it with its own compose file:

```bash
docker compose -f targets/crapi/deploy/docker/docker-compose.yml up -d
```

**seeded-race** — a small Spring Boot coupon service with a deliberately planted non-atomic double-redeem, since crAPI has no race conditions. This is the end-to-end demo for the race half of the pipeline:

```bash
cd targets/seeded-race/services/coupon-service
mvn -q -DskipTests package
java -jar target/coupon-service-0.1.0.jar     # listens on :8090
```

Then run it with replay on:

```bash
curl -X POST localhost:8000/runs -H "Content-Type: application/json" \
  -d '{"target_name":"seeded-race","replay":true}'
```

See [targets/README.md](targets/README.md) for more, including how to reproduce the planted bug by hand.

## Repo layout

```
/backend    FastAPI + the six-stage pipeline (Python, uv)
/frontend   React + Vite + TypeScript dashboard
/targets    Benchmark/target apps (crAPI, seeded race-condition service)
/docker     docker-compose.yml for Postgres
/scripts    Local dev helpers
```

## Checks

```bash
cd backend  && uv run ruff check . && uv run mypy src && uv run pytest
cd frontend && npm run lint && npm run build
```
