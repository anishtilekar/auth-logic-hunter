from pathlib import Path

from app.pipeline.stage1_state_model.openapi_parser import build_from_openapi
from app.pipeline.stage1_state_model.schema import ApplicationModel
from app.pipeline.stage1_state_model.source_scanner import scan_source_evidence


def build_application_model(target_dir: Path) -> ApplicationModel:
    """target_dir is a vendored target app root (e.g. targets/crapi) containing
    an openapi-spec/ dir and a services/ source tree — crAPI's own layout."""
    spec_candidates = list((target_dir / "openapi-spec").glob("*.json"))
    if not spec_candidates:
        raise FileNotFoundError(f"No OpenAPI spec found under {target_dir / 'openapi-spec'}")

    model = build_from_openapi(spec_candidates[0])

    services_dir = target_dir / "services"
    if services_dir.is_dir():
        scan_source_evidence(model, services_dir)

    return model
