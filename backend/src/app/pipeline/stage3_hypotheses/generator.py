import anthropic

from app.core.config import settings
from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.schema import SecurityInvariant
from app.pipeline.stage3_hypotheses.prompt import SYSTEM_PROMPT, build_user_prompt
from app.pipeline.stage3_hypotheses.schema import Hypothesis, HypothesisGenerationResult


def generate_hypotheses(
    model: ApplicationModel,
    invariants: list[SecurityInvariant],
    client: anthropic.Anthropic | None = None,
) -> list[Hypothesis]:
    """Stage 3: propose candidate sequential attack chains targeting the given
    invariants. Same output_format pattern as Stage 2 — structured, validated,
    no forced tool call needed for pure extraction."""
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    response = client.messages.parse(
        model=settings.hypothesis_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(model, invariants)}],
        output_format=HypothesisGenerationResult,
    )
    if response.parsed_output is None:
        reason = response.stop_reason
        detail = f" ({response.stop_details.explanation})" if response.stop_details else ""
        raise RuntimeError(
            f"Hypothesis generation produced no output (stop_reason={reason}){detail}"
        )
    return response.parsed_output.hypotheses
