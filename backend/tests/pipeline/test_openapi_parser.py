from pathlib import Path

import pytest

from app.pipeline.stage1_state_model.openapi_parser import build_from_openapi
from app.pipeline.stage1_state_model.schema import ApplicationModel, HTTPMethod, TransitionKind

CRAPI_SPEC = Path(__file__).parents[3] / "targets/crapi/openapi-spec/crapi-openapi-spec.json"


@pytest.fixture(scope="module")
def model() -> ApplicationModel:
    if not CRAPI_SPEC.is_file():
        pytest.skip("crAPI submodule not checked out (empty dir counts as missing)")
    return build_from_openapi(CRAPI_SPEC)


def test_finds_the_four_bola_relevant_resources(model: ApplicationModel) -> None:
    # These are crAPI's known per-instance resources — the ones with a path-param
    # id and therefore the actual BOLA/IDOR targets this project cares about.
    assert model.resources["video"].id_params == ["video_id"]
    assert model.resources["vehicle"].id_params == ["vehicleId"]
    assert model.resources["post"].id_params == ["postId"]
    assert model.resources["order"].id_params == ["order_id"]


def test_video_endpoints_cover_full_crud(model: ApplicationModel) -> None:
    kinds = {
        t.kind
        for t in model.transitions
        if t.resource == "video" and "{video_id}" in t.endpoint_key
    }
    assert kinds == {TransitionKind.READ, TransitionKind.UPDATE, TransitionKind.DELETE}


def test_get_endpoints_without_resource_match_are_read_not_action(model: ApplicationModel) -> None:
    # Regression test: the fallback path used to tag every unmatched endpoint
    # ACTION regardless of verb, which misclassified plain GETs like /products.
    products_get = next(
        t
        for t in model.transitions
        if t.endpoint_key == "GET /workshop/api/shop/products"
    )
    assert products_get.kind == TransitionKind.READ


def test_every_endpoint_key_is_well_formed(model: ApplicationModel) -> None:
    for ep in model.endpoints:
        assert ep.key == f"{ep.method} {ep.path}"
        assert ep.method in HTTPMethod
