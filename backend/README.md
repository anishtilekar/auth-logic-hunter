# Backend

FastAPI backend + pipeline for the Neurosymbolic Auth-Logic Hunter. See [PROJECT_PLAN.md](../PROJECT_PLAN.md) at the repo root for phase-by-phase status.

## Setup

```bash
uv sync
uv run uvicorn app.main:app --reload --app-dir src
```

## LLM provider

Stages 2–3 call an LLM through a shared OpenAI-compatible client (`app/pipeline/llm_client.py`), switched by `LLM_ENV` in `.env`:

- `LLM_ENV=dev` (default) — OpenRouter's free-tier GLM 5.2 (`OPENROUTER_API_KEY`). $0 cost, for iteration.
- `LLM_ENV=prod` — Together.ai's DeepSeek V4 Pro (`TOGETHER_API_KEY`). The real model for actual runs and evaluation.

## Checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
