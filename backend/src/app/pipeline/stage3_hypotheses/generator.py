from openai import OpenAI

from app.pipeline.llm_client import call_structured
from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.schema import SecurityInvariant
from app.pipeline.stage3_hypotheses.prompt import SYSTEM_PROMPT, build_user_prompt
from app.pipeline.stage3_hypotheses.schema import Hypothesis, HypothesisGenerationResult


def generate_hypotheses(
    model: ApplicationModel,
    invariants: list[SecurityInvariant],
    client: OpenAI | None = None,
    refuted: list[str] | None = None,
) -> list[Hypothesis]:
    """Stage 3: propose candidate sequential attack chains targeting the given invariants.

    `refuted`: Stage 5's refutation summaries from a previous round, if any — the
    counterexample feedback loop."""
    result = call_structured(
        SYSTEM_PROMPT,
        build_user_prompt(model, invariants, refuted),
        HypothesisGenerationResult,
        tool_name="record_hypotheses",
        tool_description="Record the candidate attack-chain hypotheses.",
        client=client,
    )
    return result.hypotheses
