"""Severity for a finding, derived rather than guessed.

This project's whole claim is that a finding is proven, so severity follows the
strength of the evidence, not a hunch about the endpoint:

  critical  a confirmed single_use violation — the app really did let one
            coupon/token/balance be consumed twice. Direct, repeatable
            business-logic loss.
  high      a confirmed ownership or role violation — one user really did reach
            another user's object, or an unprivileged actor a privileged action.
  medium    proven satisfiable by Z3 but not replayed, or replayed without a
            clear answer. The chain is logically sound; nobody has watched the
            live app allow it yet.
  info      Z3 refuted it, or replay showed the app enforcing the rule. Kept
            visible on purpose: "we checked this and it holds" is a result, and
            it's what separates this tool from one that only reports guesses.

Deliberately tolerant of missing fields so findings written by earlier versions
still classify sensibly instead of erroring.
"""

from enum import StrEnum

from app.pipeline.stage2_invariants.schema import InvariantKind
from app.pipeline.stage5_solver.schema import Verdict
from app.pipeline.stage6_replay.schema import ReplayOutcome

_ORDER = ["critical", "high", "medium", "low", "info"]


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


def severity_for(
    verdict: str | None,
    invariant_kind: str | None = None,
    replay_outcome: str | None = None,
) -> Severity:
    if verdict != Verdict.SAT.value:
        return Severity.INFO

    if replay_outcome == ReplayOutcome.CONFIRMED.value:
        return (
            Severity.CRITICAL if invariant_kind == InvariantKind.SINGLE_USE.value else Severity.HIGH
        )
    if replay_outcome == ReplayOutcome.REFUTED.value:
        return Severity.INFO
    # sat with no replay, or an inconclusive/errored replay: the proof stands,
    # the empirical confirmation doesn't.
    return Severity.MEDIUM


def sort_key(severity: str) -> int:
    """Most severe first, unknown values last."""
    return _ORDER.index(severity) if severity in _ORDER else len(_ORDER)
