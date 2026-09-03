"""Stage 6: fire a Z3-proven witness at a live target and see what actually happens.

The proof says a chain *can* violate its invariant given the app doesn't enforce
the check. Replay is what decides whether this app actually doesn't. Three
outcomes matter:

  confirmed   - the violating step(s) succeeded against the running app. The
                finding is real, with request/response evidence attached.
  refuted     - the app rejected them (401/403/404, or a race that stayed within
                its limit). The proof's "not enforced" assumption was wrong here;
                the endpoints that did the rejecting come back in
                `enforced_endpoints` so the next proof against this target
                refutes the same chain up front instead of re-proposing it.
  inconclusive- a setup step failed, so the violating step never got a fair try.
                Deliberately not reported as refuted: absence of a successful
                attack that never ran is not evidence of enforcement.

Race groups are fired through an asyncio.Barrier on pre-warmed connections, so
every member is released at the same instant with its TCP handshake and TLS
already done. Plain asyncio.gather would serialize the connection setup and hide
the window. Recorded per step is the wall-clock offset from the release, so the
interleaving that actually occurred is visible rather than assumed.
"""

import asyncio
import json
import time
from typing import Any

import httpx

from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage2_invariants.schema import InvariantKind, SecurityInvariant
from app.pipeline.stage3_hypotheses.schema import Hypothesis, RequestStep
from app.pipeline.stage4_encoder.binding import EncodingError, bind
from app.pipeline.stage6_replay.schema import ReplayOutcome, ReplayResult, StepEvidence
from app.pipeline.stage6_replay.targets import ReplayTarget

_EXCERPT = 400
_DENIED = {401, 403, 404, 409, 422}


class _UnresolvedStep(Exception):
    """A step's path params couldn't be filled from earlier captures.

    Firing it anyway would send a literal "{order_id}" in the URL and get a 404
    back, which reads exactly like enforcement — so a failed capture would
    silently turn a real finding into "refuted". Raised instead, and reported
    as inconclusive.
    """


def _find_value(payload: Any, key: str) -> str | None:
    """Pull a captured value out of a response body by key, at any depth.

    Also tries a few near-miss spellings, because an endpoint that returns
    `{"id": ...}` is routinely captured by an LLM as `order_id`.
    """
    candidates = [key, key.replace("_", ""), key.split("_")[-1], "id"]
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for candidate in candidates:
                for k, v in node.items():
                    if k.lower() == candidate.lower() and isinstance(v, str | int | float):
                        return str(v)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _url(base_url: str, path: str, values: dict[str, str]) -> str:
    for name, value in values.items():
        path = path.replace(f"{{{name}}}", str(value))
    return base_url.rstrip("/") + path


class _Prepared:
    __slots__ = ("step", "method", "url", "headers", "body")

    def __init__(
        self,
        step: RequestStep,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, str] | None,
    ) -> None:
        self.step, self.method, self.url, self.headers, self.body = step, method, url, headers, body


async def _send(
    client: httpx.AsyncClient,
    prepared: _Prepared,
    *,
    barrier: asyncio.Barrier | None = None,
    release_time: float | None = None,
) -> StepEvidence:
    step = prepared.step
    evidence = StepEvidence(
        step=step.step,
        actor=step.actor,
        method=prepared.method,
        url=prepared.url,
        request_body=prepared.body,
        race_group=step.race_group,
    )
    if barrier is not None:
        await barrier.wait()
    started = time.perf_counter()
    if release_time is not None:
        evidence.started_offset_ms = round((started - release_time) * 1000, 3)
    try:
        response = await client.request(
            prepared.method, prepared.url, headers=prepared.headers, json=prepared.body
        )
        evidence.status = response.status_code
        evidence.response_excerpt = response.text[:_EXCERPT]
    except Exception as exc:  # noqa: BLE001 — recorded as evidence, not swallowed
        evidence.error = f"{type(exc).__name__}: {exc}"
    evidence.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return evidence


async def _warm(client: httpx.AsyncClient, url: str) -> None:
    """Open the connection before the burst so the handshake isn't in the window."""
    try:
        await client.request("OPTIONS", url)
    except Exception:  # noqa: BLE001 — warming is best-effort
        pass


