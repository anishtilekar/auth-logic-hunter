"""Severity derivation and the shareable HTML report.

Severity is the one number a reader acts on, so the rules are pinned explicitly —
especially the two that carry this project's argument: a replay-confirmed race is
the most severe thing the tool can say, and a chain the app actually *blocked* is
demoted to info rather than reported as a vulnerability.
"""

from app.api.report import render_report
from app.pipeline.severity import Severity, severity_for, sort_key

_SMTLIB = "; violation: some governed access\n(check-sat)"


def _finding(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "hypothesis_index": 0,
        "invariant_statement": "A coupon may be redeemed at most once",
        "invariant_kind": "single_use",
        "verdict": "sat",
        "reason": None,
        "unsat_core": [],
        "witness": None,
        "smtlib": _SMTLIB,
        "solve_time_ms": 12.0,
        "replay": None,
    }
    return base | kw


def _replay(outcome: str) -> dict[str, object]:
    return {
        "outcome": outcome,
        "reason": "2 concurrent uses succeeded against a limit of 1 (steps 2, 3)",
        "base_url": "http://localhost:8090",
        "steps": [
            {
                "step": 2,
                "actor": "attacker",
                "method": "POST",
                "url": "http://localhost:8090/api/coupons/C1/redeem",
                "status": 200,
                "started_offset_ms": 0.288,
                "error": None,
            }
        ],
        "violating_steps": [2, 3],
        "enforced_endpoints": [],
    }


def test_confirmed_race_is_critical_and_confirmed_access_is_high() -> None:
    assert severity_for("sat", "single_use", "confirmed") == Severity.CRITICAL
    assert severity_for("sat", "ownership", "confirmed") == Severity.HIGH
    assert severity_for("sat", "role_required", "confirmed") == Severity.HIGH


def test_a_chain_the_app_blocked_is_info_not_a_vulnerability() -> None:
    # The whole point of Stage 6: replay disagreeing with the proof must
    # de-escalate the finding, never leave it looking exploitable.
    assert severity_for("sat", "single_use", "refuted") == Severity.INFO
    assert severity_for("sat", "ownership", "refuted") == Severity.INFO


def test_proven_but_unreplayed_is_medium() -> None:
    assert severity_for("sat", "ownership", None) == Severity.MEDIUM
    assert severity_for("sat", "single_use", "inconclusive") == Severity.MEDIUM
    assert severity_for("sat", "single_use", "error") == Severity.MEDIUM


def test_non_sat_verdicts_are_info() -> None:
    for verdict in ("unsat", "invalid", "unsupported", "unknown", None):
        assert severity_for(verdict, "ownership", None) == Severity.INFO


def test_missing_kind_still_classifies() -> None:
    # Findings written before invariant_kind existed must not error or vanish.
    assert severity_for("sat", None, "confirmed") == Severity.HIGH
    assert severity_for("sat", None, None) == Severity.MEDIUM


def test_sort_key_orders_most_severe_first_and_unknown_last() -> None:
    order = sorted(["info", "critical", "medium", "nonsense", "high"], key=sort_key)
    assert order == ["critical", "high", "medium", "info", "nonsense"]


def _run(findings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "id": 54,
        "target_name": "seeded-race",
        "status": "completed",
        "created_at": "2026-09-03T10:00:00Z",
        "completed_at": "2026-09-03T10:00:20Z",
        "invariants": [{"resource": "coupon"}],
        "hypotheses": [
            {
                "resource": "coupon",
                "expected_violation": "both redeems succeed",
                "steps": [
                    {
                        "step": 2,
                        "actor": "attacker",
                        "endpoint_key": "POST /api/coupons/{code}/redeem",
                        "description": "redeem",
                        "race_group": 1,
                    }
                ],
            }
        ],
        "findings": findings,
    }


def test_report_is_self_contained_and_shows_the_evidence() -> None:
    html = render_report(_run([_finding(replay=_replay("confirmed"))]))
    assert html.startswith("<!doctype html>")
    # Self-contained: nothing to fetch, so it survives being emailed or archived.
    assert "<script" not in html
    assert "http-equiv" not in html
    assert 'src="' not in html and "@import" not in html
    assert "critical" in html
    assert "POST /api/coupons/{code}/redeem" in html
    assert "race 1" in html
    assert "0.29 ms" in html  # the concurrent release offset survives into the report
    assert "http://localhost:8090/api/coupons/C1/redeem" in html


def test_report_orders_findings_most_severe_first() -> None:
    html = render_report(
        _run(
            [
                _finding(verdict="unsat", reason="refuted"),
                _finding(replay=_replay("confirmed")),
            ]
        )
    )
    assert html.index("critical") < html.index("info")


def test_report_escapes_content_rather_than_emitting_markup() -> None:
    html = render_report(_run([_finding(invariant_statement="<img src=x onerror=alert(1)>")]))
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_report_handles_an_empty_run() -> None:
    html = render_report({"id": 1, "target_name": "crapi", "status": "completed"})
    assert "No findings in this run." in html


def test_interleaving_is_not_printed_twice() -> None:
    # _single_use_story already writes the interleaving into the narrative, so
    # rendering witness.order as well repeated the same line verbatim.
    order = ["check step 2", "check step 3", "write step 2", "write step 3"]
    witness = {
        "actors": {},
        "instances": [],
        "violating_steps": [2, 3],
        "narrative": [f"race group 1 interleaving: {' < '.join(order)}"],
        "order": order,
    }
    html = render_report(_run([_finding(witness=witness)]))
    assert html.count("check step 2 &lt; check step 3") == 1


def test_order_still_shown_when_the_narrative_omits_it() -> None:
    order = ["check step 2", "write step 2"]
    witness = {
        "actors": {},
        "instances": [],
        "violating_steps": [2],
        "narrative": ["coupon step1.code: 2 successful uses against a limit of 1"],
        "order": order,
    }
    html = render_report(_run([_finding(witness=witness)]))
    assert "Interleaving:" in html
