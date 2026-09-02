"""Heuristic ownership-evidence scan over target source code.

Deliberately a regex pass, not a tree-sitter/Joern AST analysis — scoped
down for Phase 2 to keep the pipeline's first real stage lean. It only
scans resources that have a path-param id (video, vehicle, post, order —
the actual BOLA-relevant ones), looking for lines where the id param and a
common ownership-check keyword appear near each other in the same file.
Evidence here is a *hint* for Stage 2's LLM invariant extraction, not proof
of an ownership check existing or being correct — if this signal turns out
too noisy in practice, upgrading to real AST-based analysis is the next step.
"""

import re
from pathlib import Path

from app.pipeline.stage1_state_model.schema import ApplicationModel

_SOURCE_EXT = {".py", ".go", ".kt", ".java"}
_EXCLUDED_DIR_PARTS = {"vendor", "node_modules", "test", "tests", ".git", "build", "gradle"}
_EXCLUDED_FILE_STEMS = re.compile(r"^(tests?|.*_test|test_.*)$", re.IGNORECASE)
_OWNERSHIP_KEYWORDS = re.compile(
    r"\b(user_id|userId|current_user|request\.user|getUserId|principal|owner|Authentication|user)\b",
    re.IGNORECASE,
)
_WINDOW = 15
_MAX_HITS_PER_RESOURCE = 20


def _resource_service(resource_name: str, model: ApplicationModel) -> str | None:
    for ep in model.endpoints:
        if ep.resource == resource_name:
            return ep.path.strip("/").split("/")[0]
    return None


def _id_param_pattern(id_params: list[str]) -> re.Pattern[str]:
    # Exact id-param names only (e.g. "order_id", "vehicleId") — a looser
    # stripped-suffix variant ("order", "vehicle") sounds appealing but floods
    # results with unrelated matches on common words (Django's .order_by(),
    # OrderedDict, etc.), so it's deliberately not included here.
    variants = {re.escape(p) for p in id_params}
    return re.compile(r"\b(" + "|".join(variants) + r")\b", re.IGNORECASE)


def scan_ownership_evidence(model: ApplicationModel, services_root: Path) -> None:
    for resource in model.resources.values():
        if not resource.id_params:
            continue
        service = _resource_service(resource.name, model)
        if service is None:
            continue
        service_dir = services_root / service
        if not service_dir.is_dir():
            continue

        id_pattern = _id_param_pattern(resource.id_params)
        hits: list[str] = []

        for path in service_dir.rglob("*"):
            if len(hits) >= _MAX_HITS_PER_RESOURCE:
                break
            if path.suffix not in _SOURCE_EXT or not path.is_file():
                continue
            if _EXCLUDED_DIR_PARTS & {p.lower() for p in path.parts}:
                continue
            if _EXCLUDED_FILE_STEMS.match(path.stem):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue

            id_line_numbers = [i for i, line in enumerate(lines) if id_pattern.search(line)]
            for i in id_line_numbers:
                window = lines[max(0, i - _WINDOW) : i + _WINDOW]
                if any(_OWNERSHIP_KEYWORDS.search(line) for line in window):
                    rel = path.relative_to(services_root)
                    hits.append(f"{rel}:{i + 1}: {lines[i].strip()}")
                    if len(hits) >= _MAX_HITS_PER_RESOURCE:
                        break

        resource.ownership_evidence = hits
