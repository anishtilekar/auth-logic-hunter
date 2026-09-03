"""Stage 4+5 core: hand-built chains with known SAT/UNSAT outcomes. This is the
safety net for the project's central claim — a finding is *proven*, not guessed —
so each test pins not just the verdict but *why* (witness contents / unsat core)."""

import z3

from app.pipeline.stage4_encoder.encoder import encode
from app.pipeline.stage5_solver.schema import Verdict
from app.pipeline.stage5_solver.solver import (
    match_invariant,
    prove,
    prove_all,
    refutation_summary,
)
from tests.pipeline.solver_fixtures import (
    BOLA,
    INVARIANTS,
    MODEL,
    ORDER_OWNERSHIP,
    ORDER_STATE,
    SAME_ACTOR,
    VEHICLE_OWNERSHIP,
    VIDEO_ADMIN_ONLY,
    chain,
    step,
)

# --- SAT: chains that provably reach a violating state ------------------------


def test_bola_chain_is_sat_with_a_concrete_witness() -> None:
    r = prove(MODEL, BOLA, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.SAT
    assert r.witness is not None
    assert r.witness.violating_steps == [2]
    assert set(r.witness.actors) == {"victim", "attacker"}
    assert r.witness.actors["victim"] != r.witness.actors["attacker"]
    [inst] = r.witness.instances
    assert (inst.id, inst.resource, inst.created_at_step, inst.owner) == (
        "step1.order_id",
        "order",
        1,
        "victim",
    )
    assert "attacker GET /orders/{order_id}" in r.witness.narrative[0]
    assert "owned by victim" in r.witness.narrative[0]
    assert r.reason is None and r.unsat_core == []


def test_violation_is_attributed_only_to_the_non_owner_step() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(2, "victim", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
        step(3, "attacker", "PUT /orders/{order_id}", uses={"order_id": "step1.order_id"}),
    )
    r = prove(MODEL, hyp, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.SAT
    assert r.witness is not None and r.witness.violating_steps == [3]


def test_action_transition_kind_is_governed_too() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(2, "attacker", "POST /orders/{order_id}/return", uses={"order_id": "step1.order_id"}),
    )
    assert prove(MODEL, hyp, ORDER_OWNERSHIP).verdict == Verdict.SAT


def test_id_obtained_from_a_list_is_owned_by_the_lister() -> None:
    # crAPI's vehicle shape: the create call returns no id, so the chain must list
    # first. The captured id is an instance owned by whoever listed.
    hyp = chain(
        step(1, "victim", "POST /vehicles"),
        step(2, "victim", "GET /vehicles", captures="vehicle_id"),
        step(3, "attacker", "GET /vehicles/{vehicle_id}", uses={"vehicle_id": "step2.vehicle_id"}),
        resource="vehicle",
        target=VEHICLE_OWNERSHIP.statement,
    )
    r = prove(MODEL, hyp, VEHICLE_OWNERSHIP)
    assert r.verdict == Verdict.SAT
    assert r.witness is not None
    [inst] = r.witness.instances
    assert (inst.created_at_step, inst.owner) == (2, "victim")
    assert r.witness.violating_steps == [3]


def test_three_actors_get_pairwise_distinct_ids() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(2, "bystander", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
        step(3, "attacker", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
    )
    r = prove(MODEL, hyp, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.SAT and r.witness is not None
    assert len(set(r.witness.actors.values())) == 3
    assert r.witness.violating_steps == [2, 3]


# --- UNSAT: chains that provably cannot violate, with the reason ---------------


def test_same_actor_chain_is_unsat_because_owner_equals_accessor() -> None:
    r = prove(MODEL, SAME_ACTOR, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.UNSAT
    assert r.witness is None
    assert "step1" in r.unsat_core and "violation" in r.unsat_core
    assert r.reason is not None
    assert "owned by victim" in r.reason
    assert r.reason.startswith("no execution of this chain violates the invariant")


def test_deleted_instance_cannot_be_accessed() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(2, "victim", "DELETE /orders/{order_id}", uses={"order_id": "step1.order_id"}),
        step(3, "attacker", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
    )
    r = prove(MODEL, hyp, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.UNSAT
    # The core must name the delete and the existence precondition it breaks —
    # not the ownership terms, which are satisfiable on their own.
    assert {"step2", "pre3"} <= set(r.unsat_core)
    assert "actors_distinct" not in r.unsat_core


def test_known_enforcement_flips_sat_to_unsat_and_names_itself() -> None:
    governed = "GET /orders/{order_id}"
    assert prove(MODEL, BOLA, ORDER_OWNERSHIP).verdict == Verdict.SAT
    r = prove(MODEL, BOLA, ORDER_OWNERSHIP, enforced_endpoints=frozenset({governed}))
    assert r.verdict == Verdict.UNSAT
    assert "enforced2" in r.unsat_core
    assert r.reason is not None and r.reason.startswith("refuted by known enforcement")
    assert governed in r.reason


def test_enforcement_elsewhere_does_not_refute() -> None:
    r = prove(
        MODEL, BOLA, ORDER_OWNERSHIP, enforced_endpoints=frozenset({"PUT /orders/{order_id}"})
    )
    assert r.verdict == Verdict.SAT


def test_chain_that_never_touches_a_governed_endpoint_is_unsat() -> None:
    narrow = ORDER_OWNERSHIP.model_copy(update={"endpoint_keys": ["PUT /orders/{order_id}"]})
    r = prove(MODEL, BOLA, narrow)  # BOLA uses GET, invariant governs only PUT
    assert r.verdict == Verdict.UNSAT
    assert r.unsat_core == ["violation"]
    assert r.reason is not None and "nothing to violate" in r.reason


def test_ownership_on_an_instance_of_another_resource_is_not_governed() -> None:
    # Body-level reference to a vehicle while the invariant is about orders: the
    # order invariant must not claim a violation on the vehicle instance.
    hyp = chain(
        step(1, "victim", "GET /vehicles", captures="vehicle_id"),
        step(2, "attacker", "POST /orders", uses={"vehicle_id": "step1.vehicle_id"}),
    )
    r = prove(MODEL, hyp, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.UNSAT and r.unsat_core == ["violation"]


# --- role_required / unsupported / invalid ------------------------------------


def test_role_required_violated_by_unprivileged_actor() -> None:
    hyp = chain(
        step(1, "victim", "POST /videos", captures="video_id"),
        step(2, "attacker", "DELETE /admin/videos/{video_id}", uses={"video_id": "step1.video_id"}),
        resource="video",
        target=VIDEO_ADMIN_ONLY.statement,
    )
    r = prove(MODEL, hyp, VIDEO_ADMIN_ONLY)
    assert r.verdict == Verdict.SAT and r.witness is not None
    assert r.witness.violating_steps == [2]
    assert "without the required role" in r.witness.narrative[0]


def test_role_required_satisfied_by_admin_actor() -> None:
    hyp = chain(
        step(1, "victim", "POST /videos", captures="video_id"),
        step(2, "admin", "DELETE /admin/videos/{video_id}", uses={"video_id": "step1.video_id"}),
        resource="video",
        target=VIDEO_ADMIN_ONLY.statement,
    )
    r = prove(MODEL, hyp, VIDEO_ADMIN_ONLY)
    assert r.verdict == Verdict.UNSAT
    assert "role:admin" in r.unsat_core


def test_state_precondition_is_reported_unsupported_not_faked() -> None:
    hyp = chain(
        step(1, "victim", "POST /orders", captures="order_id"),
        step(2, "victim", "POST /orders/{order_id}/return", uses={"order_id": "step1.order_id"}),
        target=ORDER_STATE.statement,
    )
    r = prove(MODEL, hyp, ORDER_STATE)
    assert r.verdict == Verdict.UNSUPPORTED
    assert r.smtlib is None and r.witness is None


def test_unbindable_hypothesis_is_invalid_with_the_binding_error() -> None:
    hyp = chain(step(1, "attacker", "GET /orders/{order_id}", uses={"order_id": "step9.x"}))
    r = prove(MODEL, hyp, ORDER_OWNERSHIP)
    assert r.verdict == Verdict.INVALID
    assert r.reason is not None and "step 9" in r.reason


# --- The proof artifacts are real, not decorative -----------------------------


def _solve_smtlib(smtlib: str) -> z3.CheckSatResult:
    s = z3.Solver()
    s.add(z3.parse_smt2_string(smtlib))
    return s.check()


def test_exported_smtlib_reproduces_the_verdict() -> None:
    sat = prove(MODEL, BOLA, ORDER_OWNERSHIP)
    unsat = prove(MODEL, SAME_ACTOR, ORDER_OWNERSHIP)
    assert sat.smtlib and unsat.smtlib
    assert _solve_smtlib(sat.smtlib) == z3.sat
    assert _solve_smtlib(unsat.smtlib) == z3.unsat
    assert "(check-sat)" in sat.smtlib
    assert "; violation:" in sat.smtlib  # labels documented in the trace


def test_witness_actually_satisfies_the_exported_problem() -> None:
    r = prove(MODEL, BOLA, ORDER_OWNERSHIP)
    assert r.smtlib and r.witness
    constraints = z3.parse_smt2_string(r.smtlib)
    victim, attacker = z3.Int("actor:victim"), z3.Int("actor:attacker")

    pinned = z3.Solver()
    pinned.add(constraints)
    pinned.add(victim == r.witness.actors["victim"], attacker == r.witness.actors["attacker"])
    assert pinned.check() == z3.sat

    # Forcing the attacker to be the owner must make the same problem UNSAT — the
    # ownership mismatch really is what the witness hinges on.
    refuted = z3.Solver()
    refuted.add(constraints)
    refuted.add(attacker == z3.Int("owner:step1.order_id@1"))
    assert refuted.check() == z3.unsat


def test_solving_is_deterministic() -> None:
    a, b = prove(MODEL, BOLA, ORDER_OWNERSHIP), prove(MODEL, BOLA, ORDER_OWNERSHIP)
    assert a.witness == b.witness and a.smtlib == b.smtlib


def test_every_assertion_label_is_unique_and_described() -> None:
    enc = encode(MODEL, BOLA, ORDER_OWNERSHIP)
    labels = [label for label, _ in enc.assertions]
    assert len(labels) == len(set(labels)) == len(enc.descriptions)


# --- matching, batching, feedback text ------------------------------------------


def test_match_invariant_exact_then_paraphrase_on_same_resource() -> None:
    assert match_invariant(BOLA, INVARIANTS) is ORDER_OWNERSHIP
    paraphrased = BOLA.model_copy(
        update={"target_invariant_statement": "only the owning user may view or update an order"}
    )
    assert match_invariant(paraphrased, INVARIANTS) is ORDER_OWNERSHIP
    unrelated = BOLA.model_copy(update={"target_invariant_statement": "coupons apply once"})
    assert match_invariant(unrelated, INVARIANTS) is None


def test_prove_all_indexes_results_and_flags_unmatched() -> None:
    orphan = BOLA.model_copy(update={"target_invariant_statement": "coupons apply once"})
    results = prove_all(MODEL, [SAME_ACTOR, orphan, BOLA], INVARIANTS, index_offset=5)
    assert [r.hypothesis_index for r in results] == [5, 6, 7]
    assert [r.verdict for r in results] == [Verdict.UNSAT, Verdict.INVALID, Verdict.SAT]
    assert results[1].invariant_statement is None
    assert results[1].reason is not None and "no extracted invariant" in results[1].reason


def test_refutation_summary_carries_chain_and_reason() -> None:
    r = prove(MODEL, SAME_ACTOR, ORDER_OWNERSHIP)
    text = refutation_summary(SAME_ACTOR, r)
    assert text.startswith("[unsat] order: victim POST /orders -> victim GET /orders/{order_id}.")
    assert r.reason is not None and r.reason in text
