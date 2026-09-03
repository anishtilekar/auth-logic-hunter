from enum import StrEnum

from pydantic import BaseModel


class Verdict(StrEnum):
    SAT = "sat"  # chain provably reaches a violating state — witness attached
    UNSAT = "unsat"  # chain provably cannot violate the invariant — core attached
    INVALID = "invalid"  # hypothesis doesn't bind to the model (bad ref/endpoint)
    UNSUPPORTED = "unsupported"  # invariant kind has no predicate form yet
    UNKNOWN = "unknown"  # solver gave up (timeout)


class InstanceWitness(BaseModel):
    id: str
    resource: str
    created_at_step: int
    owner: str  # actor name


class Witness(BaseModel):
    actors: dict[str, int]
    instances: list[InstanceWitness]
    violating_steps: list[int]
    narrative: list[str]
    order: list[str] = []  # race witnesses: the check/write interleaving Z3 chose


class ProofResult(BaseModel):
    hypothesis_index: int
    invariant_statement: str | None
    verdict: Verdict
    reason: str | None = None
    unsat_core: list[str] = []
    witness: Witness | None = None
    smtlib: str | None = None
    solve_time_ms: float = 0.0
