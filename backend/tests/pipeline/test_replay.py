"""Stage 6 replay against a real (if tiny) HTTP server.

The point of this stage is that a proof is not a finding until the live app
agrees, so every test here asserts the *outcome the app produced*, not the
outcome the solver predicted — including the cases where the app wins.
"""

from collections.abc import Iterator

import pytest

from app.pipeline.stage1_state_model.schema import (
    ApplicationModel,
    Endpoint,
    HTTPMethod,
    Resource,
    StateTransition,
    TransitionKind,
)
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant
from app.pipeline.stage3_hypotheses.schema import Hypothesis, RequestStep
from app.pipeline.stage6_replay.replayer import replay
from app.pipeline.stage6_replay.schema import ReplayOutcome
from app.pipeline.stage6_replay.targets import ActorAuth, ReplayTarget
from tests.pipeline import replay_server

_ENDPOINTS: list[tuple[str, str, TransitionKind]] = [
    ("coupon", "POST /api/coupons", TransitionKind.CREATE),
    ("coupon", "GET /api/coupons/{code}", TransitionKind.READ),
    ("coupon", "POST /api/coupons/{code}/redeem", TransitionKind.ACTION),
    ("order", "POST /api/orders", TransitionKind.CREATE),
    ("order", "GET /api/orders/{order_id}", TransitionKind.READ),
]
REDEEM = "POST /api/coupons/{code}/redeem"
ORDER_GET = "GET /api/orders/{order_id}"


def _model() -> ApplicationModel:
    endpoints, transitions = [], []
    resources: dict[str, Resource] = {}
    for resource, key, kind in _ENDPOINTS:
        method, path = key.split(" ", 1)
        params = [p.strip("{}") for p in path.split("/") if p.startswith("{")]
        endpoints.append(
            Endpoint(path=path, method=HTTPMethod(method), path_params=params, resource=resource)
        )
        transitions.append(StateTransition(resource=resource, kind=kind, endpoint_key=key))
        res = resources.setdefault(resource, Resource(name=resource))
        res.endpoint_keys.append(key)
        for p in params:
            if p not in res.id_params:
                res.id_params.append(p)
    return ApplicationModel(
        title="Replay Fixture",
        base_url="",
        resources=resources,
        endpoints=endpoints,
        transitions=transitions,
    )


MODEL = _model()

COUPON_SINGLE_USE = SecurityInvariant(
    resource="coupon",
    endpoint_keys=[REDEEM],
    kind=InvariantKind.SINGLE_USE,
    limit=1,
    statement="A coupon may be redeemed at most once",
    rationale="fixture",
    confidence=0.5,
)
ORDER_OWNERSHIP = SecurityInvariant(
    resource="order",
    endpoint_keys=[ORDER_GET],
    kind=InvariantKind.OWNERSHIP,
    statement="Only the owner may read an order",
    rationale="fixture",
    confidence=0.4,
)


def _step(n: int, actor: str, key: str, **kw: object) -> RequestStep:
    return RequestStep(step=n, actor=actor, endpoint_key=key, description=f"{actor} {key}", **kw)  # type: ignore[arg-type]


def _race_chain() -> Hypothesis:
    return Hypothesis(
        resource="coupon",
        target_invariant_statement=COUPON_SINGLE_USE.statement,
        preconditions=[],
        steps=[
            _step(1, "victim", "POST /api/coupons", captures="code"),
            _step(2, "attacker", REDEEM, uses={"code": "step1.code"}, race_group=1),
            _step(3, "attacker", REDEEM, uses={"code": "step1.code"}, race_group=1),
        ],
        expected_violation="both redeems succeed",
        confidence=0.8,
    )


def _bola_chain() -> Hypothesis:
    return Hypothesis(
        resource="order",
        target_invariant_statement=ORDER_OWNERSHIP.statement,
        preconditions=[],
        steps=[
            _step(1, "victim", "POST /api/orders", captures="order_id"),
            _step(2, "attacker", ORDER_GET, uses={"order_id": "step1.order_id"}),
        ],
        expected_violation="attacker reads the victim's order",
        confidence=0.9,
    )


@pytest.fixture
def vulnerable() -> Iterator[str]:
    yield from replay_server.serve(atomic=False, enforce_ownership=False)


@pytest.fixture
def hardened() -> Iterator[str]:
    yield from replay_server.serve(atomic=True, enforce_ownership=True)


def _target(base_url: str) -> ReplayTarget:
    return ReplayTarget(base_url=base_url, auth=ActorAuth(headers={"X-User": "{actor}"}))


