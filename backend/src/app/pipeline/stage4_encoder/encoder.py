"""Stage 4: encode a bound hypothesis + target invariant as Z3 constraints.

Bounded model checking over the chain: state index 0 is "before step 1",
state k is "after step k". Per resource instance r and state k we track
`owner(r)@k : Int` (an actor id), `exists(r)@k : Bool`, and — for single_use
invariants — `uses(r)@k : Int`, how many times the governed effect has
succeeded on r. Transition semantics per step, by Stage 1's TransitionKind:

  create / capture-from-read : exists@k := True, owner@k := acting actor
  delete                     : exists@k := False
  read / update / action     : no owner/exists change
  everything not touched     : framed (unchanged)

Single-use counters (coupon redeem, vote, token consume, withdraw):
  sequential governed use    : atomic check-then-act —
                               ok_k := uses@(k-1) < limit ; uses@k := uses@(k-1) + ok_k
  race group of governed uses: each member j has a *check* event and a *write*
                               event with symbolic times chk_j < wr_j, all
                               events distinct. Member j observes
                               base + #{i != j : ok_i and wr_i < chk_j}, and
                               succeeds iff that is < limit. Z3 therefore
                               searches every interleaving of the concurrent
                               requests — the classic TOCTOU window is the
                               interleaving where all checks precede all writes.

The question posed to Z3: does there exist an execution of this exact chain
in which the invariant is violated — assuming the application does NOT
enforce the check at the governed endpoint (unless the endpoint is in
`enforced_endpoints`, i.e. known-enforced or known-atomic from evidence or
a prior replay)?

  SAT   -> the chain structurally reaches a violating state; the model is a
           concrete witness (which actor, which instance, which step — and for
           races, which interleaving) that Stage 6 replays against the live app.
  UNSAT -> no execution of this chain can violate the invariant, whatever the
           app does; the unsat core says why.

Modeling assumptions (deliberate, kept small):
  * named actors are distinct authenticated principals;
  * a value captured from a read/list made by actor A is an instance owned by A;
  * for role_required invariants, an actor is privileged iff its name contains
    "admin" — the invariant text is prose, so the required role isn't
    machine-readable yet;
  * a single_use limit is per instance (global), not per actor;
  * race-group members are treated in declared order for owner/exists
    semantics — concurrency only matters for the use counter.
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
    uses: dict[str, list[z3.ArithRef]] = field(default_factory=dict)  # single_use only
    use_target: dict[int, str | None] = field(default_factory=dict)  # step -> instance used
    ok: dict[int, z3.BoolRef] = field(default_factory=dict)  # step position -> use succeeded
    events: dict[int, tuple[z3.ArithRef, z3.ArithRef]] = field(default_factory=dict)  # (chk, wr)
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

    if invariant.kind == InvariantKind.SINGLE_USE:
        _encode_single_use(enc, invariant, enforced_endpoints)
    else:
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


def _governed_use_target(enc: Encoding, step: BoundStep) -> str | None:
    """Instance of the invariant's resource this step is a governed use of, if any."""
    if not _governed(step, enc.invariant) or step.target is None:
        return None
    if enc.binding.instances[step.target].resource != enc.invariant.resource:
        return None
    return step.target


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
            r = _governed_use_target(enc, step)
            if r is None:
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


