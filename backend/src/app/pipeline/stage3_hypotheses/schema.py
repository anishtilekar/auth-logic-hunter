from pydantic import BaseModel, Field


class RequestStep(BaseModel):
    step: int = Field(description="1-indexed order in the sequence")
    actor: str = Field(
        description="Symbolic role performing this request, e.g. 'victim' or 'attacker' "
        "— not a real user, concretized at replay time"
    )
    endpoint_key: str = Field(
        description='"METHOD /path" matching an endpoint from the application model — '
        "the method is embedded here, not a separate field"
    )
    description: str = Field(description="One sentence: what this step does and why")
    captures: str | None = Field(
        default=None,
        description="Name this step's response value under, if a later step needs it "
        "(e.g. 'order_id')",
    )
    uses: dict[str, str] = Field(
        default_factory=dict,
        description="Path/body param name -> reference to an earlier step's captured value, "
        "e.g. {'order_id': 'step1.order_id'}",
    )
    race_group: int | None = Field(
        default=None,
        description="Steps sharing the same race_group integer are fired *concurrently* "
        "(a race), not one after another. Such steps must be consecutive. None = sequential.",
    )


class Hypothesis(BaseModel):
    resource: str = Field(
        description="Resource this hypothesis targets — must match a resource "
        "from the application model"
    )
    target_invariant_statement: str = Field(
        description="Which invariant this chain attempts to violate"
    )
    preconditions: list[str] = Field(
        description="Setup assumptions before the chain runs, e.g. 'victim and attacker "
        "are both registered, authenticated users'"
    )
    steps: list[RequestStep]
    expected_violation: str = Field(
        description="What success looks like if the invariant is actually broken"
    )
    confidence: float = Field(
        ge=0, le=1, description="0-1 confidence this chain would actually succeed"
    )


class HypothesisGenerationResult(BaseModel):
    hypotheses: list[Hypothesis]
