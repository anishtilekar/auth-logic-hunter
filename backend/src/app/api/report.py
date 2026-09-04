"""Self-contained HTML report for a run.

One file, no external assets, no JS — so it can be emailed, committed as a build
artifact, or printed to PDF from the browser without anything breaking. Rendered
server-side rather than client-side precisely so the CLI and the GitHub Action
(Phase 10) can emit the identical artifact without a browser.
"""

from html import escape
from typing import Any

from app.pipeline.severity import Severity, severity_for, sort_key

_SEVERITY_COLOR = {
    Severity.CRITICAL.value: "#b3261e",
    Severity.HIGH.value: "#c05621",
    Severity.MEDIUM.value: "#8a6d1f",
    Severity.LOW.value: "#4a5568",
    Severity.INFO.value: "#4a5568",
}

_CSS = """
*{box-sizing:border-box}
body{font:14px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
 color:#1a1a1a;background:#fff;margin:0;padding:32px}
main{max-width:900px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:28px 0 10px;padding-bottom:6px;border-bottom:1px solid #e2e2e2}
.sub{color:#666;margin:0 0 20px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 8px;padding:0;list-style:none}
.stats li{border:1px solid #e2e2e2;border-radius:6px;padding:8px 12px;min-width:104px}
.stats b{display:block;font-size:19px}
.stats span{color:#666;font-size:12px}
.finding{border:1px solid #e2e2e2;border-radius:6px;padding:14px;margin-bottom:12px;
 page-break-inside:avoid}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:11px;
 font-weight:600;color:#fff;text-transform:uppercase;letter-spacing:.03em}
.tag{display:inline-block;border:1px solid #d8d8d8;border-radius:4px;padding:0 6px;
 font-size:11px;color:#555;margin-left:6px}
.muted{color:#666}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
ol.steps{margin:8px 0;padding-left:20px}
ol.steps li{margin:2px 0}
pre{background:#f6f6f6;border-radius:5px;padding:10px;overflow-x:auto;font-size:11px;
 white-space:pre-wrap;word-break:break-word}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ececec}
th{color:#666;font-weight:600;font-size:12px}
footer{margin-top:32px;color:#888;font-size:12px}
@media print{body{padding:0}.finding{border-color:#ccc}}
"""


def _severity_of(finding: dict[str, Any]) -> str:
    replay = finding.get("replay") or {}
    return severity_for(
        finding.get("verdict"), finding.get("invariant_kind"), replay.get("outcome")
    ).value


def _steps_html(hypothesis: dict[str, Any]) -> str:
    rows = []
    for step in hypothesis.get("steps", []):
        race = step.get("race_group")
        tag = f'<span class="tag">race {race}</span>' if race is not None else ""
        rows.append(
            f"<li><b>{escape(str(step.get('actor', '')))}</b>{tag} "
            f'<span class="mono">{escape(str(step.get("endpoint_key", "")))}</span><br>'
            f'<span class="muted">{escape(str(step.get("description", "")))}</span></li>'
        )
    return f'<ol class="steps">{"".join(rows)}</ol>' if rows else ""


def _replay_html(replay: dict[str, Any]) -> str:
    rows = []
    for step in replay.get("steps", []):
        offset = step.get("started_offset_ms")
        at = f" (+{offset:.2f} ms)" if isinstance(offset, int | float) else ""
        status = step.get("error") or step.get("status")
        rows.append(
            f"<tr><td>{escape(str(step.get('step', '')))}</td>"
            f'<td class="mono">{escape(str(step.get("method", "")))} '
            f"{escape(str(step.get('url', '')))}</td>"
            f"<td>{escape(str(status))}{at}</td></tr>"
        )
    table = (
        f"<table><tr><th>Step</th><th>Request</th><th>Response</th></tr>{''.join(rows)}</table>"
        if rows
        else ""
    )
    return (
        f"<p><b>Replay: {escape(str(replay.get('outcome', '')))}</b> "
        f'against <span class="mono">{escape(str(replay.get("base_url", "")))}</span><br>'
        f'<span class="muted">{escape(str(replay.get("reason", "")))}</span></p>{table}'
    )


