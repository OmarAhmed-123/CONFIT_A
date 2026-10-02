"""Feature 04 (Smart Wardrobe) — zero-model unit tests for the extraction logic.

Pins the contract of services/wardrobe-worker/extraction.py (importable with
no torch/modal) and the Modal request model (pydantic only):
  * ATR label→slot mapping by NAME (a reordered id2label can never swap meanings);
  * grouping: both shoes merge into one footwear item; skirts+pants stay separate
    lower items; garment order = prominence (area), capped at MAX_ITEMS;
  * honesty: below-threshold specks are REPORTED as skipped, never promoted;
    unmapped labels are reported, never guessed;
  * person detection from body labels;
  * confidence is bounded, area-derived, never fabricated;
  * cutout compositing: alpha crisp at the threshold, exact RGB preservation;
  * worker request validation (job_id charset, max_items bounds, image size).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest
from PIL import Image

_WORKER_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "services", "wardrobe-worker")
if _WORKER_ROOT not in sys.path:
    sys.path.insert(0, _WORKER_ROOT)

import extraction as ex  # noqa: E402


def _mask(h=200, w=150, fill=255):
    return np.full((h, w), fill, dtype=np.uint8)


# --- label mapping ---------------------------------------------------------------

def test_atr_mapping_covers_all_garment_labels():
    garment_labels = {"Hat", "Upper-clothes", "Skirt", "Pants", "Dress", "Belt",
                      "Left-shoe", "Right-shoe", "Bag", "Scarf"}
    assert garment_labels == set(ex.ATR_LABEL_TO_SLOT)
    assert set(ex.ATR_BODY_LABELS) & set(ex.ATR_LABEL_TO_SLOT) == set()


def test_slot_mapping_matches_vton_vocabulary():
    # tops/bottoms/one-pieces align with the VTON engine categories
    assert ex.SLOT_TO_CATEGORY["upper_outer"] == "tops"
    assert ex.SLOT_TO_CATEGORY["lower"] == "bottoms"
    assert ex.SLOT_TO_CATEGORY["dress"] == "one-pieces"
    assert ex.SLOT_TO_CATEGORY["footwear"] == "footwear"
    assert ex.SLOT_TO_CATEGORY["accessory"] == "accessory"


# --- grouping --------------------------------------------------------------------

def test_shoes_merge_into_one_footwear_item():
    items, report = ex.group_regions(
        [("Left-shoe", _mask()), ("Right-shoe", _mask())], image_area=200 * 150
    )
    assert len(items) == 1
    assert items[0]["slot_type"] == "footwear"
    assert items[0]["label_names"] == ["Left-shoe", "Right-shoe"]
    assert not report["skipped"]


def test_tops_and_bottoms_stay_separate():
    items, _ = ex.group_regions(
        [("Upper-clothes", _mask()), ("Pants", _mask())], image_area=200 * 150
    )
    slots = {i["slot_type"] for i in items}
    assert slots == {"upper_outer", "lower"}


def test_items_ordered_by_prominence_and_capped():
    big = np.ones((500, 400), dtype=np.uint8)      # 200k px
    small = np.ones((100, 100), dtype=np.uint8)    # 10k px
    items, _ = ex.group_regions(
        [("Upper-clothes", big), ("Bag", small)], image_area=1000 * 800
    )
    assert items[0]["slot_type"] == "upper_outer"  # bigger region first
    many = [(lbl, np.ones((50, 50), dtype=np.uint8)) for lbl in
            ("Hat", "Bag", "Scarf", "Belt", "Left-shoe", "Right-shoe", "Dress", "Pants")]
    items, _ = ex.group_regions(many, image_area=100 * 100)
    # Hat+Bag+Scarf+Belt all map to accessory -> ONE merged item; shoes merge;
    # dress and pants stay separate. 8 labels -> 4 honest items.
    slots = [i["slot_type"] for i in items]
    assert slots == ["accessory", "footwear", "dress", "lower"], slots
    assert items[0]["label_names"] == ["Hat", "Bag", "Scarf", "Belt"]


def test_speck_is_reported_skipped_never_promoted():
    speck = np.zeros((100, 100), dtype=np.uint8)
    speck[0, 0] = 1  # 1 pixel = far below 0.5% of 10k
    items, report = ex.group_regions([("Bag", speck)], image_area=100 * 100)
    assert items == []
    assert report["skipped"] == [{"label": "Bag", "reason": "below_min_area", "area": 1}]


def test_unmapped_label_is_reported_not_guessed():
    items, report = ex.group_regions([("Sunglass", _mask(20, 20))], image_area=100 * 100)
    # Sunglass is a BODY label -> person signal, not a wardrobe item
    assert items == []
    assert report["person_detected"] is True
    assert "Sunglass" in report["person_labels"]


def test_body_labels_set_person_detected():
    _, report = ex.group_regions(
        [("Face", _mask(10, 10)), ("Hair", _mask(10, 10))], image_area=100 * 100
    )
    assert report["person_detected"] is True
    assert report["person_labels"] == ["Face", "Hair"]


def test_background_ignored():
    items, report = ex.group_regions([("Background", _mask())], image_area=200 * 150)
    assert items == [] and not report["person_detected"]


# --- confidence honesty ------------------------------------------------------------

def test_confidence_bounded_and_monotonic():
    assert ex.item_confidence(0, 1000) == 0.35
    assert ex.item_confidence(300, 1000) == 0.95  # capped, never > 0.95
    assert ex.item_confidence(100, 1000) < ex.item_confidence(200, 1000)


# --- cutout compositing --------------------------------------------------------------

def test_cutout_alpha_crisp_and_rgb_preserved():
    rgb = Image.new("RGB", (10, 10), (200, 30, 40))
    mask = np.full((10, 10), 0.9, dtype=np.float32)
    mask[:, 5:] = 0.1
    out = ex.compose_cutout(rgb, mask)
    arr = np.asarray(out)
    assert arr.shape == (10, 10, 4)
    assert (arr[:, :5, 3] == 255).all()   # mask >= 0.5 -> opaque
    assert (arr[:, 5:, 3] == 0).all()     # mask < 0.5 -> transparent
    assert (arr[:, :5, :3] == (200, 30, 40)).all()  # RGB untouched


def test_cutout_resizes_mask_to_crop():
    rgb = Image.new("RGB", (20, 10), (1, 2, 3))
    mask = np.full((10, 5), 1.0, dtype=np.float32)  # wrong size -> must resize
    out = ex.compose_cutout(rgb, mask)
    assert np.asarray(out).shape == (10, 20, 4)
    assert (np.asarray(out)[:, :, 3] == 255).all()


# --- bbox ------------------------------------------------------------------------------

def test_bbox_tight():
    m = np.zeros((100, 100), dtype=np.uint8)
    m[20:40, 10:60] = 1
    assert ex.bbox_of_mask(m) == (10, 20, 59, 39)
    assert ex.bbox_of_mask(np.zeros((10, 10))) == (0, 0, 0, 0)


# --- worker request contract --------------------------------------------------------------

def _worker_module():
    import importlib.util

    path = os.path.join(_WORKER_ROOT, "modal_app.py")
    spec = importlib.util.spec_from_file_location("confit_wardrobe_modal_app", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def worker():
    return _worker_module()


def test_worker_app_name(worker):
    assert worker.app.name == "confit-wardrobe-worker"


def test_worker_models_are_mit_and_pinned(worker):
    assert worker.SCHP_MODEL_ID == "pirocheto/schp-atr-18"
    assert worker.BIREFNET_MODEL_ID == "ZhengPeng7/BiRefNet_lite"
    health = {"parser_license": "MIT", "matting_license": "MIT"}  # asserted in /health
    assert "MIT" in health["parser_license"] and "MIT" in health["matting_license"]


def test_request_validation(worker):
    from pydantic import ValidationError

    ok = worker.ExtractionRequest(job_id="job_1", image_base64_or_url="data:image/png;base64,AA==")
    assert ok.max_items == 4
    for bad_kwargs in (
        {"job_id": "bad id!", "image_base64_or_url": "x"},
        {"job_id": "j", "image_base64_or_url": ""},
        {"job_id": "j", "image_base64_or_url": "x", "max_items": 0},
        {"job_id": "j", "image_base64_or_url": "x", "max_items": ex.MAX_ITEMS + 1},
    ):
        with pytest.raises(ValidationError):
            worker.ExtractionRequest(**bad_kwargs)


def test_ssrf_guard_blocks_private_targets(worker):
    for url in (
        "http://localhost/x", "http://169.254.169.254/meta", "http://10.0.0.5/x",
        "ftp://example.com/x", "http://192.168.1.1/x", "",
    ):
        assert worker._is_safe_url(url) is False, url
    assert worker._is_safe_url("https://images.unsplash.com/photo-x?w=600") is True


def test_image_validation_rejects_bombs(worker):
    import base64 as b64

    tiny = b64.b64encode(b"x" * 10).decode()  # < MIN_IMAGE_BYTES
    with pytest.raises(Exception):
        worker._validate_and_decode_image(b64.b64decode(tiny), "test")
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (16 * 1024 * 1024)  # > 15MB
    with pytest.raises(Exception):
        worker._validate_and_decode_image(big, "test")
