from unittest.mock import MagicMock

from app.core.config import settings
from app.pipeline.stage1_state_model.schema import (
    ApplicationModel,
    Endpoint,
    HTTPMethod,
    Resource,
)
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant
from app.pipeline.stage3_hypotheses.generator import generate_hypotheses
from app.pipeline.stage3_hypotheses.prompt import build_user_prompt
from app.pipeline.stage3_hypotheses.schema import (
    Hypothesis,
    HypothesisGenerationResult,
    RequestStep,
)


def _sample_model() -> ApplicationModel:
    return ApplicationModel(
        title="Test App",
        base_url="http://localhost",
        resources={"order": Resource(name="order", id_params=["order_id"])},
        endpoints=[
            Endpoint(
                path="/orders",
                method=HTTPMethod.POST,
                path_params=[],
                resource="order",
            ),
            Endpoint(
                path="/orders/{order_id}",
                method=HTTPMethod.GET,
                path_params=["order_id"],
                resource="order",
            ),
        ],
        transitions=[],
    )


def _sample_invariants() -> list[SecurityInvariant]:
    return [
        SecurityInvariant(
            resource="order",
            endpoint_keys=["GET /orders/{order_id}"],
            kind=InvariantKind.OWNERSHIP,
            statement="Only the owner may view their order.",
            rationale="No ownership filter found in the lookup.",
            confidence=0.4,
        ),
        SecurityInvariant(
            resource="order",
            endpoint_keys=["POST /orders"],
            kind=InvariantKind.STATE_PRECONDITION,
            statement="An order must reference a valid product.",
            rationale="Not a BOLA-relevant rule.",
            confidence=0.8,
        ),
    ]


def test_build_user_prompt_includes_only_ownership_invariants() -> None:
    prompt = build_user_prompt(_sample_model(), _sample_invariants())
    assert "Only the owner may view their order" in prompt
    assert "must reference a valid product" not in prompt  # state_precondition filtered out
    assert "GET /orders/{order_id}" in prompt


def test_generate_hypotheses_uses_configured_model_and_parses_result() -> None:
    expected = Hypothesis(
        resource="order",
        target_invariant_statement="Only the owner may view their order.",
        preconditions=["victim and attacker are both registered users"],
        steps=[
            RequestStep(
                step=1,
                actor="victim",
                endpoint_key="POST /orders",
                description="Victim creates an order",
                captures="order_id",
            ),
            RequestStep(
                step=2,
                actor="attacker",
                endpoint_key="GET /orders/{order_id}",
                description="Attacker fetches it",
                uses={"order_id": "step1.order_id"},
            ),
        ],
        expected_violation="Attacker sees the victim's order",
        confidence=0.7,
    )
    mock_response = MagicMock()
    mock_response.parsed_output = HypothesisGenerationResult(hypotheses=[expected])
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response

    result = generate_hypotheses(_sample_model(), _sample_invariants(), client=mock_client)

    assert result == [expected]
    call_kwargs = mock_client.messages.parse.call_args.kwargs
    assert call_kwargs["model"] == settings.hypothesis_model
    assert call_kwargs["output_format"] is HypothesisGenerationResult
