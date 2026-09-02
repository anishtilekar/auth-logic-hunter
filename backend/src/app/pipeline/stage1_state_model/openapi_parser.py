"""Builds an ApplicationModel from an OpenAPI spec.

Resource/transition inference is a deliberate heuristic, not a full semantic
parse — it groups endpoints by the noun in their path and guesses CRUD vs.
action intent from the HTTP verb and path shape. Stage 2 (LLM invariant
extraction) is where real semantic understanding gets layered on top; this
stage's job is just to produce a clean, consistent structural skeleton.
"""

import json
import re
from pathlib import Path
from typing import Any

from app.pipeline.stage1_state_model.schema import (
    ApplicationModel,
    Endpoint,
    HTTPMethod,
    Resource,
    StateTransition,
    TransitionKind,
)

_SKIP_SEGMENTS = {"api"}
_VERSION_RE = re.compile(r"^v[\d.]+$", re.IGNORECASE)
_IRREGULAR_PLURALS = {"mechanic": "mechanic"}  # extend as real irregulars turn up


def _singularize(word: str) -> str:
    if word in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[word]
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _clean_segments(path: str, service_prefixes: set[str]) -> list[str]:
    segments = [s for s in path.strip("/").split("/") if s]
    out = []
    for i, seg in enumerate(segments):
        if i == 0 and seg in service_prefixes:
            continue
        if seg in _SKIP_SEGMENTS or _VERSION_RE.match(seg):
            continue
        out.append(seg)
    return out


def _is_param(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _infer_resource_and_kind(
    method: HTTPMethod, segments: list[str], known_resources: set[str]
) -> tuple[str, TransitionKind]:
    # Pass 1 (high confidence): resource is the static segment right before a path param.
    for i, seg in enumerate(segments):
        if _is_param(seg) and i > 0 and not _is_param(segments[i - 1]):
            resource = _singularize(segments[i - 1])
            kind = {
                HTTPMethod.GET: TransitionKind.READ,
                HTTPMethod.PUT: TransitionKind.UPDATE,
                HTTPMethod.PATCH: TransitionKind.UPDATE,
                HTTPMethod.DELETE: TransitionKind.DELETE,
                HTTPMethod.POST: TransitionKind.ACTION,
            }[method]
            return resource, kind

    # Pass 2 (no path param): match remaining static segments against the
    # known-resource vocabulary built from pass-1 endpoints across the spec.
    static_segments = [s for s in segments if not _is_param(s)]
    for seg in reversed(static_segments):
        singular = _singularize(seg.replace("-", "_"))
        if singular in known_resources:
            kind = TransitionKind.CREATE if method == HTTPMethod.POST else TransitionKind.READ
            return singular, kind
        for known in known_resources:
            if known in seg.replace("-", "_"):
                return known, TransitionKind.ACTION

    # Fallback: no confident resource match. Still classify by verb — GET/PUT/
    # PATCH/DELETE without a path param are unambiguous regardless of naming;
    # only bare POST stays ACTION, since most of crAPI's noun-less POSTs really
    # are RPC-style actions (apply_coupon, validate-coupon, signup, login...).
    last = _singularize(static_segments[-1].replace("-", "_")) if static_segments else "unknown"
    fallback_kind = {
        HTTPMethod.GET: TransitionKind.READ,
        HTTPMethod.PUT: TransitionKind.UPDATE,
        HTTPMethod.PATCH: TransitionKind.UPDATE,
        HTTPMethod.DELETE: TransitionKind.DELETE,
        HTTPMethod.POST: TransitionKind.ACTION,
    }[method]
    return last, fallback_kind


def build_from_openapi(spec_path: Path) -> ApplicationModel:
    spec: dict[str, Any] = json.loads(spec_path.read_text(encoding="utf-8"))
    servers = spec.get("servers", [])
    base_url = servers[0]["url"] if servers else ""

    service_prefixes = {p.strip("/").split("/")[0] for p in spec["paths"]}

    raw_endpoints: list[tuple[str, HTTPMethod, dict[str, Any]]] = []
    for path, methods in spec["paths"].items():
        for m, op in methods.items():
            if m.upper() in HTTPMethod.__members__:
                raw_endpoints.append((path, HTTPMethod(m.upper()), op))

    # Build the known-resource vocabulary from pass-1 (path-param-adjacent) endpoints first.
    known_resources: set[str] = set()
    for path, _method, _op in raw_endpoints:
        segments = _clean_segments(path, service_prefixes)
        for i, seg in enumerate(segments):
            if _is_param(seg) and i > 0 and not _is_param(segments[i - 1]):
                known_resources.add(_singularize(segments[i - 1]))

    endpoints: list[Endpoint] = []
    transitions: list[StateTransition] = []
    resources: dict[str, Resource] = {}

    for path, method, op in raw_endpoints:
        segments = _clean_segments(path, service_prefixes)
        path_params = re.findall(r"\{([^}]+)\}", path)
        resource_name, kind = _infer_resource_and_kind(method, segments, known_resources)

        endpoint = Endpoint(
            path=path,
            method=method,
            operation_id=op.get("operationId"),
            summary=op.get("summary"),
            path_params=path_params,
            resource=resource_name,
        )
        endpoints.append(endpoint)
        transitions.append(
            StateTransition(resource=resource_name, kind=kind, endpoint_key=endpoint.key)
        )

        res = resources.setdefault(resource_name, Resource(name=resource_name))
        res.endpoint_keys.append(endpoint.key)
        for p in path_params:
            if p not in res.id_params:
                res.id_params.append(p)

    return ApplicationModel(
        title=spec.get("info", {}).get("title", ""),
        base_url=base_url,
        resources=resources,
        endpoints=endpoints,
        transitions=transitions,
    )
