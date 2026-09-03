"""Structural binding of a Hypothesis onto the Application Model.

Resolves every step to a transition kind and a concrete resource instance
*before* anything touches Z3, so that ill-formed chains (unknown endpoint,
dangling `stepN.x` reference, unbound path param) fail with a precise
EncodingError instead of silently encoding to something vacuous.
"""

import re
from dataclasses import dataclass

from app.pipeline.stage1_state_model.schema import ApplicationModel, TransitionKind
from app.pipeline.stage3_hypotheses.schema import Hypothesis

_REF_RE = re.compile(r"^step(\d+)\.(\w+)$")


class EncodingError(ValueError):
    """The hypothesis cannot be encoded against this application model."""


@dataclass(frozen=True)
class Instance:
    id: str  # "step<N>.<name>" — the same text a later step's `uses` refers to
    resource: str
    created_at: int  # 1-based step position that introduces it


@dataclass(frozen=True)
class BoundStep:
    position: int  # 1-based order in the chain
    actor: str
    endpoint_key: str
    kind: TransitionKind
    resource: str | None
    target: str | None  # instance id this step acts on (from `uses`), if any
    creates: str | None  # instance id this step introduces (from `captures`), if any


@dataclass(frozen=True)
class Binding:
    steps: list[BoundStep]
    instances: dict[str, Instance]
    actors: list[str]  # distinct, in first-appearance order


def _pick_target(bound: dict[str, str], path_params: list[str], id_params: list[str]) -> str | None:
    """Prefer the path param that is the resource's own id, then any path param,
    then any body-level reference — the instance this request is *about*."""
    for p in path_params:
        if p in bound and p in id_params:
            return bound[p]
    for p in path_params:
        if p in bound:
            return bound[p]
    return next(iter(bound.values()), None)


def bind(model: ApplicationModel, hypothesis: Hypothesis) -> Binding:
    endpoints = {ep.key: ep for ep in model.endpoints}
    kinds = {t.endpoint_key: t.kind for t in model.transitions}

    steps_in_order = sorted(hypothesis.steps, key=lambda s: s.step)
    numbers = [s.step for s in steps_in_order]
    if len(set(numbers)) != len(numbers):
        raise EncodingError(f"duplicate step numbers: {numbers}")

    # step number -> (position, capture name -> instance id)
    captured: dict[int, tuple[int, dict[str, str]]] = {}
    instances: dict[str, Instance] = {}
    bound_steps: list[BoundStep] = []
    actors: list[str] = []

    for position, step in enumerate(steps_in_order, start=1):
        ep = endpoints.get(step.endpoint_key)
        if ep is None:
            raise EncodingError(f"step {step.step}: unknown endpoint {step.endpoint_key!r}")
        kind = kinds.get(step.endpoint_key)
        if kind is None:
            raise EncodingError(f"step {step.step}: no transition for {step.endpoint_key!r}")
        if step.actor not in actors:
            actors.append(step.actor)

        bound: dict[str, str] = {}
        for param, ref in step.uses.items():
            m = _REF_RE.match(ref)
            if m is None:
                raise EncodingError(
                    f"step {step.step}: `uses` value {ref!r} for {param!r} is not a "
                    "'stepN.name' reference"
                )
            ref_step, name = int(m.group(1)), m.group(2)
            if ref_step not in captured:
                raise EncodingError(
                    f"step {step.step}: {ref!r} refers to step {ref_step}, which does not "
                    "precede it or captures nothing"
                )
            _, names = captured[ref_step]
            if name not in names:
                raise EncodingError(f"step {step.step}: step {ref_step} does not capture {name!r}")
            bound[param] = names[name]

        for p in ep.path_params:
            if p not in bound:
                raise EncodingError(
                    f"step {step.step}: path param {p!r} of {step.endpoint_key!r} is not "
                    "bound via `uses`"
                )

        resource = ep.resource or hypothesis.resource
        id_params = model.resources[resource].id_params if resource in model.resources else []
        target = _pick_target(bound, ep.path_params, id_params)

        creates: str | None = None
        names_here: dict[str, str] = {}
        if step.captures:
            if kind == TransitionKind.CREATE or target is None:
                # A fresh instance: created outright, or surfaced by a listing/read
                # the actor made on their own data.
                creates = f"step{step.step}.{step.captures}"
                instances[creates] = Instance(creates, resource, position)
                names_here[step.captures] = creates
            else:
                # Capturing a field of the instance acted on: an alias, not a new one.
                names_here[step.captures] = target
        captured[step.step] = (position, names_here)

        bound_steps.append(
            BoundStep(
                position=position,
                actor=step.actor,
                endpoint_key=step.endpoint_key,
                kind=kind,
                resource=resource,
                target=target,
                creates=creates,
            )
        )

    return Binding(steps=bound_steps, instances=instances, actors=actors)
