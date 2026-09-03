"""Stage 4: encode a bound hypothesis + target invariant as Z3 constraints.

Bounded model checking over the chain: state index 0 is "before step 1",
state k is "after step k". Per resource instance r and state k we track
`owner(r)@k : Int` (an actor id) and `exists(r)@k : Bool`. Transition
semantics per step, by Stage 1's TransitionKind:

  create / capture-from-read : exists@k := True, owner@k := acting actor
  delete                     : exists@k := False
  read / update / action     : no state change
  everything not touched     : framed (unchanged)

The question posed to Z3: does there exist an execution of this exact chain
in which some step *governed by the invariant* is performed in a way the
invariant forbids — assuming the application does NOT enforce the check at
that endpoint (unless the endpoint is in `enforced_endpoints`, i.e. known-
enforced from evidence or a prior replay)?

  SAT   -> the chain structurally reaches a violating state; the model is a
           concrete witness (which actor, which instance, which step) that
           Stage 6 replays against the live app.
  UNSAT -> no execution of this chain can violate the invariant, whatever the
           app does; the unsat core says why.

Modeling assumptions (deliberate, kept small):
  * named actors are distinct authenticated principals;
  * a value captured from a read/list made by actor A is an instance owned by A;
  * for role_required invariants, an actor is privileged iff its name contains
    "admin" — the invariant text is prose, so the required role isn't
    machine-readable yet.
"""

from dataclasses import dataclass, field

import z3

from app.pipeline.stage1_state_model.schema import ApplicationModel, TransitionKind
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant
from app.pipeline.stage3_hypotheses.schema import Hypothesis
from app.pipeline.stage4_encoder.binding import Binding, BoundStep, EncodingError, bind


class UnsupportedInvariantError(EncodingError):
    """Invariant kind has no predicate form yet — a verdict of 'unsupported', not a bug."""


@dataclass
class Encoding:
    binding: Binding
    invariant: SecurityInvariant
    actors: dict[str, z3.ArithRef]
    owner: dict[str, list[z3.ArithRef]]  # instance id -> owner var per state 0..n
    exists: dict[str, list[z3.BoolRef]]
    privileged: dict[str, z3.BoolRef]
    assertions: list[tuple[str, z3.BoolRef]] = field(default_factory=list)  # (label, expr)
    descriptions: dict[str, str] = field(default_factory=dict)  # label -> human text
    violation_terms: list[tuple[int, z3.BoolRef]] = field(default_factory=list)

    def add(self, label: str, description: str, expr: z3.BoolRef) -> None:
        if label in self.descriptions:
            raise ValueError(f"duplicate assertion label {label!r}")
        self.assertions.append((label, expr))
        self.descriptions[label] = description

    def to_smtlib(self) -> str:
        """The exact problem as SMT-LIB 2 — faithful, not decorative: re-parsing
        this text and solving it yields the same verdict (pinned by a test)."""
        # A fresh context so let-binding ids in the text are deterministic across
        # runs (they're hash-cons ids, which the shared default context recycles).
        ctx = z3.Context()
        s = z3.Solver(ctx=ctx)
        for _, expr in self.assertions:
            s.add(expr.translate(ctx))
        header = "".join(f"; {label}: {desc}\n" for label, desc in self.descriptions.items())
        return header + str(s.to_smt2())


_VERB = {
    TransitionKind.CREATE: "create",
    TransitionKind.READ: "read",
    TransitionKind.UPDATE: "update",
    TransitionKind.DELETE: "delete",
    TransitionKind.ACTION: "act on",
}


def _is_privileged_name(actor: str) -> bool:
    return "admin" in actor.lower()


def encode(
    model: ApplicationModel,
    hypothesis: Hypothesis,
    invariant: SecurityInvariant,
    *,
    enforced_endpoints: frozenset[str] = frozenset(),
) -> Encoding:
    if invariant.kind == InvariantKind.STATE_PRECONDITION:
        raise UnsupportedInvariantError(
            "state_precondition invariants have no SMT predicate form yet (prose only)"
        )

    binding = bind(model, hypothesis)
    n = len(binding.steps)

    actors = {a: z3.Int(f"actor:{a}") for a in binding.actors}
    owner = {r: [z3.Int(f"owner:{r}@{k}") for k in range(n + 1)] for r in binding.instances}
    exists = {r: [z3.Bool(f"exists:{r}@{k}") for k in range(n + 1)] for r in binding.instances}
    privileged = {a: z3.Bool(f"privileged:{a}") for a in binding.actors}
    enc = Encoding(binding, invariant, actors, owner, exists, privileged)

    if len(actors) > 1:
        enc.add(
            "actors_distinct",
            f"named actors ({', '.join(binding.actors)}) are distinct principals",
            z3.Distinct(*actors.values()),
        )
    if binding.instances:
        enc.add(
            "init",
            "no chain-introduced instance exists before step 1",
            z3.And(*[z3.Not(exists[r][0]) for r in binding.instances]),
        )

    for step in binding.steps:
        _encode_step(enc, step)

    _encode_violation(enc, invariant, enforced_endpoints)
    return enc


