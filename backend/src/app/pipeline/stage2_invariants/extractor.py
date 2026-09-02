from openai import OpenAI

from app.pipeline.llm_client import call_structured
from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.prompt import SYSTEM_PROMPT, build_user_prompt
from app.pipeline.stage2_invariants.schema import InvariantExtractionResult, SecurityInvariant


def extract_invariants(
    model: ApplicationModel, client: OpenAI | None = None
) -> list[SecurityInvariant]:
    """Stage 2: infer security invariants for the model's BOLA-relevant resources."""
    result = call_structured(
        SYSTEM_PROMPT,
        build_user_prompt(model),
        InvariantExtractionResult,
        tool_name="record_invariants",
        tool_description="Record the extracted security invariants.",
        client=client,
    )
    return result.invariants
