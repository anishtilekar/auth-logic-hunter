"""Structural binding (Stage 4, pre-Z3): ill-formed chains must fail loudly with a
precise EncodingError, never encode to something vacuous."""

import pytest

from app.pipeline.stage1_state_model.schema import TransitionKind
from app.pipeline.stage4_encoder.binding import EncodingError, bind
from tests.pipeline.solver_fixtures import MODEL, chain, step


def test_unknown_endpoint() -> None:
    with pytest.raises(EncodingError, match="unknown endpoint"):
        bind(MODEL, chain(step(1, "victim", "POST /nope")))


def test_reference_must_be_stepN_name() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(2, "attacker", "GET /orders/{order_id}", uses={"order_id": "the victim's id"}),
    )
    with pytest.raises(EncodingError, match="not a 'stepN.name' reference"):
        bind(MODEL, hyp)


def test_forward_reference_is_rejected() -> None:
    hyp = chain(
        step(1, "attacker", "GET /orders/{order_id}", uses={"order_id": "step2.order_id"}),
        step(2, "victim", "POST /orders", captures="order_id"),
    )
    with pytest.raises(EncodingError, match="does not precede it"):
        bind(MODEL, hyp)


def test_reference_to_uncaptured_name_is_rejected() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(2, "attacker", "GET /orders/{order_id}", uses={"order_id": "step1.vehicle_id"}),
    )
    with pytest.raises(EncodingError, match="does not capture 'vehicle_id'"):
        bind(MODEL, hyp)


def test_unbound_path_param_is_rejected() -> None:
    # A "guess the id" single request: not a chain, and not something we can prove
    # anything about — it must not silently become a free symbolic instance.
    hyp = chain(step(1, "attacker", "GET /orders/{order_id}"))
    with pytest.raises(EncodingError, match="path param 'order_id'.*not bound"):
        bind(MODEL, hyp)


def test_duplicate_step_numbers_are_rejected() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(1, "attacker", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
    )
    with pytest.raises(EncodingError, match="duplicate step numbers"):
        bind(MODEL, hyp)


def test_create_capture_introduces_instance_owned_by_creator() -> None:
    b = bind(
        MODEL,
        chain(
            step(1, "victim", "POST /orders", captures="order_id"),
            step(2, "attacker", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
        ),
    )
    assert list(b.instances) == ["step1.order_id"]
    assert b.instances["step1.order_id"].resource == "order"
    assert b.instances["step1.order_id"].created_at == 1
    assert b.steps[0].creates == "step1.order_id" and b.steps[0].kind == TransitionKind.CREATE
    assert b.steps[1].target == "step1.order_id" and b.steps[1].creates is None
    assert b.actors == ["victim", "attacker"]


def test_capture_from_list_read_introduces_instance() -> None:
    b = bind(
        MODEL,
        chain(
            step(1, "victim", "POST /vehicles"),
            step(2, "victim", "GET /vehicles", captures="vehicle_id"),
            step(
                3, "attacker", "GET /vehicles/{vehicle_id}", uses={"vehicle_id": "step2.vehicle_id"}
            ),
        ),
    )
    inst = b.instances["step2.vehicle_id"]
    assert inst.created_at == 2 and inst.resource == "vehicle"
    assert b.steps[1].kind == TransitionKind.READ and b.steps[1].creates == "step2.vehicle_id"
    assert b.steps[2].target == "step2.vehicle_id"


def test_capture_on_targeted_step_is_an_alias_not_a_new_instance() -> None:
    b = bind(
        MODEL,
        chain(
            step(1, "victim", "POST /orders", captures="order_id"),
            step(
                2,
                "victim",
                "GET /orders/{order_id}",
                uses={"order_id": "step1.order_id"},
                captures="oid",
            ),
            step(3, "attacker", "PUT /orders/{order_id}", uses={"order_id": "step2.oid"}),
        ),
    )
    assert list(b.instances) == ["step1.order_id"]
    assert b.steps[1].creates is None
    assert b.steps[2].target == "step1.order_id"


def test_target_prefers_the_resource_id_path_param_over_body_refs() -> None:
    b = bind(
        MODEL,
        chain(
            step(1, "victim", "POST /orders", captures="order_id"),
            step(2, "victim", "GET /vehicles", captures="vehicle_id"),
            step(
                3,
                "attacker",
                "POST /orders/{order_id}/return",
                uses={"vehicle_id": "step2.vehicle_id", "order_id": "step1.order_id"},
            ),
        ),
    )
    assert b.steps[2].target == "step1.order_id"


def test_steps_are_ordered_by_declared_number() -> None:
    b = bind(
        MODEL,
        chain(
            step(2, "attacker", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
            step(1, "victim", "POST /orders", captures="order_id"),
        ),
    )
    assert [s.actor for s in b.steps] == ["victim", "attacker"]
    assert [s.position for s in b.steps] == [1, 2]
