"""Hand-crafted hypothesis against a real, known crAPI bug — proves the Hypothesis
schema can actually express a genuine multi-step BOLA attack chain before Stage 3's
LLM generation is trusted to produce them automatically.

Targets the exact vulnerability Phase 2's source scanner found: workshop/crapi/shop/
views.py:122, `order = Order.objects.get(id=order_id)` — no ownership filter at all.
"""

import json

from app.pipeline.stage3_hypotheses.schema import Hypothesis, RequestStep

HANDCRAFTED_ORDER_BOLA = Hypothesis(
    resource="order",
    target_invariant_statement="Only the user who owns an order may view it",
    preconditions=["victim and attacker are both registered, authenticated crAPI users"],
    steps=[
        RequestStep(
            step=1,
            actor="victim",
            endpoint_key="POST /workshop/api/shop/orders",
            description="Victim places an order, receiving an order_id in the response",
            captures="order_id",
        ),
        RequestStep(
            step=2,
            actor="attacker",
            endpoint_key="GET /workshop/api/shop/orders/{order_id}",
            description="Attacker requests the victim's order using the captured "
            "order_id, authenticated as themself",
            uses={"order_id": "step1.order_id"},
        ),
    ],
    expected_violation="Attacker receives HTTP 200 with the victim's order details, "
    "despite not owning the order",
    confidence=0.9,
)


def test_handcrafted_hypothesis_round_trips_through_json() -> None:
    dumped = HANDCRAFTED_ORDER_BOLA.model_dump_json()
    restored = Hypothesis.model_validate(json.loads(dumped))
    assert restored == HANDCRAFTED_ORDER_BOLA


def test_handcrafted_hypothesis_captures_the_actor_switch() -> None:
    # The core BOLA structure: one actor creates the resource, a *different* actor
    # accesses it using a captured identifier — if this doesn't hold, the schema
    # can't actually express the attack it's meant to represent.
    creator, accessor = HANDCRAFTED_ORDER_BOLA.steps
    assert creator.actor != accessor.actor
    assert creator.captures is not None
    assert accessor.uses[creator.captures] == f"step{creator.step}.{creator.captures}"