async def replay(
    model: ApplicationModel,
    hypothesis: Hypothesis,
    invariant: SecurityInvariant,
    target: ReplayTarget,
    *,
    violating_steps: list[int] | None = None,
) -> ReplayResult:
    try:
        # Validates references/params exactly as the encoder did, so replay never
        # fires a request built from an unresolved id.
        bind(model, hypothesis)
    except EncodingError as exc:
        return ReplayResult(outcome=ReplayOutcome.ERROR, reason=str(exc), base_url=target.base_url)

    endpoints = {ep.key: ep for ep in model.endpoints}
    steps = sorted(hypothesis.steps, key=lambda s: s.step)
    captured: dict[str, str] = {}  # "stepN.name" -> concrete value
    evidence: list[StepEvidence] = []
    targeted = set(violating_steps or [])

    def prepare(step: RequestStep) -> _Prepared:
        ep = endpoints[step.endpoint_key]
        values = {param: captured[ref] for param, ref in step.uses.items() if ref in captured}
        path_values = {p: values[p] for p in ep.path_params if p in values}
        missing = [p for p in ep.path_params if p not in path_values]
        if missing:
            raise _UnresolvedStep(
                f"step {step.step} ({step.actor} {step.endpoint_key}): path param(s) "
                f"{', '.join(missing)} could not be resolved - an earlier step captured nothing"
            )
        body = {k: v for k, v in values.items() if k not in ep.path_params} or None
        if ep.method.value in {"GET", "DELETE"}:
            body = None
        return _Prepared(
            step,
            ep.method.value,
            _url(target.base_url, ep.path, path_values),
            target.auth.headers_for(step.actor),
            body,
        )

    limits = httpx.Limits(max_connections=32, max_keepalive_connections=32)
    async with httpx.AsyncClient(timeout=target.timeout_s, limits=limits) as client:
        i = 0
        while i < len(steps):
            group = steps[i].race_group
            if group is None:
                try:
                    prepared_step = prepare(steps[i])
                except _UnresolvedStep as exc:
                    return ReplayResult(
                        outcome=ReplayOutcome.INCONCLUSIVE,
                        reason=f"{exc}, so the violating step never ran",
                        base_url=target.base_url,
                        steps=evidence,
                    )
                ev = await _send(client, prepared_step)
                _capture(steps[i], ev, captured)
                evidence.append(ev)
                if ev.error or (ev.status is not None and ev.status >= 400):
                    # A *governed* step failing is the app enforcing the rule — a
                    # real verdict for _judge. Only a non-governed setup step
                    # failing means the attack never got a fair try.
                    is_governed = steps[i].step in targeted or steps[i].endpoint_key in (
                        invariant.endpoint_keys or []
                    )
                    if not is_governed:
                        return _inconclusive(evidence, target, steps[i], ev)
                i += 1
                continue

            members = [s for s in steps[i:] if s.race_group == group]
            try:
                prepared = [prepare(s) for s in members]
            except _UnresolvedStep as exc:
                return ReplayResult(
                    outcome=ReplayOutcome.INCONCLUSIVE,
                    reason=f"{exc}, so the violating step never ran",
                    base_url=target.base_url,
                    steps=evidence,
                )
            # One client per member: separate connections, so no member waits on
            # another's socket, and the barrier release is the only ordering.
            clients = [httpx.AsyncClient(timeout=target.timeout_s, limits=limits) for _ in prepared]
            try:
                pairs = list(zip(clients, prepared, strict=True))
                await asyncio.gather(*(_warm(c, p.url) for c, p in pairs))
                barrier = asyncio.Barrier(len(prepared))
                release = time.perf_counter()
                group_evidence = await asyncio.gather(
                    *(_send(c, p, barrier=barrier, release_time=release) for c, p in pairs)
                )
            finally:
                await asyncio.gather(*(c.aclose() for c in clients), return_exceptions=True)
            for step, ev in zip(members, group_evidence, strict=True):
                _capture(step, ev, captured)
            evidence += list(group_evidence)
            i += len(members)

    return _judge(invariant, hypothesis, evidence, targeted, target)


