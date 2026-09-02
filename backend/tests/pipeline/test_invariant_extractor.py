from unittest.mock import MagicMock

from app.core.config import settings
from app.pipeline.stage1_state_model.schema import (
    ApplicationModel,
    Endpoint,
    HTTPMethod,
    Resource,
    StateTransition,
    TransitionKind,
)
from app.pipeline.stage2_invariants.extractor import extract_invariants
from app.pipeline.stage2_invariants.prompt import build_user_prompt
from app.pipeline.stage2_invariants.schema import (
    InvariantExtractionResult,
    InvariantKind,
    SecurityInvariant,
)


def _sample_model() -> ApplicationModel:
    return ApplicationModel(
        title="Test App",
        base_url="http://localhost",
        resources={
            "order": Resource(
                name="order",
                id_params=["order_id"],
                endpoint_keys=["GET /orders/{order_id}"],
                ownership_evidence=["views.py:1: order = Order.objects.get(id=order_id)"],
            ),
            "signup": Resource(name="signup", id_params=[], endpoint_keys=["POST /signup"]),
        },
        endpoints=[
            Endpoint(path="/orders/{order_id}", method=HTTPMethod.GET, path_params=["order_id"]),
        ],
        transitions=[
            StateTransition(
                resource="order", kind=TransitionKind.READ, endpoint_key="GET /orders/{order_id}"
            ),
        ],
    )


def test_build_user_prompt_includes_only_id_param_resources() -> None:
    prompt = build_user_prompt(_sample_model())
    assert "order" in prompt
    assert "order_id" in prompt
    assert "Order.objects.get(id=order_id)" in prompt
    assert "signup" not in prompt  # no id_params — not a BOLA-relevant resource


def test_extract_invariants_uses_configured_model_and_parses_result() -> None:
    expected = SecurityInvariant(
        resource="order",
        endpoint_keys=["GET /orders/{order_id}"],
        kind=InvariantKind.OWNERSHIP,
        statement="Only the owner may view their order.",
        rationale="No ownership filter found in the lookup.",
        confidence=0.4,
    )
    mock_response = MagicMock()
    mock_response.parsed_output = InvariantExtractionResult(invariants=[expected])
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response

    result = extract_invariants(_sample_model(), client=mock_client)

    assert result == [expected]
    call_kwargs = mock_client.messages.parse.call_args.kwargs
    assert call_kwargs["model"] == settings.invariant_model
    assert call_kwargs["output_format"] is InvariantExtractionResult