def _encode_single_use(
    enc: Encoding, invariant: SecurityInvariant, enforced_endpoints: frozenset[str]
) -> None:
    n = len(enc.binding.steps)
    limit = invariant.limit
    tracked = [
        r for r, inst in enc.binding.instances.items() if inst.resource == invariant.resource
    ]
    for r in tracked:
        enc.uses[r] = [z3.Int(f"uses:{r}@{k}") for k in range(n + 1)]
    if tracked:
        enc.add(
            "init_uses",
            f"no {invariant.resource} instance has been used before step 1",
            z3.And(*[enc.uses[r][0] == 0 for r in tracked]),
        )

    steps = {s.position: s for s in enc.binding.steps}
    enc.use_target = {s.position: _governed_use_target(enc, s) for s in enc.binding.steps}
    # Race blocks: group id -> instance -> member positions (governed uses only).
    blocks: dict[int, dict[str, list[int]]] = {}
    for g, positions in enc.binding.race_groups.items():
        for k in positions:
            member_target = enc.use_target[k]
            if member_target is not None:
                blocks.setdefault(g, {}).setdefault(member_target, []).append(k)
    in_block = {k for per_r in blocks.values() for ks in per_r.values() for k in ks}

    for k in range(1, n + 1):
        step = steps[k]
        used = enc.use_target[k]
        changed: set[str] = set()

        if used is not None and k not in in_block:
            ok = z3.Bool(f"ok:step{k}")
            enc.ok[k] = ok
            changed.add(used)
            enc.add(
                f"use{k}",
                f"step {k}: {step.actor} {step.endpoint_key} on {used} is atomic - it succeeds "
                f"only if fewer than {limit} prior uses, then counts as one use",
                z3.And(
                    ok == (enc.uses[used][k - 1] < limit),
                    enc.uses[used][k] == enc.uses[used][k - 1] + z3.If(ok, 1, 0),
                ),
            )
        elif used is not None:
            changed.add(used)  # counter for r inside a race block is set by the block below

        frame = [enc.uses[x][k] == enc.uses[x][k - 1] for x in tracked if x not in changed]
        if frame:
            enc.add(
                f"uframe{k}", f"step {k}: use counts of other instances unchanged", z3.And(*frame)
            )

    for g, per_r in blocks.items():
        for r, members in per_r.items():
            _encode_race_block(enc, g, r, members, limit, enforced_endpoints)

    if not tracked or not any(enc.use_target.values()):
        enc.add(
            "violation",
            f"no step in the chain is a governed use of a {invariant.resource!r} instance "
            "- nothing to violate",
            z3.BoolVal(False),
        )
        return

    for r in tracked:
        enc.violation_terms.append((n, enc.uses[r][n] > limit))
    enc.add(
        "violation",
        f"some {invariant.resource} instance ends up used more than {limit} time(s)",
        z3.Or(*[t for _, t in enc.violation_terms]),
    )


def _encode_race_block(
    enc: Encoding,
    group: int,
    r: str,
    members: list[int],
    limit: int,
    enforced_endpoints: frozenset[str],
) -> None:
    first, last = members[0], members[-1]
    base = enc.uses[r][first - 1]
    steps = {s.position: s for s in enc.binding.steps}
    for k in members:
        enc.ok[k] = z3.Bool(f"ok:step{k}")
        enc.events[k] = (z3.Int(f"chk:step{k}"), z3.Int(f"wr:step{k}"))

    all_events = [e for k in members for e in enc.events[k]]
    constraints: list[z3.BoolRef] = [z3.Distinct(*all_events)]
    for k in members:
        chk, wr = enc.events[k]
        constraints += [chk >= 0, wr < len(all_events), chk < wr]
        observed_terms = [
            z3.If(z3.And(enc.ok[j], enc.events[j][1] < chk), 1, 0) for j in members if j != k
        ]
        observed = base + z3.Sum(*observed_terms) if observed_terms else base
        constraints.append(enc.ok[k] == (observed < limit))
    # Intermediate states inside the block keep the base count; the last state
    # carries the total - the block is one concurrent burst.
    for k in members[:-1]:
        constraints.append(enc.uses[r][k] == base)
    constraints.append(
        enc.uses[r][last] == base + z3.Sum(*[z3.If(enc.ok[k], 1, 0) for k in members])
    )
    who = ", ".join(f"step {k} ({steps[k].actor})" for k in members)
    enc.add(
        f"race{group}:{r}",
        f"race group {group}: {who} fire {steps[first].endpoint_key} on {r} concurrently; "
        f"each observes only the writes that landed before its own check",
        z3.And(*constraints),
    )

    for k in members:
        if steps[k].endpoint_key in enforced_endpoints:
            earlier = [j for j in members if j < k]
            if not earlier:
                continue
            enc.add(
                f"enforced{k}",
                f"{steps[k].endpoint_key} is known to be atomic (evidence/replay) - "
                f"step {k} observes every earlier write",
                z3.And(*[enc.events[j][1] < enc.events[k][0] for j in earlier]),
            )
