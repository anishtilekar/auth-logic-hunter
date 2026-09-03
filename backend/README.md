# Backend

FastAPI backend + pipeline for the Neurosymbolic Auth-Logic Hunter. See [PROJECT_PLAN.md](../PROJECT_PLAN.md) at the repo root for phase-by-phase status.

## Setup

```bash
uv sync
uv run uvicorn app.main:app --reload --app-dir src
```

## LLM provider

Stages 2–3 call an LLM through a shared OpenAI-compatible client (`app/pipeline/llm_client.py`), switched by `LLM_ENV` in `.env`:

- `LLM_ENV=dev` (default) — OpenRouter's free-tier GLM 5.2 (`OPENROUTER_API_KEY`). $0 cost, tool-calling confirmed, the safe choice for iteration.
- `LLM_ENV=nvidia` — build.nvidia.com's free endpoint for DeepSeek V4 Pro (`NVIDIA_API_KEY`). Same model as `prod`, so dev-testing here is representative of real production behavior — but tool-calling support isn't confirmed for this specific endpoint yet, unlike the `dev` tier. Don't use for the actual Phase 11 evaluation numbers even once confirmed working — it's a "prototyping" tier.
- `LLM_ENV=prod` — Together.ai's DeepSeek V4 Pro (`TOGETHER_API_KEY`). The real model for actual runs and evaluation.

## Proof engine (Stages 4–5)

`app/pipeline/stage4_encoder` binds each hypothesis onto the application model (rejecting dangling `stepN.x` references, unknown endpoints, unbound path params) and encodes it as bounded-model-checking constraints over per-instance `owner`/`exists` state; `app/pipeline/stage5_solver` decides it with Z3. `sat` = the chain provably reaches a violating state (concrete witness attached, for Stage 6 replay); `unsat` = it provably cannot (unsat core + reason attached, fed back into Stage 3's next round). Every result carries the exact SMT-LIB problem. Z3 is CPU-only (`z3-solver` wheel, no native build step).

Race conditions (Phase 7): a `single_use` invariant carries a `limit`; hypothesis steps sharing a `race_group` are fired concurrently, and the encoder gives each a symbolic check/write event time so Z3 searches every interleaving. The same chain is `sat` concurrent and `unsat` sequential — that gap is the race. The seeded target for this lives in `targets/seeded-race` (see `targets/README.md`).

## Checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
