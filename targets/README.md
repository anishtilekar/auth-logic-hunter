# Targets

Benchmark/target applications the pipeline runs against. Docs for each live here, not inside the target's own directory — `crapi/` is a git submodule (a clean pinned reference to someone else's repo) and shouldn't have our own files mixed into it.

## crAPI (primary benchmark)

Vendored as a git submodule at `crapi/`, pinned to release `v1.1.6` (not tracking `develop`, so the pipeline is always tested against a known-stable snapshot). Chosen as the primary target because it's also NEO's own benchmark (direct baseline comparison) and it ships known BOLA/IDOR bugs by design. It has **no built-in race conditions** — Phase 7 needs a separate seeded target for that half of the evaluation.

### Starting it

Uses crAPI's own prebuilt images (no local build needed):

```bash
docker compose -f targets/crapi/deploy/docker/docker-compose.yml up -d
```

First pull is a few GB and can take a few minutes. Services report healthy in this order: `postgresdb`/`mongodb`/`mailhog` → `crapi-identity` → `crapi-community` → `crapi-workshop` → `crapi-web`. Watch it with:

```bash
docker compose -f targets/crapi/deploy/docker/docker-compose.yml ps
```

Everything is reached through the `crapi-web` gateway on the host — the individual services (identity/community/workshop) are **not** exposed directly, only proxied through it:

- App: http://localhost:8888 (also https on :8443)
- Mailhog UI (OTP/email capture for signup flows): http://localhost:8025
- Health check: `curl http://localhost:8888/health`

Verified end-to-end (2026-09-01): health check returns 200, and `POST /identity/api/auth/signup` returns a real success response — not just "containers report healthy."

`crapi-chatbot` needs an OpenAI key (`CHATBOT_OPENAI_API_KEY` in `crapi/deploy/docker/.env`) we haven't provided — it may crash-loop, but nothing else `depends_on` it, so it doesn't block the rest of the stack and can be ignored for this project's purposes.

### OpenAPI spec

Static file, no running server needed to read it: [`crapi/openapi-spec/crapi-openapi-spec.json`](crapi/openapi-spec/crapi-openapi-spec.json) — 40 endpoints across `/identity`, `/community`, `/workshop`. Its declared `servers` entry is already `http://localhost:8888`, matching the compose setup above with zero path rewriting needed.

### Relationship to our own `docker/docker-compose.yml`

Two separate, independent compose stacks — not merged:

- `docker/docker-compose.yml` (repo root) — **our** Postgres (findings/runs/invariants) + backend
- `targets/crapi/deploy/docker/docker-compose.yml` — crAPI's own Postgres/Mongo/Chroma/services, entirely self-contained

Verified running simultaneously with no port conflicts — crAPI's internal `postgresdb` isn't exposed to the host, so it doesn't clash with our own Postgres on 5432.

During local development the backend runs natively on the host (`uv run uvicorn ...`, see root README), not inside its own container, so it reaches crAPI directly at `http://localhost:8888` with no cross-container networking to think about. If the backend ever needs to run containerized *and* reach crAPI, it'll need `http://host.docker.internal:8888` instead of `localhost` — not needed yet.

### Resetting state between pipeline runs

Two options, pick based on what you're testing:

- **Full reset** (`./targets/crapi-reset.sh`) — tears down containers and wipes volumes, so the next `up -d` starts from a genuinely fresh DB. Correct, but slow (full re-init + health-check ramp-up each time).
- **Fresh users per run** (cheaper, usually sufficient) — most of crAPI's authorization bugs (BOLA/IDOR on orders, vehicles, etc.) are about ownership *between two different users*, not about the app being in some pristine global state. Signing up new throwaway accounts via `/identity/api/auth/signup` for each pipeline run avoids state pollution without a full reset. Prefer this for iterative pipeline development; use the full reset before an actual evaluation run (Phase 11) so results aren't affected by leftover data from earlier debugging.

### Stopping it

```bash
docker compose -f targets/crapi/deploy/docker/docker-compose.yml down
```

## seeded-race/ (not yet built)

Custom service(s) seeded with planted race-condition bugs — Phase 7.
