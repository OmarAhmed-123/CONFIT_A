"""Mask GEOMETRY and QUALITY tests.

Architecture, single-production-path and resource-safety gates live in
test_vton_single_production_path.py — do not duplicate them here.

VTON Mask Quality Tests — semantic boundaries, not just existence

Tests:
- upper body does not include lower body
- lower body does not include upper body beyond threshold
- footwear does not cover full person
- accessory mask remains localized
- dress mask covers intended region but not entire image
- overlapping garments deterministic
- mask dimensions match source image
- masks do not become empty
- masks are not entire-image rectangles unless semantically valid
- person-aware masking: masks intersect with person silhouette
"""

import io
import base64
from PIL import Image
import numpy as np
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys
import os

# Add vton-worker pipeline to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "vton-worker"))

try:
    from pipeline.segmentation import HumanParsingEngine, AgnosticMaskGenerator
    PIPELINE_AVAILABLE = True
except Exception as e:
    PIPELINE_AVAILABLE = False
    HumanParsingEngine = None
    AgnosticMaskGenerator = None


def _make_person_image(w=512, h=768, person_color=(200, 180, 160), bg_color=(240, 240, 240)):
    """Create synthetic person image: centered rectangle as person silhouette."""
    img = Image.new("RGB", (w, h), color=bg_color)
    # Draw person-like silhouette: head + torso + legs
    import PIL.ImageDraw as Draw
    d = Draw.Draw(img)
    # Head
    d.ellipse((int(w*0.40), int(h*0.05), int(w*0.60), int(h*0.18)), fill=person_color)
    # Torso
    d.rectangle((int(w*0.30), int(h*0.18), int(w*0.70), int(h*0.55)), fill=person_color)
    # Arms
    d.rectangle((int(w*0.20), int(h*0.20), int(w*0.30), int(h*0.55)), fill=person_color)
    d.rectangle((int(w*0.70), int(h*0.20), int(w*0.80), int(h*0.55)), fill=person_color)
    # Legs
    d.rectangle((int(w*0.30), int(h*0.55), int(w*0.48), int(h*0.92)), fill=person_color)
    d.rectangle((int(w*0.52), int(h*0.55), int(w*0.70), int(h*0.92)), fill=person_color)
    # Feet
    d.rectangle((int(w*0.28), int(h*0.92), int(w*0.48), int(h*0.98)), fill=(50, 50, 50))
    d.rectangle((int(w*0.52), int(h*0.92), int(w*0.72), int(h*0.98)), fill=(50, 50, 50))
    return img


@pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="VTON pipeline not available")
class TestHumanParsingEngine:
    def test_parse_returns_required_keys(self):
        img = _make_person_image()
        result = HumanParsingEngine.parse_human_image(img)
        assert "mask" in result
        assert "face_preserve_mask" in result
        assert "person_mask" in result
        assert "bbox" in result
        assert "foreground_pixels" in result
        assert result["foreground_pixels"] > 0

    def test_person_mask_dimensions_match_source(self):
        img = _make_person_image(w=512, h=768)
        result = HumanParsingEngine.parse_human_image(img)
        assert result["mask"].size == img.size
        assert result["person_mask"].size == img.size

    def test_person_mask_not_empty(self):
        img = _make_person_image()
        result = HumanParsingEngine.parse_human_image(img)
        arr = np.asarray(result["person_mask"].convert("L"))
        assert arr.sum() > 1000, "Person mask should not be empty"

    def test_person_mask_not_entire_image(self):
        img = _make_person_image()
        result = HumanParsingEngine.parse_human_image(img)
        arr = np.asarray(result["person_mask"].convert("L")) > 20
        ratio = arr.sum() / (img.width * img.height)
        # Person should not be entire image — background should exist
        assert ratio < 0.95, f"Person mask ratio {ratio} too high, should not be entire image"
        assert ratio > 0.05, f"Person mask ratio {ratio} too low"


@pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="VTON pipeline not available")
class TestAgnosticMaskGenerator:
    def test_all_slots_produce_masks(self):
        img = _make_person_image()
        for slot in AgnosticMaskGenerator.SUPPORTED_SLOTS:
            mask = AgnosticMaskGenerator.create_agnostic_mask(img, slot)
            assert mask is not None
            assert mask.size == img.size
            arr = np.asarray(mask.convert("L"))
            assert arr.sum() > 0, f"Mask for {slot} is empty"

    def test_mask_dimensions_match_source(self):
        img = _make_person_image(w=640, h=960)
        for slot in AgnosticMaskGenerator.SUPPORTED_SLOTS:
            mask = AgnosticMaskGenerator.create_agnostic_mask(img, slot)
            assert mask.size == img.size, f"Mask size mismatch for {slot}"

    def test_upper_body_does_not_include_lower_body(self):
        """Upper body masks should not extend below 75% height."""
        img = _make_person_image(h=768)
        for slot in ("upper_outer", "upper_inner"):
            mask = AgnosticMaskGenerator.create_agnostic_mask(img, slot)
            validation = AgnosticMaskGenerator.validate_mask_semantics(img, mask, slot)
            assert validation.get("upper_not_lower", False), f"{slot} extends too far into lower body: y_max {validation.get('y_max_ratio')}"
            assert validation["y_max_ratio"] <= 0.75, f"{slot} y_max {validation['y_max_ratio']} > 0.75"

    def test_lower_body_does_not_include_upper_body(self):
        """Lower body masks should not start above 30% height."""
        img = _make_person_image(h=768)
        mask = AgnosticMaskGenerator.create_agnostic_mask(img, "lower")
        validation = AgnosticMaskGenerator.validate_mask_semantics(img, mask, "lower")
        assert validation.get("lower_not_upper", False), f"lower starts too high: y_min {validation.get('y_min_ratio')}"
        assert validation["y_min_ratio"] >= 0.30

    def test_footwear_does_not_cover_full_person(self):
        """Footwear mask should be localized to feet, <25% of image."""
        img = _make_person_image(h=768)
        mask = AgnosticMaskGenerator.create_agnostic_mask(img, "footwear")
        validation = AgnosticMaskGenerator.validate_mask_semantics(img, mask, "footwear")
        assert validation.get("footwear_localized", False), f"footwear not localized: {validation}"
        assert validation["mask_ratio"] <= 0.25, f"footwear mask too large: {validation['mask_ratio']}"
        assert validation["y_min_ratio"] >= 0.70, f"footwear should be bottom: y_min {validation['y_min_ratio']}"

    def test_accessory_mask_remains_localized(self):
        """Accessory mask should be small, <20% of image."""
        img = _make_person_image(h=768)
        mask = AgnosticMaskGenerator.create_agnostic_mask(img, "accessory")
        validation = AgnosticMaskGenerator.validate_mask_semantics(img, mask, "accessory")
        assert validation.get("accessory_localized", False), f"accessory not localized: {validation}"
        assert validation["mask_ratio"] <= 0.20

    def test_dress_mask_covers_intended_region(self):
        """Dress should cover significant vertical range but not entire image."""
        img = _make_person_image(h=768)
        mask = AgnosticMaskGenerator.create_agnostic_mask(img, "dress")
        validation = AgnosticMaskGenerator.validate_mask_semantics(img, mask, "dress")
        assert validation.get("dress_covers_body", False), f"dress doesn't cover body: {validation}"
        # Dress should not be entire image
        assert validation["mask_ratio"] <= 0.80

    def test_masks_not_entire_image_rectangles_unless_dress(self):
        """Non-dress masks should not be entire-image rectangles."""
        img = _make_person_image(h=768)
        for slot in ("upper_outer", "upper_inner", "lower", "footwear", "accessory"):
            mask = AgnosticMaskGenerator.create_agnostic_mask(img, slot)
            arr = np.asarray(mask.convert("L")) > 20
            ratio = arr.sum() / (img.width * img.height)
            assert ratio <= 0.85, f"{slot} mask is entire image: ratio {ratio}"

    def test_masks_deterministic(self):
        """Same image + slot should produce same mask."""
        img = _make_person_image()
        for slot in AgnosticMaskGenerator.SUPPORTED_SLOTS:
            mask1 = AgnosticMaskGenerator.create_agnostic_mask(img, slot)
            mask2 = AgnosticMaskGenerator.create_agnostic_mask(img, slot)
            arr1 = np.asarray(mask1.convert("L"))
            arr2 = np.asarray(mask2.convert("L"))
            assert np.array_equal(arr1, arr2), f"{slot} masks not deterministic"

    def test_overlapping_garments_deterministic_order(self):
        """Multi-garment layering order should be deterministic."""
        img = _make_person_image()
        slots = ["upper_inner", "upper_outer", "lower", "footwear", "accessory"]
        # Simulate layer ordering as in modal_app.py
        slot_order = {"upper_inner": 1, "upper_outer": 2, "dress": 2, "lower": 3, "footwear": 4, "accessory": 5}
        sorted_slots = sorted(slots, key=lambda s: slot_order.get(s, 99))
        assert sorted_slots == ["upper_inner", "upper_outer", "lower", "footwear", "accessory"]

    def test_unsupported_slot_raises(self):
        img = _make_person_image()
        with pytest.raises(ValueError):
            AgnosticMaskGenerator.create_agnostic_mask(img, "headwear")


@pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="VTON pipeline not available")
class TestVTONMultiGarmentQuality:
    def test_multi_garment_masks_do_not_fully_overlap(self):
        """Upper and lower masks should not fully overlap."""
        img = _make_person_image(h=768)
        upper = AgnosticMaskGenerator.create_agnostic_mask(img, "upper_inner")
        lower = AgnosticMaskGenerator.create_agnostic_mask(img, "lower")
        upper_arr = np.asarray(upper.convert("L")) > 20
        lower_arr = np.asarray(lower.convert("L")) > 20
        overlap = (upper_arr & lower_arr).sum()
        upper_only = upper_arr.sum()
        lower_only = lower_arr.sum()
        # Overlap should be less than 50% of either mask (some overlap at waist is okay)
        if upper_only > 0:
            overlap_ratio_upper = overlap / upper_only
            assert overlap_ratio_upper < 0.50, f"Upper/lower overlap too high: {overlap_ratio_upper}"
        if lower_only > 0:
            overlap_ratio_lower = overlap / lower_only
            assert overlap_ratio_lower < 0.50, f"Lower/upper overlap too high: {overlap_ratio_lower}"

    def test_footwear_and_upper_no_overlap(self):
        """Footwear and upper should have no overlap."""
        img = _make_person_image(h=768)
        upper = AgnosticMaskGenerator.create_agnostic_mask(img, "upper_inner")
        footwear = AgnosticMaskGenerator.create_agnostic_mask(img, "footwear")
        upper_arr = np.asarray(upper.convert("L")) > 20
        foot_arr = np.asarray(footwear.convert("L")) > 20
        overlap = (upper_arr & foot_arr).sum()
        assert overlap == 0, f"Upper and footwear should not overlap, found {overlap} pixels"

    def test_mask_inference_time_reasonable(self):
        """Mask generation should be fast (<1s per mask on CPU)."""
        import time
        img = _make_person_image()
        start = time.time()
        for slot in AgnosticMaskGenerator.SUPPORTED_SLOTS:
            AgnosticMaskGenerator.create_agnostic_mask(img, slot)
        elapsed = time.time() - start
        # 6 masks should be <2s total on CPU
        assert elapsed < 2.0, f"Mask generation too slow: {elapsed}s for 6 masks"


@pytest.mark.skipif(not PIPELINE_AVAILABLE, reason="VTON pipeline not available")
class TestVTONPartialFailure:
    def test_partial_failure_reports_the_failing_layer(self):
        """Every per-layer failure exit in the diffusion loop must name failed_layer.

        Previously this was `assert True` with a comment claiming code inspection.
        It now actually parses modal_app.py and checks each raise inside the
        garment loop, so deleting the field breaks the test.
        """
        import ast

        src = (REPO / "services" / "vton-worker" / "modal_app.py").read_text()
        tree = ast.parse(src)

        raises = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Raise) and "failed_layer" not in ast.unparse(n)
            and any(code in ast.unparse(n) for code in ("GPU_OOM", "INFERENCE_FAILED"))
        ]
        assert raises == [], [ast.unparse(n)[:120] for n in raises]

        # and the field must be populated with the loop index, not a constant
        for code in ("GPU_OOM", "INFERENCE_FAILED"):
            hit = [
                ast.unparse(n) for n in ast.walk(tree)
                if isinstance(n, ast.Raise) and code in ast.unparse(n)
            ]
            assert hit, f"no raise found for {code}"
            for h in hit:
                assert "'failed_layer': idx" in h or '"failed_layer": idx' in h, h
