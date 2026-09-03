"""Stage 5: decide each hypothesis with Z3 and interpret the outcome."""

import difflib
import time

import z3

from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant
from app.pipeline.stage3_hypotheses.schema import Hypothesis
from app.pipeline.stage4_encoder.binding import EncodingError
from app.pipeline.stage4_encoder.encoder import Encoding, UnsupportedInvariantError, encode
from app.pipeline.stage5_solver.schema import InstanceWitness, ProofResult, Verdict, Witness

DEFAULT_TIMEOUT_MS = 5_000


def match_invariant(
    hypothesis: Hypothesis, invariants: list[SecurityInvariant]
) -> SecurityInvariant | None:
    """Exact statement match first; otherwise the closest statement on the same
    resource (the LLM often paraphrases), never a weak cross-resource guess."""
    target = hypothesis.target_invariant_statement.strip().lower()
    for inv in invariants:
        if inv.statement.strip().lower() == target:
            return inv
    best, best_ratio = None, 0.0
    for inv in invariants:
        if inv.resource != hypothesis.resource:
            continue
        ratio = difflib.SequenceMatcher(None, inv.statement.lower(), target).ratio()
        if ratio > best_ratio:
            best, best_ratio = inv, ratio
    return best if best_ratio >= 0.5 else None


def prove(
    model: ApplicationModel,
    hypothesis: Hypothesis,
    invariant: SecurityInvariant,
    *,
    hypothesis_index: int = 0,
    enforced_endpoints: frozenset[str] = frozenset(),
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ProofResult:
    started = time.perf_counter()

    def done(
        verdict: Verdict,
        *,
        reason: str | None = None,
        unsat_core: list[str] | None = None,
        witness: Witness | None = None,
        smtlib: str | None = None,
    ) -> ProofResult:
        return ProofResult(
            hypothesis_index=hypothesis_index,
            invariant_statement=invariant.statement,
            verdict=verdict,
            reason=reason,
            unsat_core=unsat_core or [],
            witness=witness,
            smtlib=smtlib,
            solve_time_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    try:
        enc = encode(model, hypothesis, invariant, enforced_endpoints=enforced_endpoints)
    except UnsupportedInvariantError as exc:
        return done(Verdict.UNSUPPORTED, reason=str(exc))
    except EncodingError as exc:
        return done(Verdict.INVALID, reason=str(exc))

    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    tracker = {label: z3.Bool(f"L:{label}") for label, _ in enc.assertions}
    for label, expr in enc.assertions:
        solver.add(z3.Implies(tracker[label], expr))
    result = solver.check(*tracker.values())
    smtlib = enc.to_smtlib()

    if result == z3.sat:
        return done(Verdict.SAT, witness=_witness(enc, solver.model()), smtlib=smtlib)
    if result == z3.unsat:
        core_names = {str(c) for c in solver.unsat_core()}
        core = [label for label in tracker if f"L:{label}" in core_names]
        return done(Verdict.UNSAT, reason=_unsat_reason(enc, core), unsat_core=core, smtlib=smtlib)
    return done(Verdict.UNKNOWN, reason=solver.reason_unknown(), smtlib=smtlib)


def prove_all(
    model: ApplicationModel,
    hypotheses: list[Hypothesis],
    invariants: list[SecurityInvariant],
    *,
    index_offset: int = 0,
    enforced_endpoints: frozenset[str] = frozenset(),
) -> list[ProofResult]:
    results = []
    for i, hyp in enumerate(hypotheses):
        idx = index_offset + i
        inv = match_invariant(hyp, invariants)
        if inv is None:
            results.append(
                ProofResult(
                    hypothesis_index=idx,
                    invariant_statement=None,
                    verdict=Verdict.INVALID,
                    reason=f"no extracted invariant on {hyp.resource!r} matches "
                    f"{hyp.target_invariant_statement!r}",
                )
            )
            continue
        results.append(
            prove(model, hyp, inv, hypothesis_index=idx, enforced_endpoints=enforced_endpoints)
        )
    return results


def refutation_summary(hypothesis: Hypothesis, result: ProofResult) -> str:
    """One line per refuted chain, fed back into Stage 3's next round."""
    chain = " -> ".join(f"{s.actor} {s.endpoint_key}" for s in hypothesis.steps)
    return f"[{result.verdict.value}] {hypothesis.resource}: {chain}. Reason: {result.reason}"


def _actor_name(enc: Encoding, m: z3.ModelRef, value: z3.ExprRef) -> str:
    for name, var in enc.actors.items():
        if z3.is_true(m.eval(var == value, model_completion=True)):
            return name
    return str(value)


def _witness(enc: Encoding, m: z3.ModelRef) -> Witness:
    actors = {
        name: m.eval(var, model_completion=True).as_long() for name, var in enc.actors.items()
    }
    steps = {s.position: s for s in enc.binding.steps}
    instances = []
    owners: dict[str, str] = {}
    for r, inst in enc.binding.instances.items():
        owner = _actor_name(enc, m, m.eval(enc.owner[r][inst.created_at], model_completion=True))
        owners[r] = owner
        instances.append(
            InstanceWitness(
                id=r, resource=inst.resource, created_at_step=inst.created_at, owner=owner
            )
        )

    violating, narrative = [], []
    for k, term in enc.violation_terms:
        if not z3.is_true(m.eval(term, model_completion=True)):
            continue
        violating.append(k)
        s = steps[k]
        if enc.invariant.kind == InvariantKind.OWNERSHIP and s.target in owners:
            inst = enc.binding.instances[s.target]
            narrative.append(
                f"step {k}: {s.actor} {s.endpoint_key} on {inst.resource} {s.target}, "
                f"owned by {owners[s.target]} (introduced at step {inst.created_at})"
            )
        else:
            narrative.append(f"step {k}: {s.actor} {s.endpoint_key} without the required role")
    return Witness(
        actors=actors, instances=instances, violating_steps=violating, narrative=narrative
    )


def _unsat_reason(enc: Encoding, core: list[str]) -> str:
    descs = {label: enc.descriptions[label] for label in core}
    enforced = [d for label, d in descs.items() if label.startswith("enforced")]
    if enforced:
        return "refuted by known enforcement: " + "; ".join(enforced)
    if core == ["violation"]:
        return descs["violation"]
    relevant = [d for label, d in descs.items() if not label.startswith("frame")]
    return "no execution of this chain violates the invariant: " + "; ".join(relevant)