async def test_bola_replay_confirms_against_a_vulnerable_app(vulnerable: str) -> None:
    result = await replay(
        MODEL, _bola_chain(), ORDER_OWNERSHIP, _target(vulnerable), violating_steps=[2]
    )
    assert result.outcome == ReplayOutcome.CONFIRMED
    assert result.violating_steps == [2]
    # The captured id from step 1 really was substituted into step 2's URL.
    assert result.steps[0].captured == {"order_id": "O1"}
    assert result.steps[1].url.endswith("/api/orders/O1")
    assert result.steps[1].status == 200
    assert "not your order" not in result.steps[1].response_excerpt


async def test_bola_replay_is_refuted_when_the_app_enforces_ownership(hardened: str) -> None:
    result = await replay(
        MODEL, _bola_chain(), ORDER_OWNERSHIP, _target(hardened), violating_steps=[2]
    )
    assert result.outcome == ReplayOutcome.REFUTED
    assert result.steps[1].status == 403
    # The feedback that makes the next proof smarter, not just a verdict.
    assert result.enforced_endpoints == [ORDER_GET]


async def test_race_replay_confirms_the_double_redeem(vulnerable: str) -> None:
    result = await replay(
        MODEL, _race_chain(), COUPON_SINGLE_USE, _target(vulnerable), violating_steps=[2, 3]
    )
    assert result.outcome == ReplayOutcome.CONFIRMED
    assert result.violating_steps == [2, 3]
    assert [s.status for s in result.steps[1:]] == [200, 200]
    assert "2 concurrent uses succeeded against a limit of 1" in result.reason
    # Both members were released together rather than run back to back: their
    # start offsets are close, and far below the server's 50 ms window.
    offsets = [s.started_offset_ms for s in result.steps[1:]]
    assert all(o is not None for o in offsets)
    assert abs(offsets[0] - offsets[1]) < 25  # type: ignore[operator]


async def test_race_replay_is_refuted_against_an_atomic_endpoint(hardened: str) -> None:
    result = await replay(
        MODEL, _race_chain(), COUPON_SINGLE_USE, _target(hardened), violating_steps=[2, 3]
    )
    assert result.outcome == ReplayOutcome.REFUTED
    assert sorted(s.status or 0 for s in result.steps[1:]) == [200, 409]
    assert result.enforced_endpoints == [REDEEM]


async def test_failed_setup_is_inconclusive_not_refuted(vulnerable: str) -> None:
    # Step 1 targets a route the server doesn't serve, so step 2 never gets a
    # fair try. Reporting "refuted" here would silently discard a real finding.
    broken = _bola_chain()
    broken.steps[0] = _step(1, "victim", "POST /api/coupons", captures="order_id")
    model = MODEL.model_copy()
    result = await replay(model, broken, ORDER_OWNERSHIP, _target(vulnerable), violating_steps=[2])
    assert result.outcome == ReplayOutcome.INCONCLUSIVE
    assert "never ran" in result.reason


async def test_unreachable_target_reports_error_evidence_not_a_verdict() -> None:
    dead = ReplayTarget(
        base_url="http://127.0.0.1:9",
        auth=ActorAuth(headers={"X-User": "{actor}"}),
        timeout_s=2.0,
    )
    result = await replay(MODEL, _bola_chain(), ORDER_OWNERSHIP, dead, violating_steps=[2])
    assert result.outcome == ReplayOutcome.INCONCLUSIVE
    assert result.steps[0].error is not None


def _sequential_redeem_chain() -> Hypothesis:
    chain = _race_chain()
    for step in chain.steps[1:]:
        step.race_group = None
    return chain


async def test_sequential_repeats_are_refuted_without_claiming_atomicity(vulnerable: str) -> None:
    # The app rejects the second sequential redeem, but that says nothing about
    # whether it holds under concurrency. Marking the endpoint enforced here would
    # suppress the very race proof this target exists to demonstrate.
    result = await replay(MODEL, _sequential_redeem_chain(), COUPON_SINGLE_USE, _target(vulnerable))
    assert result.outcome == ReplayOutcome.REFUTED
    assert [s.status for s in result.steps[1:]] == [200, 409]
    assert result.enforced_endpoints == []
    assert "say nothing about whether it is atomic" in result.reason


async def test_a_governed_step_being_denied_is_a_verdict_not_a_failed_setup(
    hardened: str,
) -> None:
    # Without violating_steps to mark it, a governed step returning 403 must still
    # be judged as enforcement rather than dismissed as a broken setup step.
    result = await replay(MODEL, _bola_chain(), ORDER_OWNERSHIP, _target(hardened))
    assert result.outcome == ReplayOutcome.REFUTED
    assert result.enforced_endpoints == [ORDER_GET]