def _finding_html(finding: dict[str, Any], hypothesis: dict[str, Any] | None) -> str:
    severity = _severity_of(finding)
    colour = _SEVERITY_COLOR.get(severity, "#4a5568")
    resource = (hypothesis or {}).get("resource", "")
    parts = [
        '<div class="finding">',
        f'<span class="pill" style="background:{colour}">{escape(severity)}</span> ',
        f"<b>{escape(str(resource))}</b>",
        f'<span class="tag">{escape(str(finding.get("verdict", "")))}</span>',
    ]
    kind = finding.get("invariant_kind")
    if kind:
        parts.append(f'<span class="tag">{escape(str(kind))}</span>')
    statement = finding.get("invariant_statement")
    if statement:
        parts.append(f'<p class="muted">Invariant: {escape(str(statement))}</p>')
    if hypothesis:
        parts.append(_steps_html(hypothesis))
        violation = hypothesis.get("expected_violation")
        if violation:
            parts.append(f"<p>{escape(str(violation))}</p>")

    witness = finding.get("witness") or {}
    narrative = [str(line) for line in witness.get("narrative", [])]
    for line in narrative:
        parts.append(f'<p class="mono">{escape(line)}</p>')
    # The narrative already spells out a race's interleaving, so only fall back to
    # the raw event order when it doesn't.
    if witness.get("order") and not any("interleaving" in line.lower() for line in narrative):
        order = " &lt; ".join(escape(str(o)) for o in witness["order"])
        parts.append(f'<p class="mono">Interleaving: {order}</p>')
    if finding.get("reason"):
        parts.append(f'<p class="muted">{escape(str(finding["reason"]))}</p>')
    if finding.get("replay"):
        parts.append(_replay_html(finding["replay"]))
    if finding.get("smtlib"):
        parts.append(
            "<details><summary class='muted'>SMT-LIB proof</summary>"
            f"<pre>{escape(str(finding['smtlib']))}</pre></details>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_report(run: dict[str, Any]) -> str:
    findings: list[dict[str, Any]] = list(run.get("findings") or [])
    hypotheses: list[dict[str, Any]] = list(run.get("hypotheses") or [])
    counts: dict[str, int] = {}
    for finding in findings:
        severity = _severity_of(finding)
        counts[severity] = counts.get(severity, 0) + 1

    ordered = sorted(
        findings, key=lambda f: (sort_key(_severity_of(f)), f.get("hypothesis_index", 0))
    )
    body = [
        _finding_html(
            finding,
            hypotheses[finding["hypothesis_index"]]
            if isinstance(finding.get("hypothesis_index"), int)
            and finding["hypothesis_index"] < len(hypotheses)
            else None,
        )
        for finding in ordered
    ]

    stats = [
        ("Invariants", len(run.get("invariants") or [])),
        ("Hypotheses", len(hypotheses)),
        ("Findings", len(findings)),
    ] + [(severity.title(), counts[severity]) for severity in sorted(counts, key=sort_key)]
    stats_html = "".join(
        f"<li><b>{value}</b><span>{escape(label)}</span></li>" for label, value in stats
    )

    target = escape(str(run.get("target_name", "")))
    completed = escape(str(run.get("completed_at") or run.get("created_at") or ""))
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Auth-Logic Hunter — run {run.get('id')} ({target})</title>"
        f"<style>{_CSS}</style></head><body><main>"
        f"<h1>Auth-Logic Hunter — run {run.get('id')}</h1>"
        f"<p class='sub'>Target <b>{target}</b> · status "
        f"{escape(str(run.get('status', '')))} · {completed}</p>"
        f"<ul class='stats'>{stats_html}</ul>"
        "<h2>Findings</h2>"
        + ("".join(body) if body else "<p class='muted'>No findings in this run.</p>")
        + "<footer>Every finding above was decided by Z3 against the application model. "
        "<b>Confirmed</b> findings were additionally replayed against the running "
        "application, with the requests and responses shown. Findings marked "
        "<b>info</b> were checked and did not hold — the tool verified them rather "
        "than guessing.</footer>"
        "</main></body></html>"
    )
