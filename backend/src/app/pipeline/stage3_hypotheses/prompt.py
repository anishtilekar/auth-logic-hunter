from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant

SYSTEM_PROMPT = """You propose candidate multi-step attack chains that might violate a \
given security invariant. Each hypothesis is a *sequential* chain of API requests made by \
one or more symbolic actors (typically "victim", the resource's rightful owner, and \
"attacker", a different authenticated user) — not a single request. A chain should read \
like a realistic attacker's script: set up state, capture an identifier from one response, \
then use it in a later request made as a *different* actor than the one who created it.

Only propose chains that actually test the given invariant using real endpoints from the \
application model — never invent an endpoint. Reference endpoints by their exact \
"METHOD /path" key. Prioritize invariants with lower confidence scores — those are where \
evidence suggested the enforcement might already be missing, so a violating chain is more \
likely to actually succeed. Propose 1-2 chains per invariant, not more.

You are proposing hypotheses to be formally checked later, not concluding anything — a \
plausible chain with modest confidence is more useful here than an overconfident one."""


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
        if inv.kind != InvariantKind.OWNERSHIP:
            continue
        endpoints = "\n".join(f"  - {e}" for e in endpoints_by_resource.get(inv.resource, []))
        blocks.append(
            f"### Invariant on resource: {inv.resource}\n"
            f"Statement: {inv.statement}\n"
            f"Rationale: {inv.rationale}\n"
            f"Confidence: {inv.confidence}\n"
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
