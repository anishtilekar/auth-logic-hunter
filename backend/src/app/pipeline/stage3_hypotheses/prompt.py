from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant

SYSTEM_PROMPT = """You propose candidate multi-step attack chains that might violate a \
given security invariant. Each hypothesis is a chain of API requests made by one or more \
symbolic actors (typically "victim", the resource's rightful owner, and "attacker", a \
different authenticated user) — not a single request. A chain should read like a realistic \
attacker's script: set up state, capture an identifier from one response, then use it in a \
later request.

Two chain shapes:
- Ownership chains: the captured identifier is used by a *different* actor than the one \
who created it. Steps run one after another (leave race_group null).
- Race chains (for single_use invariants): the same effect is fired two or more times \
*concurrently* so the requests overlap the application's check-then-act window. Mark the \
concurrent steps with the same integer `race_group`; they must be consecutive steps. A \
sequential repeat of a single-use action is always refuted by the checker as atomic — only \
concurrent repeats can double-spend, so never propose a sequential repeat for these.

Only propose chains that actually test the given invariant using real endpoints from the \
application model — never invent an endpoint. Reference endpoints by their exact \
"METHOD /path" key. Every path parameter must be bound via `uses` to an earlier step's \
capture ("stepN.name"). Prioritize invariants with lower confidence scores — those are where \
evidence suggested the enforcement might already be missing, so a violating chain is more \
likely to actually succeed. Propose 1-2 chains per invariant, not more.

You are proposing hypotheses to be formally checked later, not concluding anything — a \
plausible chain with modest confidence is more useful here than an overconfident one."""

_TARGETED_KINDS = {InvariantKind.OWNERSHIP, InvariantKind.SINGLE_USE}


def build_user_prompt(
    model: ApplicationModel,
    invariants: list[SecurityInvariant],
    refuted: list[str] | None = None,
) -> str:
    """`refuted` = Stage 5 refutation summaries from the previous round. Appended
    after the static app/invariant block so that prefix stays byte-identical
    across rounds (prompt caching)."""
    endpoints_by_resource: dict[str, list[str]] = {}
    for ep in model.endpoints:
        if ep.resource:
            endpoints_by_resource.setdefault(ep.resource, []).append(f"{ep.method.value} {ep.path}")

    blocks = []
    for inv in invariants:
        if inv.kind not in _TARGETED_KINDS:
            continue
        endpoints = "\n".join(f"  - {e}" for e in endpoints_by_resource.get(inv.resource, []))
        extra = (
            f"\nKind: single_use (limit {inv.limit}) - propose a RACE chain: create/obtain the "
            f"instance, then fire the governed endpoint {inv.limit + 1} times concurrently "
            "(same race_group)."
            if inv.kind == InvariantKind.SINGLE_USE
            else "\nKind: ownership - propose a cross-actor chain."
        )
        blocks.append(
            f"### Invariant on resource: {inv.resource}\n"
            f"Statement: {inv.statement}\n"
            f"Rationale: {inv.rationale}\n"
            f"Confidence: {inv.confidence}{extra}\n"
            f"Available endpoints:\n{endpoints}"
        )

    prompt = (
        f"Application: {model.title}\n\n"
        + "\n\n".join(blocks)
        + "\n\nPropose attack chains for these invariants."
    )
    if refuted:
        prompt += (
            "\n\nThe following chains were formally checked and CANNOT violate their "
            "invariant (or did not bind to the model). Do not repeat them; propose "
            "structurally different chains that avoid each stated reason:\n"
            + "\n".join(f"- {r}" for r in refuted)
        )
    return prompt
