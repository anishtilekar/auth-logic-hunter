from enum import StrEnum

from pydantic import BaseModel, Field


class ReplayOutcome(StrEnum):
    CONFIRMED = "confirmed"  # the proven violation actually happened against the live app
    REFUTED = "refuted"  # the app enforced the rule — the proof's assumption was wrong
    INCONCLUSIVE = "inconclusive"  # setup failed, so the violating step never got a fair try
    ERROR = "error"  # transport/config failure, not a statement about the app


class StepEvidence(BaseModel):
    step: int
    actor: str
    method: str
    url: str
    status: int | None = None
    elapsed_ms: float = 0.0
    request_body: dict[str, str] | None = None
    response_excerpt: str = ""
    captured: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    race_group: int | None = None
    # Wall-clock offsets from the burst release, so a race's actual interleaving
    # is visible rather than assumed.
    started_offset_ms: float | None = None


class ReplayResult(BaseModel):
    outcome: ReplayOutcome
    reason: str
    base_url: str
    steps: list[StepEvidence] = Field(default_factory=list)
    violating_steps: list[int] = Field(default_factory=list)
    # Endpoints observed to enforce the rule — fed back as `enforced_endpoints`
    # so future proofs against this target refute the same chain up front.
    enforced_endpoints: list[str] = Field(default_factory=list)
