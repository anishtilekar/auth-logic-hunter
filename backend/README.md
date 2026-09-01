# Backend

FastAPI backend + pipeline for the Neurosymbolic Auth-Logic Hunter. See [PROJECT_PLAN.md](../PROJECT_PLAN.md) at the repo root for phase-by-phase status.

## Setup

```bash
uv sync
uv run uvicorn app.main:app --reload --app-dir src
```

## Checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
