"""End-to-end on real Stage 1 output: the hand-crafted order BOLA from Phase 5 must
prove SAT against the actual crAPI application model, and its same-actor twin UNSAT."""

from pathlib import Path

import pytest

from app.pipeline.stage1_state_model.builder import build_application_model
from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant
from app.pipeline.stage3_hypotheses.schema import RequestStep
from app.pipeline.stage5_solver.schema import Verdict
from app.pipeline.stage5_solver.solver import prove
from tests.pipeline.test_hypothesis_handcrafted import HANDCRAFTED_ORDER_BOLA

CRAPI_ROOT = Path(__file__).parents[3] / "targets/crapi"

ORDER_INVARIANT = SecurityInvariant(
    resource="order",
    endpoint_keys=[
        "GET /workshop/api/shop/orders/{order_id}",
        "PUT /workshop/api/shop/orders/{order_id}",
    ],
    kind=InvariantKind.OWNERSHIP,
    statement=HANDCRAFTED_ORDER_BOLA.target_invariant_statement,
    rationale="Order.objects.get(id=order_id) has no ownership filter",
    confidence=0.4,
)


@pytest.fixture(scope="module")
def model() -> ApplicationModel:
    if not (CRAPI_ROOT / "openapi-spec/crapi-openapi-spec.json").is_file():
        pytest.skip("crAPI submodule not checked out (empty dir counts as missing)")
    return build_application_model(CRAPI_ROOT)


def test_handcrafted_order_bola_is_proven_against_real_crapi_model(
    model: ApplicationModel,
) -> None:
    r = prove(model, HANDCRAFTED_ORDER_BOLA, ORDER_INVARIANT)
    assert r.verdict == Verdict.SAT
    assert r.witness is not None
    assert r.witness.violating_steps == [2]
    [inst] = r.witness.instances
    assert (inst.resource, inst.owner) == ("order", "victim")


def test_same_actor_twin_is_refuted_against_real_crapi_model(model: ApplicationModel) -> None:
    steps = [
        HANDCRAFTED_ORDER_BOLA.steps[0],
        RequestStep(**{**HANDCRAFTED_ORDER_BOLA.steps[1].model_dump(), "actor": "victim"}),
    ]
    twin = HANDCRAFTED_ORDER_BOLA.model_copy(update={"steps": steps})
    r = prove(model, twin, ORDER_INVARIANT)
    assert r.verdict == Verdict.UNSAT
    assert "violation" in r.unsat_core
