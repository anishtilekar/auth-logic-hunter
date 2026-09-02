from pathlib import Path

import pytest

from app.pipeline.stage1_state_model.builder import build_application_model
from app.pipeline.stage1_state_model.schema import ApplicationModel

CRAPI_ROOT = Path(__file__).parents[3] / "targets/crapi"


@pytest.fixture(scope="module")
def model() -> ApplicationModel:
    if not (CRAPI_ROOT / "openapi-spec/crapi-openapi-spec.json").is_file():
        pytest.skip("crAPI submodule not checked out (empty dir counts as missing)")
    return build_application_model(CRAPI_ROOT)


def test_order_scan_surfaces_the_known_bola_line(model: ApplicationModel) -> None:
    # workshop/crapi/shop/views.py fetches an order by id_param with no ownership
    # filter at all (Order.objects.get(id=order_id), no .filter(user=...)) — a
    # real, live BOLA bug in crAPI, and exactly the kind of evidence Stage 2
    # needs. This is a regression anchor: if the scanner stops finding it, the
    # heuristic broke.
    evidence = model.resources["order"].ownership_evidence
    assert any("Order.objects.get(id=order_id)" in line for line in evidence)


def test_scan_excludes_vendored_and_test_directories(model: ApplicationModel) -> None:
    for resource in model.resources.values():
        for line in resource.ownership_evidence:
            path_part = line.split(":", 1)[0].lower()
            assert "vendor" not in path_part
            assert "/test" not in path_part.replace("\\", "/")
