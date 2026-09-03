"""Stage 1's check-then-act scan — the signal Stage 2 needs to propose a single_use
invariant at all. The seeded target is the regression anchor; synthetic fixtures pin
the fallback and the lock-suppression behaviour."""

import json
from pathlib import Path

import pytest

from app.pipeline.stage1_state_model.builder import build_application_model
from app.pipeline.stage1_state_model.schema import ApplicationModel

SEEDED_ROOT = Path(__file__).parents[3] / "targets/seeded-race"

_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Fixture", "version": "1"},
    "paths": {
        "/api/widgets": {"post": {"operationId": "create"}},
        "/api/widgets/{widget_id}/claim": {
            "post": {
                "operationId": "claim",
                "parameters": [
                    {
                        "name": "widget_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
            }
        },
    },
}


def _target(tmp_path: Path, source: str, service_dir: str = "widget-svc") -> Path:
    root = tmp_path / "target"
    (root / "openapi-spec").mkdir(parents=True)
    (root / "openapi-spec/spec.json").write_text(json.dumps(_SPEC), encoding="utf-8")
    svc = root / "services" / service_dir
    svc.mkdir(parents=True)
    (svc / "Handler.java").write_text(source, encoding="utf-8")
    return root


_RACY = """
public class Handler {
    public void claim(String widget_id) {
        Widget w = store.get(widget_id);
        if (w.claimed) {
            throw new Conflict();
        }
        w.claimed = true;
    }
}
"""

_GUARDED = """
public class Handler {
    public synchronized void claim(String widget_id) {
        Widget w = store.get(widget_id);
        if (w.claimed) {
            throw new Conflict();
        }
        w.claimed = true;
    }
}
"""


@pytest.fixture(scope="module")
def seeded() -> ApplicationModel:
    if not (SEEDED_ROOT / "openapi-spec/seeded-race-openapi.json").is_file():
        pytest.skip("seeded-race target missing")
    return build_application_model(SEEDED_ROOT)


def test_seeded_target_race_evidence_names_the_planted_check_then_act(
    seeded: ApplicationModel,
) -> None:
    # Regression anchor: CouponController checks `redeemed` then writes it with no
    # lock between. If this stops being found, Stage 2 loses the only real signal
    # it has for proposing the single_use invariant this target exists to test.
    evidence = seeded.resources["coupon"].race_evidence
    assert any("c.redeemed = true" in line and "if (c.redeemed)" in line for line in evidence)
    assert all("no lock in between" in line for line in evidence)


def test_evidence_uses_posix_paths(seeded: ApplicationModel) -> None:
    # These strings go straight into an LLM prompt and the dashboard; Windows
    # backslashes there are noise at best and escape hazards at worst.
    for line in seeded.resources["coupon"].ownership_evidence:
        assert "\\" not in line


def test_scan_falls_back_when_no_service_dir_matches_the_path_prefix(tmp_path: Path) -> None:
    # Path prefix is "api", the service dir is "widget-svc" — without the fallback
    # this silently yields zero evidence, which is exactly how the seeded target
    # originally came back empty.
    model = build_application_model(_target(tmp_path, _RACY))
    assert model.resources["widget"].race_evidence


def test_scan_still_prefers_a_prefix_named_service_dir(tmp_path: Path) -> None:
    model = build_application_model(_target(tmp_path, _RACY, service_dir="api"))
    [hit] = model.resources["widget"].race_evidence
    # Paths stay relative to services/ (same convention crAPI's evidence uses),
    # so a prefix-matched dir still appears in the reported path.
    assert hit.startswith("api/Handler.java:")


def test_synchronized_check_then_act_is_not_reported_as_racy(tmp_path: Path) -> None:
    model = build_application_model(_target(tmp_path, _GUARDED))
    assert model.resources["widget"].race_evidence == []
