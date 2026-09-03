"""Fixture model for race-condition tests: a single-use coupon (redeem at most once)
alongside an owned order resource, so ownership + race can be tested together."""

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
    ("coupon", "POST /coupons", TransitionKind.CREATE),
    ("coupon", "GET /coupons/{code}", TransitionKind.READ),
    ("coupon", "POST /coupons/{code}/redeem", TransitionKind.ACTION),
    ("order", "POST /orders", TransitionKind.CREATE),
    ("order", "GET /orders/{order_id}", TransitionKind.READ),
    ("order", "PUT /orders/{order_id}", TransitionKind.UPDATE),
]


def _build() -> ApplicationModel:
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
        title="Race Fixture",
        base_url="http://localhost",
        resources=resources,
        endpoints=endpoints,
        transitions=transitions,
    )


MODEL = _build()

REDEEM = "POST /coupons/{code}/redeem"

COUPON_SINGLE_USE = SecurityInvariant(
    resource="coupon",
    endpoint_keys=[REDEEM],
    kind=InvariantKind.SINGLE_USE,
    limit=1,
    statement="A coupon may be redeemed at most once",
    rationale="fixture",
    confidence=0.5,
)
ORDER_OWNERSHIP = SecurityInvariant(
    resource="order",
    endpoint_keys=["GET /orders/{order_id}", "PUT /orders/{order_id}"],
    kind=InvariantKind.OWNERSHIP,
    statement="Only the owner may read or update an order",
    rationale="fixture",
    confidence=0.4,
)


def step(
    n: int,
    actor: str,
    endpoint_key: str,
    *,
    captures: str | None = None,
    uses: dict[str, str] | None = None,
    race_group: int | None = None,
) -> RequestStep:
    return RequestStep(
        step=n,
        actor=actor,
        endpoint_key=endpoint_key,
        description=f"{actor} {endpoint_key}",
        captures=captures,
        uses=uses or {},
        race_group=race_group,
    )


def chain(*steps: RequestStep, resource: str = "coupon", target: str | None = None) -> Hypothesis:
    return Hypothesis(
        resource=resource,
        target_invariant_statement=target or COUPON_SINGLE_USE.statement,
        preconditions=["actors are authenticated"],
        steps=list(steps),
        expected_violation="the effect succeeds more times than allowed",
        confidence=0.5,
    )


def redeem_chain(*, concurrent: bool, times: int = 2, actor: str = "attacker") -> Hypothesis:
    """Create a coupon, then redeem it `times` times — concurrently or sequentially."""
    steps = [step(1, "victim", "POST /coupons", captures="code")]
    for i in range(times):
        steps.append(
            step(
                2 + i,
                actor,
                REDEEM,
                uses={"code": "step1.code"},
                race_group=1 if concurrent else None,
            )
        )
    return chain(*steps)
