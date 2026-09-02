from enum import StrEnum

from pydantic import BaseModel, Field


class InvariantKind(StrEnum):
    OWNERSHIP = "ownership"
    ROLE_REQUIRED = "role_required"
    STATE_PRECONDITION = "state_precondition"


class SecurityInvariant(BaseModel):
    resource: str = Field(
        description="Resource name this invariant governs — must match a resource "
        "from the application model"
    )
    endpoint_keys: list[str] = Field(
        description='Which endpoints this invariant applies to, as "METHOD /path" strings'
    )
    kind: InvariantKind
    statement: str = Field(
        description="Precise statement of the rule, e.g. 'Only the user who owns the "
        "order may view, update, or cancel it'"
    )
    rationale: str = Field(
        description="Why this invariant should hold, citing the endpoint structure "
        "and/or evidence provided"
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="0-1 confidence this invariant is actually intended by the application",
    )


class InvariantExtractionResult(BaseModel):
    invariants: list[SecurityInvariant]
