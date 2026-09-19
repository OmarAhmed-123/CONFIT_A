"""Region + occlusion tests (Phase 0.5 §28): malformed, missing, occluded."""
from __future__ import annotations

from PIL import Image

from vton_metrics import occlusion, regions
from vton_metrics.imaging import load_image


def test_missing_pose_returns_no_pose(blank_img):
    img = load_image(blank_img)
    r, status = regions.regions_from_pose(img, "upper_inner")
    assert status == "NO_POSE"
    assert r == {}


def test_face_missing_returns_no_face(blank_img):
    img = load_image(blank_img)
    r, status = regions.face_region(img)
    assert status == "NO_FACE"


def test_occlusion_classify():
    assert occlusion.classify("OK", True, False) == "FULLY_VISIBLE"
    assert occlusion.classify("OK", False, False) == "PARTIALLY_VISIBLE"
    assert occlusion.classify("OK", True, True) == "OCCLUDED_VERIFIED"
    assert occlusion.classify("NO_POSE", None, False) == "UNDETERMINED"


def test_outfit_occlusion_map_inner_outer():
    m = occlusion.outfit_occlusion_map(["upper_inner", "upper_outer"])
    assert m["upper_inner"] is True      # inner covered by outer
    assert m["upper_outer"] is False


def test_outfit_occlusion_map_top_bottom_no_occlusion():
    m = occlusion.outfit_occlusion_map(["upper_inner", "lower"])
    assert m["upper_inner"] is False
    assert m["lower"] is False


def test_outfit_occlusion_map_dress_covers():
    m = occlusion.outfit_occlusion_map(["upper_inner", "dress"])
    assert m["upper_inner"] is True


def test_region_in_image():
    assert occlusion.region_in_image((10, 10, 100, 100), 200, 200) is True
    assert occlusion.region_in_image((150, 150, 260, 260), 200, 200) is False


def test_procrustes_aligns_similarity_transform():
    import numpy as np
    from vton_metrics.pose_metrics import procrustes
    rng = np.random.default_rng(0)
    ref = rng.normal(size=(33, 2))
    ang, s = 0.4, 1.3
    Rc = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    src = (ref - ref.mean(0)) @ Rc.T * s + ref.mean(0) + np.array([2.0, -1.0])
    al = procrustes(src, ref)
    assert np.linalg.norm(al - ref, axis=1).mean() < 1e-8
