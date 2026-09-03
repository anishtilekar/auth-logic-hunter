from app.pipeline.stage1_state_model.schema import ApplicationModel

SYSTEM_PROMPT = """You infer authorization and business-logic invariants for a web API from its \
structure and static-analysis evidence. You are given, for each resource that has a \
per-instance identifier (a path parameter — the kind of resource where one user's object \
could be accessed via another user's request, i.e. a BOLA/IDOR target), its endpoints and \
any ownership-check evidence found in the source code.

Invariant kinds:
- ownership: only the user who owns X may read/modify/delete it.
- role_required: only a privileged role (e.g. admin) may perform the action.
- single_use: an effect on an instance may succeed at most `limit` times in total — \
redeeming a coupon, casting a vote, consuming a one-time token, withdrawing a balance. \
Set `limit` (default 1). Sequential repeats are harmless; concurrent requests racing the \
check are how these get violated.
- state_precondition: an action is only valid in a given state (prose only for now).

Only emit an invariant when the endpoint structure or evidence actually supports it; do not \
invent rules with no basis in what you were given. If evidence for a resource shows no \
ownership check at all (e.g. a lookup by id with no comparison against the requester), \
still state the invariant the application clearly *should* enforce, but reflect the missing \
enforcement in a lower confidence score and note it in the rationale — that gap is exactly \
what this system exists to find, not a reason to skip the resource.

Keep statements precise and short. Keep rationale to one sentence."""


def build_user_prompt(model: ApplicationModel) -> str:
    transitions_by_resource: dict[str, list[str]] = {}
    for t in model.transitions:
        transitions_by_resource.setdefault(t.resource, []).append(
            f"{t.kind.value}: {t.endpoint_key}"
        )

    blocks = []
    for resource in model.resources.values():
        if not resource.id_params:
            continue
        endpoints = "\n".join(f"  - {e}" for e in transitions_by_resource.get(resource.name, []))
        evidence = (
            "\n".join(f"  - {line}" for line in resource.ownership_evidence)
            if resource.ownership_evidence
            else "  (none found)"
        )
        blocks.append(
            f"### Resource: {resource.name} (id params: {', '.join(resource.id_params)})\n"
            f"Endpoints:\n{endpoints}\n"
            f"Ownership-check evidence from source:\n{evidence}"
        )

    return (
        f"Application: {model.title}\n\n"
        + "\n\n".join(blocks)
        + "\n\nInfer the security invariants for these resources."
    )
