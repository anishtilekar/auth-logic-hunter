import anthropic

from app.core.config import settings
from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.prompt import SYSTEM_PROMPT, build_user_prompt
from app.pipeline.stage2_invariants.schema import InvariantExtractionResult, SecurityInvariant


def extract_invariants(
    model: ApplicationModel, client: anthropic.Anthropic | None = None
) -> list[SecurityInvariant]:
    """Stage 2: infer security invariants for the model's BOLA-relevant resources.

    Structured via output_format (JSON-schema-constrained response), not a forced
    tool call — for pure extraction with no agentic loop this is the more direct
    surface and it hands back an already-validated Pydantic instance.
    """
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    response = client.messages.parse(
        model=settings.invariant_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(model)}],
        output_format=InvariantExtractionResult,
    )
    if response.parsed_output is None:
        reason = response.stop_reason
        detail = f" ({response.stop_details.explanation})" if response.stop_details else ""
        raise RuntimeError(
            f"Invariant extraction produced no output (stop_reason={reason}){detail}"
        )
    return response.parsed_output.invariants