def _encode_step(enc: Encoding, step: BoundStep) -> None:
    k = step.position
    actor = enc.actors[step.actor]
    touched: set[str] = set()

    if step.target is not None:
        r = step.target
        enc.add(
            f"pre{k}",
            f"step {k}: {r} must exist for {step.actor} to {_VERB[step.kind]} it",
            enc.exists[r][k - 1],
        )
        if step.kind == TransitionKind.DELETE:
            touched.add(r)
            enc.add(
                f"step{k}",
                f"step {k}: {step.actor} deletes {r}",
                z3.And(z3.Not(enc.exists[r][k]), enc.owner[r][k] == enc.owner[r][k - 1]),
            )

    if step.creates is not None:
        r = step.creates
        touched.add(r)
        how = "creates" if step.kind == TransitionKind.CREATE else "obtains (from own data)"
        enc.add(
            f"step{k}",
            f"step {k}: {step.actor} {how} {step.resource} {r}, owned by {step.actor}",
            z3.And(enc.exists[r][k], enc.owner[r][k] == actor),
        )

    frame = [
        z3.And(enc.owner[r][k] == enc.owner[r][k - 1], enc.exists[r][k] == enc.exists[r][k - 1])
        for r in enc.binding.instances
        if r not in touched
    ]
    if frame:
        enc.add(f"frame{k}", f"step {k}: all other instances unchanged", z3.And(*frame))


def _governed(step: BoundStep, invariant: SecurityInvariant) -> bool:
    if invariant.endpoint_keys:
        return step.endpoint_key in invariant.endpoint_keys
    # No endpoint list: govern every non-create step on the invariant's resource.
    return step.resource == invariant.resource and step.kind != TransitionKind.CREATE


def _encode_violation(
    enc: Encoding, invariant: SecurityInvariant, enforced_endpoints: frozenset[str]
) -> None:
    governed_desc: list[str] = []
    for step in enc.binding.steps:
        if not _governed(step, invariant):
            continue
        k = step.position
        actor = enc.actors[step.actor]

        if invariant.kind == InvariantKind.OWNERSHIP:
            r = step.target
            if r is None or enc.binding.instances[r].resource != invariant.resource:
                continue
            term: z3.BoolRef = actor != enc.owner[r][k - 1]
            check: z3.BoolRef = actor == enc.owner[r][k - 1]
            what = f"step {k}: {step.actor} {step.endpoint_key} on {r}"
        else:  # ROLE_REQUIRED
            term = z3.Not(enc.privileged[step.actor])
            check = enc.privileged[step.actor]
            what = f"step {k}: {step.actor} {step.endpoint_key}"

        governed_desc.append(what)
        enc.violation_terms.append((k, term))
        if step.endpoint_key in enforced_endpoints:
            enc.add(
                f"enforced{k}",
                f"{step.endpoint_key} is known to enforce this check (evidence/replay)",
                check,
            )

    if invariant.kind == InvariantKind.ROLE_REQUIRED:
        for name, var in enc.privileged.items():
            priv = _is_privileged_name(name)
            level = "a privileged" if priv else "an unprivileged"
            enc.add(
                f"role:{name}", f"{name} is {level} actor (by name)", var if priv else z3.Not(var)
            )

    if not enc.violation_terms:
        enc.add(
            "violation",
            f"no step in the chain touches an endpoint governed by the invariant on "
            f"{invariant.resource!r} - nothing to violate",
            z3.BoolVal(False),
        )
        return

    forbidden = (
        "made by someone other than the instance's owner"
        if invariant.kind == InvariantKind.OWNERSHIP
        else "made by an unprivileged actor"
    )
    enc.add(
        "violation",
        f"some governed access ({'; '.join(governed_desc)}) is {forbidden}",
        z3.Or(*[t for _, t in enc.violation_terms]),
    )
