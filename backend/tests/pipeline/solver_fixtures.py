"""Shared hand-built application model for the Stage 4/5 tests. Small, but shaped
like crAPI: an owned resource with full CRUD + an action, a resource whose id is
only obtainable from a list, and an admin-only endpoint."""

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

_ENDPOINTS: list[tuple[str, str, TransitionKind]] = [
    ("order", "POST /orders", TransitionKind.CREATE),
    ("order", "GET /orders/{order_id}", TransitionKind.READ),
    ("order", "PUT /orders/{order_id}", TransitionKind.UPDATE),
    ("order", "DELETE /orders/{order_id}", TransitionKind.DELETE),
    ("order", "POST /orders/{order_id}/return", TransitionKind.ACTION),
    ("vehicle", "POST /vehicles", TransitionKind.CREATE),
    ("vehicle", "GET /vehicles", TransitionKind.READ),
    ("vehicle", "GET /vehicles/{vehicle_id}", TransitionKind.READ),
    ("video", "POST /videos", TransitionKind.CREATE),
    ("video", "DELETE /admin/videos/{video_id}", TransitionKind.DELETE),
]


def _build_model() -> ApplicationModel:
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
        title="Fixture App",
        base_url="http://localhost",
        resources=resources,
        endpoints=endpoints,
        transitions=transitions,
    )


MODEL = _build_model()

ORDER_OWNERSHIP = SecurityInvariant(
    resource="order",
    endpoint_keys=[
        "GET /orders/{order_id}",
        "PUT /orders/{order_id}",
        "DELETE /orders/{order_id}",
        "POST /orders/{order_id}/return",
    ],
    kind=InvariantKind.OWNERSHIP,
    statement="Only the user who owns an order may view, update, cancel, or return it",
    rationale="fixture",
    confidence=0.4,
)
VEHICLE_OWNERSHIP = SecurityInvariant(
    resource="vehicle",
    endpoint_keys=["GET /vehicles/{vehicle_id}"],
    kind=InvariantKind.OWNERSHIP,
    statement="Only the owner of a vehicle may view its details",
    rationale="fixture",
    confidence=0.5,
)
VIDEO_ADMIN_ONLY = SecurityInvariant(
    resource="video",
    endpoint_keys=["DELETE /admin/videos/{video_id}"],
    kind=InvariantKind.ROLE_REQUIRED,
    statement="Only administrators may delete videos",
    rationale="fixture",
    confidence=0.7,
)
ORDER_STATE = SecurityInvariant(
    resource="order",
    endpoint_keys=["POST /orders/{order_id}/return"],
    kind=InvariantKind.STATE_PRECONDITION,
    statement="An order may only be returned after it has been delivered",
    rationale="fixture",
    confidence=0.6,
)
INVARIANTS = [ORDER_OWNERSHIP, VEHICLE_OWNERSHIP, VIDEO_ADMIN_ONLY, ORDER_STATE]


def step(
    n: int,
    actor: str,
    endpoint_key: str,
    *,
    captures: str | None = None,
    uses: dict[str, str] | None = None,
) -> RequestStep:
    return RequestStep(
        step=n,
        actor=actor,
        endpoint_key=endpoint_key,
        description=f"{actor} {endpoint_key}",
        captures=captures,
        uses=uses or {},
    )


def chain(
    *steps: RequestStep,
    resource: str = "order",
    target: str = ORDER_OWNERSHIP.statement,
) -> Hypothesis:
    return Hypothesis(
        resource=resource,
        target_invariant_statement=target,
        preconditions=["all actors are registered, authenticated users"],
        steps=list(steps),
        expected_violation="a non-owner succeeds",
        confidence=0.5,
    )


# The canonical two-step BOLA chain: victim creates, attacker reads.
BOLA = chain(
    step(1, "victim", "POST /orders", captures="order_id"),
    step(2, "attacker", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
)
SAME_ACTOR = chain(
    step(1, "victim", "POST /orders", captures="order_id"),
    step(2, "victim", "GET /orders/{order_id}", uses={"order_id": "step1.order_id"}),
)
