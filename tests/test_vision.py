# tests/test_vision.py
# Smoke tests. Run: python -m pytest -q
import os
import numpy as np
import cv2 as cv

from app import vision, agent, store


def _make_pair(tmp, bright_change=True):
    rng = np.random.default_rng(7)
    a = rng.integers(60, 150, (256, 256, 3), dtype=np.uint8)
    for _ in range(40):
        x, y = rng.integers(0, 240, 2)
        cv.rectangle(a, (x, y), (x + 12, y + 12),
                     tuple(int(c) for c in rng.integers(40, 200, 3)), -1)
    b = a.copy()
    colour = (210, 210, 215) if bright_change else (40, 120, 40)  # bare vs veg
    cv.rectangle(b, (150, 150), (205, 205), colour, -1)
    pa, pb = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
    cv.imwrite(pa, a); cv.imwrite(pb, b)
    return pa, pb


def test_opencv5_apis_exist():
    assert cv.__version__.startswith("5.")
    assert hasattr(cv, "USAC_MAGSAC")
    assert hasattr(cv, "findTransformECC")
    assert hasattr(cv, "connectedComponentsWithStats")


def test_cloud_gate(tmp_path):
    pa, _ = _make_pair(str(tmp_path))
    assert 0.0 <= vision.cloud_gate(pa, str(tmp_path))["cloud_ratio"] <= 1.0


def test_coregister_reports_sanity(tmp_path):
    pa, pb = _make_pair(str(tmp_path))
    r = vision.coregister(pa, pb, str(tmp_path))
    assert r["inliers"] > 0
    assert "corner_disp_frac" in r


def test_coarse_then_native(tmp_path):
    pa, pb = _make_pair(str(tmp_path))
    coarse = vision.detect_change(pa, pb, str(tmp_path), scale=0.5)
    assert coarse["num_blobs"] >= 1
    roi = vision.inspect_roi_native(pa, pb, coarse["blobs"][0], str(tmp_path))
    assert "roi_change_score" in roi


def test_disturbed_surface_higher_for_bare(tmp_path):
    bare = np.full((40, 40, 3), (210, 210, 215), np.uint8)
    veg = np.full((40, 40, 3), (40, 120, 40), np.uint8)
    assert vision.disturbed_surface_score(bare) > vision.disturbed_surface_score(veg)


def test_agent_loop_runs(tmp_path):
    pa, pb = _make_pair(str(tmp_path))
    out = agent.inspect(pa, pb, out_dir=str(tmp_path))
    assert out["verdict"]["status"] in {
        "NO_SIGNIFICANT_CHANGE", "PENDING_REVIEW", "NEEDS_REVIEW"}
    assert len(out["trace"]) >= 3


def test_state_transition_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_OUT", str(tmp_path))
    rec = {"id": "t1", "status": "PENDING_REVIEW"}
    store.put_alert(rec)
    assert store.set_status("t1", "CONFIRMED")["ok"] is True
    # cannot approve an already-confirmed alert
    assert store.set_status("t1", "CONFIRMED")["ok"] is False
