from pathlib import Path


def get_repo_root() -> Path:
    """Locate the monorepo root regardless of cwd (uv run from backend/,
    or a container with a different WORKDIR) by walking up to PROJECT_PLAN.md."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "PROJECT_PLAN.md").is_file():
            return parent
    raise RuntimeError("Could not locate repo root (PROJECT_PLAN.md not found in any parent)")


def resolve_target(target_name: str) -> Path:
    """Resolve a target name (e.g. "crapi") to its vendored directory under
    /targets, rejecting anything that would escape that directory."""
    targets_root = get_repo_root() / "targets"
    candidate = (targets_root / target_name).resolve()
    if targets_root not in candidate.parents:
        raise ValueError(f"Invalid target name: {target_name!r}")
    if not candidate.is_dir():
        raise FileNotFoundError(f"No such target: {target_name!r} (looked in {targets_root})")
    return candidate
