from enum import StrEnum

from pydantic import BaseModel


class HTTPMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class TransitionKind(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    ACTION = "action"


class Endpoint(BaseModel):
    path: str
    method: HTTPMethod
    operation_id: str | None = None
    summary: str | None = None
    path_params: list[str] = []
    resource: str | None = None

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


class StateTransition(BaseModel):
    resource: str
    kind: TransitionKind
    endpoint_key: str


class Resource(BaseModel):
    name: str
    id_params: list[str] = []
    endpoint_keys: list[str] = []
    ownership_evidence: list[str] = []
    """file:line snippets from source where an ownership-style check was found
    near this resource's identifier — a heuristic hint for Stage 2, not proof."""


class ApplicationModel(BaseModel):
    title: str
    base_url: str
    resources: dict[str, Resource]
    endpoints: list[Endpoint]
    transitions: list[StateTransition]
