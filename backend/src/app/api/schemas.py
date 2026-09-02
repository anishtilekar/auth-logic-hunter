from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.models import RunStatus


class RunCreate(BaseModel):
    target_name: str


class RunSummary(BaseModel):
    id: int
    target_name: str
    status: RunStatus
    error: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RunDetail(RunSummary):
    application_model: dict[str, Any] | None
    invariants: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
