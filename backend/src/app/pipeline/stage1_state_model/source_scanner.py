"""Heuristic source-evidence scan over target source code.

Deliberately a regex pass, not a tree-sitter/Joern AST analysis — scoped
down for Phase 2 to keep the pipeline's first real stage lean. It gathers
two kinds of hint for Stage 2's LLM invariant extraction, both *hints*
rather than proof:

  ownership_evidence  — lines where a resource's id param and a common
                        ownership-check keyword appear near each other.
  race_evidence       — check-then-act shapes: a state flag or counter is
                        tested in a conditional and then written a few
                        lines later, with no synchronization between. This
                        is what a single_use invariant looks like in source,
                        and what makes it violable by concurrent requests.

If either signal turns out too noisy in practice, upgrading to real
AST-based analysis is the next step.
"""

import re
from pathlib import Path

from app.pipeline.stage1_state_model.schema import ApplicationModel, Resource

_SOURCE_EXT = {".py", ".go", ".kt", ".java"}
_EXCLUDED_DIR_PARTS = {"vendor", "node_modules", "test", "tests", ".git", "build", "gradle"}
_EXCLUDED_FILE_STEMS = re.compile(r"^(tests?|.*_test|test_.*)$", re.IGNORECASE)
_OWNERSHIP_KEYWORDS = re.compile(
    r"\b(user_id|userId|current_user|request\.user|getUserId|principal|owner|Authentication|user)\b",
    re.IGNORECASE,
)
_WINDOW = 15
_MAX_HITS_PER_RESOURCE = 20

# Check-then-act: a conditional testing a state field, then a write to that
# same field shortly after. Captures the field name so the write can be matched
# to the check — `if (c.redeemed) ... c.redeemed = true` is the shape, and it's
# exactly a TOCTOU window when the two aren't atomic.
_CHECK_RE = re.compile(
    r"\b(?:if|elif|unless)\b[^\n]*?[\w\]\)]\.(?P<field>\w+)|"
    r"\b(?:if|elif)\s+(?:not\s+)?(?P<bare>\w+)\s*(?:[:)]|==|!=)"
)
_MAX_ACT_DISTANCE = 12
_COUNTER_CALLS = re.compile(r"\b(incrementAndGet|getAndIncrement|\+\+|\+=\s*1)\b")
# Locking/atomicity constructs: their presence near the window means the
# check-then-act is probably guarded, so it isn't worth reporting as a race hint.
_SYNC_RE = re.compile(
    r"\b(synchronized|Lock\b|lock\(\)|compareAndSet|@Transactional|select_for_update|"
    r"SELECT\s+FOR\s+UPDATE|atomic|Mutex|with\s+\w*lock)\b",
    re.IGNORECASE,
)


def _write_pattern(field: str) -> re.Pattern[str]:
    f = re.escape(field)
    return re.compile(rf"\.{f}\s*=(?!=)|\b{f}\s*=(?!=)|\.{f}\b[^\n]*(\+\+|\+=)")


def _candidate_dirs(resource_name: str, model: ApplicationModel, services_root: Path) -> list[Path]:
    """Directories to scan for this resource.

    Prefers the service directory named after the resource's own path prefix
    (crAPI's layout: /workshop/... -> services/workshop). Falls back to the
    whole services tree when no such directory exists — without this fallback
    a target whose service dirs aren't named after its path prefixes silently
    yields zero evidence, which is how the seeded-race target originally got
    no evidence at all despite its source sitting right there.
    """
    for ep in model.endpoints:
        if ep.resource == resource_name:
            prefix = ep.path.strip("/").split("/")[0]
            candidate = services_root / prefix
            if candidate.is_dir():
                return [candidate]
            break
    return [services_root] if services_root.is_dir() else []


def _id_param_pattern(id_params: list[str]) -> re.Pattern[str]:
    # Exact id-param names only (e.g. "order_id", "vehicleId") — a looser
    # stripped-suffix variant ("order", "vehicle") sounds appealing but floods
    # results with unrelated matches on common words (Django's .order_by(),
    # OrderedDict, etc.), so it's deliberately not included here.
    variants = {re.escape(p) for p in id_params}
    return re.compile(r"\b(" + "|".join(variants) + r")\b", re.IGNORECASE)


def _source_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in _SOURCE_EXT or not path.is_file():
                continue
            if _EXCLUDED_DIR_PARTS & {p.lower() for p in path.parts}:
                continue
            if _EXCLUDED_FILE_STEMS.match(path.stem):
                continue
            files.append(path)
    return files


def _scan_file(
    resource: Resource,
    path: Path,
    lines: list[str],
    services_root: Path,
    id_pattern: re.Pattern[str],
) -> tuple[list[str], list[str]]:
    rel = path.relative_to(services_root).as_posix()
    ownership: list[str] = []
    race: list[str] = []

    id_line_numbers = [i for i, line in enumerate(lines) if id_pattern.search(line)]
    for i in id_line_numbers:
        window = lines[max(0, i - _WINDOW) : i + _WINDOW]
        if any(_OWNERSHIP_KEYWORDS.search(line) for line in window):
            ownership.append(f"{rel}:{i + 1}: {lines[i].strip()}")

    # Only look for check-then-act in files that mention this resource's id at
    # all, so evidence stays attributed to the right resource.
    if id_line_numbers:
        for i, line in enumerate(lines):
            m = _CHECK_RE.search(line)
            if m is None:
                continue
            field = m.group("field") or m.group("bare")
            if not field:
                continue
            act_window = lines[i + 1 : i + 1 + _MAX_ACT_DISTANCE]
            guard_window = lines[max(0, i - 3) : i + 1 + _MAX_ACT_DISTANCE]
            if any(_SYNC_RE.search(w) for w in guard_window):
                continue
            writer = _write_pattern(field)
            for j, act in enumerate(act_window):
                if writer.search(act) or (
                    _COUNTER_CALLS.search(act) and field.lower() in act.lower()
                ):
                    race.append(
                        f"{rel}:{i + 1}: checks `{line.strip()}` then "
                        f"line {i + j + 2} writes `{act.strip()}` (no lock in between)"
                    )
                    break
    return ownership, race


def scan_source_evidence(model: ApplicationModel, services_root: Path) -> None:
    for resource in model.resources.values():
        if not resource.id_params:
            continue
        roots = _candidate_dirs(resource.name, model, services_root)
        if not roots:
            continue

        id_pattern = _id_param_pattern(resource.id_params)
        ownership: list[str] = []
        race: list[str] = []

        for path in _source_files(roots):
            if len(ownership) >= _MAX_HITS_PER_RESOURCE and len(race) >= _MAX_HITS_PER_RESOURCE:
                break
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            own_hits, race_hits = _scan_file(resource, path, lines, services_root, id_pattern)
            ownership += own_hits
            race += race_hits

        resource.ownership_evidence = ownership[:_MAX_HITS_PER_RESOURCE]
        resource.race_evidence = race[:_MAX_HITS_PER_RESOURCE]
