"""The seeded race target (targets/seeded-race) must be ingestible by Stage 1, and
the hand-crafted double-redeem race must prove SAT against the model Stage 1 builds
from it — with its sequential twin UNSAT."""

from pathlib import Path

import pytest

from app.pipeline.stage1_state_model.builder import build_application_model
from app.pipeline.stage1_state_model.schema import ApplicationModel, TransitionKind
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant
from app.pipeline.stage3_hypotheses.schema import Hypothesis, RequestStep
from app.pipeline.stage5_solver.schema import Verdict
from app.pipeline.stage5_solver.solver import prove

SEEDED_ROOT = Path(__file__).parents[3] / "targets/seeded-race"
REDEEM = "POST /api/coupons/{code}/redeem"

COUPON_INVARIANT = SecurityInvariant(
    resource="coupon",
    endpoint_keys=[REDEEM],
    kind=InvariantKind.SINGLE_USE,
    limit=1,
    statement="A coupon may be redeemed at most once",
    rationale="redeem checks `redeemed` then sets it without synchronization",
    confidence=0.5,
)


def _race(concurrent: bool) -> Hypothesis:
    group = 1 if concurrent else None
    return Hypothesis(
        resource="coupon",
        target_invariant_statement=COUPON_INVARIANT.statement,
        preconditions=["victim and attacker are authenticated users"],
        steps=[
            RequestStep(
                step=1,
                actor="victim",
                endpoint_key="POST /api/coupons",
                description="Victim creates a coupon and receives its code",
                captures="code",
            ),
            RequestStep(
                step=2,
                actor="attacker",
                endpoint_key=REDEEM,
                description="Attacker redeems the coupon",
                uses={"code": "step1.code"},
                race_group=group,
            ),
            RequestStep(
                step=3,
                actor="attacker",
                endpoint_key=REDEEM,
                description="Attacker redeems the same coupon again, overlapping the first",
                uses={"code": "step1.code"},
                race_group=group,
            ),
        ],
        expected_violation="Both redeems return 200; GET shows redemptionCount 2",
        confidence=0.8,
    )


HANDCRAFTED_DOUBLE_REDEEM = _race(concurrent=True)


@pytest.fixture(scope="module")
def model() -> ApplicationModel:
    if not (SEEDED_ROOT / "openapi-spec/seeded-race-openapi.json").is_file():
        pytest.skip("seeded-race target missing")
    return build_application_model(SEEDED_ROOT)


def test_stage1_ingests_the_seeded_target(model: ApplicationModel) -> None:
    assert model.title == "Seeded Race Target"
    assert model.resources["coupon"].id_params == ["code"]
    kinds = {t.endpoint_key: t.kind for t in model.transitions}
    assert kinds["POST /api/coupons"] == TransitionKind.CREATE
    assert kinds["GET /api/coupons/{code}"] == TransitionKind.READ
    assert kinds[REDEEM] == TransitionKind.ACTION


def test_handcrafted_double_redeem_race_is_proven(model: ApplicationModel) -> None:
    r = prove(model, HANDCRAFTED_DOUBLE_REDEEM, COUPON_INVARIANT)
    assert r.verdict == Verdict.SAT
    assert r.witness is not None and r.witness.violating_steps == [2, 3]
    assert r.witness.order  # an explicit interleaving is part of the proof


def test_sequential_twin_is_refuted(model: ApplicationModel) -> None:
    r = prove(model, _race(concurrent=False), COUPON_INVARIANT)
    assert r.verdict == Verdict.UNSAT
