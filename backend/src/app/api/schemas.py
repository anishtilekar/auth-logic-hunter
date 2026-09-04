from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.models import RunStatus


class RunCreate(BaseModel):
    target_name: str
    replay: bool = False
    """Fire each proven witness at the live target (Stage 6). Off by default:
    it requires the target to actually be running and sends real requests."""
    base_url: str | None = None
    """Override the target's default base URL for replay."""


class RunSummary(BaseModel):
    id: int
    target_name: str
    status: RunStatus
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    severity_counts: dict[str, int] = {}
    """Findings by derived severity. Computed on read so the dashboard can show a
    breakdown from the list endpoint alone, without fetching every run's detail."""

    model_config = {"from_attributes": True}


class RunDetail(RunSummary):
    application_model: dict[str, Any] | None
    invariants: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    """Each carries a derived `severity` added on read (see api.runs._with_severity)."""