def _capture(step: RequestStep, ev: StepEvidence, captured: dict[str, str]) -> None:
    if not step.captures or ev.status is None or ev.status >= 400:
        return
    try:
        payload = json.loads(ev.response_excerpt)
    except json.JSONDecodeError:
        return
    value = _find_value(payload, step.captures)
    if value is not None:
        captured[f"step{step.step}.{step.captures}"] = value
        ev.captured = {step.captures: value}


def _inconclusive(
    evidence: list[StepEvidence], target: ReplayTarget, step: RequestStep, ev: StepEvidence
) -> ReplayResult:
    detail = ev.error or f"HTTP {ev.status}"
    return ReplayResult(
        outcome=ReplayOutcome.INCONCLUSIVE,
        reason=f"setup step {step.step} ({step.actor} {step.endpoint_key}) failed with {detail}, "
        "so the violating step never ran",
        base_url=target.base_url,
        steps=evidence,
    )


def _judge(
    invariant: SecurityInvariant,
    hypothesis: Hypothesis,
    evidence: list[StepEvidence],
    targeted: set[int],
    target: ReplayTarget,
) -> ReplayResult:
    by_step = {e.step: e for e in evidence}
    endpoint_of = {s.step: s.endpoint_key for s in hypothesis.steps}
    governed = [
        s.step
        for s in hypothesis.steps
        if (s.step in targeted)
        or (not targeted and s.endpoint_key in (invariant.endpoint_keys or []))
    ]

    if invariant.kind == InvariantKind.SINGLE_USE:
        uses = [
            s.step
            for s in hypothesis.steps
            if s.step in by_step and s.endpoint_key in (invariant.endpoint_keys or [])
        ]
        raced = [s.step for s in hypothesis.steps if s.race_group is not None]
        successes = [k for k in uses if (by_step[k].status or 500) < 400]
        shape = "concurrent" if raced else "sequential"
        if len(successes) > invariant.limit:
            return ReplayResult(
                outcome=ReplayOutcome.CONFIRMED,
                reason=f"{len(successes)} {shape} uses succeeded against a limit of "
                f"{invariant.limit} (steps {', '.join(map(str, successes))})",
                base_url=target.base_url,
                steps=evidence,
                violating_steps=successes,
            )
        # Surviving *sequential* repeats says nothing about atomicity under
        # concurrency, so it must not mark the endpoint enforced — doing so would
        # suppress the race proof that this target exists to demonstrate.
        held = f"only {len(successes)} of {len(uses)} {shape} uses succeeded, within the limit "
        return ReplayResult(
            outcome=ReplayOutcome.REFUTED,
            reason=held
            + (
                f"of {invariant.limit} — the endpoint held under the race"
                if raced
                else f"of {invariant.limit} — but sequential repeats say nothing about "
                "whether it is atomic under concurrency"
            ),
            base_url=target.base_url,
            steps=evidence,
            enforced_endpoints=sorted({endpoint_of[k] for k in raced}) if raced else [],
        )

    succeeded = [k for k in governed if (by_step[k].status or 500) < 400]
    if succeeded:
        return ReplayResult(
            outcome=ReplayOutcome.CONFIRMED,
            reason=f"step(s) {', '.join(map(str, succeeded))} succeeded despite the invariant "
            f"forbidding it: {invariant.statement}",
            base_url=target.base_url,
            steps=evidence,
            violating_steps=succeeded,
        )
    denied = [k for k in governed if (by_step[k].status or 0) in _DENIED]
    if denied:
        return ReplayResult(
            outcome=ReplayOutcome.REFUTED,
            reason="the app rejected the violating request(s): "
            + ", ".join(f"step {k} -> HTTP {by_step[k].status}" for k in denied),
            base_url=target.base_url,
            steps=evidence,
            enforced_endpoints=sorted({endpoint_of[k] for k in denied}),
        )
    return ReplayResult(
        outcome=ReplayOutcome.INCONCLUSIVE,
        reason="no governed step produced a clear allow/deny result",
        base_url=target.base_url,
        steps=evidence,
    )
