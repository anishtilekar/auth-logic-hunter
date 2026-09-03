"""Stage 2/3 prompts carry the race vocabulary: single_use as an invariant kind, and
race_group as the way to express concurrency in a hypothesis."""

from app.pipeline.stage2_invariants.prompt import SYSTEM_PROMPT as STAGE2_SYSTEM
from app.pipeline.stage2_invariants.schema import InvariantExtractionResult
from app.pipeline.stage3_hypotheses.prompt import SYSTEM_PROMPT as STAGE3_SYSTEM
from app.pipeline.stage3_hypotheses.prompt import build_user_prompt
from app.pipeline.stage3_hypotheses.schema import HypothesisGenerationResult
from tests.pipeline.race_fixtures import COUPON_SINGLE_USE, MODEL, ORDER_OWNERSHIP
from tests.pipeline.solver_fixtures import ORDER_STATE


def test_stage2_prompt_and_schema_expose_single_use() -> None:
    assert "single_use" in STAGE2_SYSTEM and "limit" in STAGE2_SYSTEM
    schema = InvariantExtractionResult.model_json_schema()
    assert "limit" in schema["$defs"]["SecurityInvariant"]["properties"]
    assert "single_use" in schema["$defs"]["InvariantKind"]["enum"]


def test_stage3_prompt_targets_single_use_with_race_instructions() -> None:
    prompt = build_user_prompt(MODEL, [COUPON_SINGLE_USE, ORDER_OWNERSHIP, ORDER_STATE])
    assert "A coupon may be redeemed at most once" in prompt
    assert "RACE chain" in prompt and "2 times concurrently" in prompt
    assert "Only the owner may read or update an order" in prompt
    assert "delivered" not in prompt  # state_precondition still excluded
    assert "race_group" in STAGE3_SYSTEM


def test_stage3_tool_schema_carries_race_group() -> None:
    step_schema = HypothesisGenerationResult.model_json_schema()["$defs"]["RequestStep"]
    assert "race_group" in step_schema["properties"]
