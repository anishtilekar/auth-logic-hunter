"""Race-condition proofs (Phase 7): the same chain must be SAT when the repeats are
concurrent and UNSAT when they are sequential — that gap *is* the race condition."""

import z3

from app.pipeline.stage5_solver.schema import Verdict
from app.pipeline.stage5_solver.solver import prove, refutation_summary
from tests.pipeline.race_fixtures import (
    COUPON_SINGLE_USE,
    MODEL,
    ORDER_OWNERSHIP,
    REDEEM,
    chain,
    redeem_chain,
    step,
)


def test_concurrent_double_redeem_is_sat_with_interleaving_witness() -> None:
    r = prove(MODEL, redeem_chain(concurrent=True), COUPON_SINGLE_USE)
    assert r.verdict == Verdict.SAT
    assert r.witness is not None
    assert r.witness.violating_steps == [2, 3]
    assert any("2 successful uses against a limit of 1" in line for line in r.witness.narrative)
    # The only interleavings that double-redeem are those where both checks land
    # before both writes — the witness must be one of them.
    order = r.witness.order
    assert len(order) == 4
    assert max(order.index("check step 2"), order.index("check step 3")) < min(
        order.index("write step 2"), order.index("write step 3")
    )


def test_sequential_double_redeem_is_unsat_because_each_use_is_atomic() -> None:
    r = prove(MODEL, redeem_chain(concurrent=False), COUPON_SINGLE_USE)
    assert r.verdict == Verdict.UNSAT
    assert {"use2", "use3", "violation"} <= set(r.unsat_core)
    assert r.reason is not None and "atomic" in r.reason


def test_limit_bounds_how_many_concurrent_uses_are_needed() -> None:
    twice = COUPON_SINGLE_USE.model_copy(update={"limit": 2})
    assert prove(MODEL, redeem_chain(concurrent=True, times=2), twice).verdict == Verdict.UNSAT
    r = prove(MODEL, redeem_chain(concurrent=True, times=3), twice)
    assert r.verdict == Verdict.SAT and r.witness is not None
    assert len(r.witness.violating_steps) == 3


def test_known_atomic_endpoint_refutes_the_race() -> None:
    r = prove(
        MODEL,
        redeem_chain(concurrent=True),
        COUPON_SINGLE_USE,
        enforced_endpoints=frozenset({REDEEM}),
    )
    assert r.verdict == Verdict.UNSAT
    assert "enforced3" in r.unsat_core
    assert r.reason is not None and "atomic" in r.reason


def test_different_actors_can_race_the_same_coupon() -> None:
    hyp = chain(
        step(1, "victim", "POST /coupons", captures="code"),
        step(2, "victim", REDEEM, uses={"code": "step1.code"}, race_group=1),
        step(3, "attacker", REDEEM, uses={"code": "step1.code"}, race_group=1),
    )
    assert prove(MODEL, hyp, COUPON_SINGLE_USE).verdict == Verdict.SAT


def test_race_on_a_non_governed_endpoint_is_not_a_violation() -> None:
    hyp = chain(
        step(1, "victim", "POST /coupons", captures="code"),
        step(2, "attacker", "GET /coupons/{code}", uses={"code": "step1.code"}, race_group=1),
        step(3, "attacker", "GET /coupons/{code}", uses={"code": "step1.code"}, race_group=1),
    )
    r = prove(MODEL, hyp, COUPON_SINGLE_USE)
    assert r.verdict == Verdict.UNSAT and r.unsat_core == ["violation"]


def test_malformed_race_groups_are_invalid() -> None:
    lone = chain(
        step(1, "victim", "POST /coupons", captures="code"),
        step(2, "attacker", REDEEM, uses={"code": "step1.code"}, race_group=1),
    )
    r = prove(MODEL, lone, COUPON_SINGLE_USE)
    assert r.verdict == Verdict.INVALID and r.reason is not None and "single member" in r.reason

    split = chain(
        step(1, "victim", "POST /coupons", captures="code"),
        step(2, "attacker", REDEEM, uses={"code": "step1.code"}, race_group=1),
        step(3, "attacker", "GET /coupons/{code}", uses={"code": "step1.code"}),
        step(4, "attacker", REDEEM, uses={"code": "step1.code"}, race_group=1),
    )
    r = prove(MODEL, split, COUPON_SINGLE_USE)
    assert r.verdict == Verdict.INVALID and r.reason is not None and "consecutive" in r.reason


def test_ownership_semantics_still_hold_inside_a_race_group() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(
            2,
            "attacker",
            "GET /orders/{order_id}",
            uses={"order_id": "step1.order_id"},
            race_group=1,
        ),
        step(
            3,
            "attacker",
            "PUT /orders/{order_id}",
            uses={"order_id": "step1.order_id"},
            race_group=1,
        ),
        resource="order",
        target=ORDER_OWNERSHIP.statement,
    )
    r = prove(MODEL, hyp, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.SAT and r.witness is not None
    assert r.witness.violating_steps == [2, 3]


def _solve(smtlib: str) -> z3.CheckSatResult:
    s = z3.Solver()
    s.add(z3.parse_smt2_string(smtlib))
    return s.check()


def test_race_smtlib_reproduces_both_verdicts() -> None:
    sat = prove(MODEL, redeem_chain(concurrent=True), COUPON_SINGLE_USE)
    unsat = prove(MODEL, redeem_chain(concurrent=False), COUPON_SINGLE_USE)
    assert sat.smtlib and unsat.smtlib
    assert _solve(sat.smtlib) == z3.sat
    assert _solve(unsat.smtlib) == z3.unsat


def test_forcing_a_serialized_interleaving_kills_the_race_witness() -> None:
    r = prove(MODEL, redeem_chain(concurrent=True), COUPON_SINGLE_USE)
    assert r.smtlib
    s = z3.Solver()
    s.add(z3.parse_smt2_string(r.smtlib))
    # step 3's check happens after step 2's write: no window left.
    s.add(z3.Int("wr:step2") < z3.Int("chk:step3"))
    assert s.check() == z3.unsat


def test_refutation_summary_marks_race_steps() -> None:
    hyp = redeem_chain(concurrent=True)
    r = prove(MODEL, hyp, COUPON_SINGLE_USE.model_copy(update={"limit": 2}))
    text = refutation_summary(hyp, r)
    assert "[race 1]" in text and text.startswith("[unsat] coupon:")
