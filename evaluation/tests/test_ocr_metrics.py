"""OCR metric tests (Phase 0.5 §28): presence, absence, occlusion leniency.

EasyOCR models are pre-warmed in ~/.EasyOCR (see LICENSE_AUDIT.md); these tests
are skipped (not failed) if the engine cannot initialize, so the suite stays
green on minimal envs while still PROOFING behavior where the engine exists.
"""
from __future__ import annotations

import pytest

from PIL import Image

from vton_metrics import ocr_metrics


@pytest.fixture(scope="module")
def reader_ok():
    try:
        ocr_metrics._get_reader()
        return True
    except Exception as e:
        pytest.skip(f"EasyOCR unavailable: {e}")


def test_text_detected_strict(text_img, reader_ok):
    img = Image.open(text_img).convert("RGB")
    rep = ocr_metrics.text_fidelity("STUDIO 2026", img, (0, 0, 600, 200), occluded=False)
    assert rep["score"] == 1.0, rep
    assert rep["exact_match"] is True


def test_text_partial_strict(text_img, reader_ok):
    img = Image.open(text_img).convert("RGB")
    rep = ocr_metrics.text_fidelity("STUDIO 1999", img, (0, 0, 600, 200), occluded=False)
    assert 0.0 < rep["score"] < 1.0, rep


def test_ocr_absence_on_plain(solid_img, reader_ok):
    """OCR-absence test: plain solid region must yield no unexpected text."""
    img = Image.open(solid_img).convert("RGB")
    rep = ocr_metrics.text_fidelity(None, img, (5, 5, 195, 195), occluded=False)
    assert rep["expected_text"] is None
    assert rep["unexpected_text_found"] is False
    assert rep["score"] == 1.0


def test_occluded_lenient_regime(text_img, reader_ok):
    """When occluded, partial word overlap earns full credit (documented leniency)."""
    img = Image.open(text_img).convert("RGB")
    strict = ocr_metrics.text_fidelity("STUDIO 1999", img, (0, 0, 600, 200), occluded=False)
    lenient = ocr_metrics.text_fidelity("STUDIO 1999", img, (0, 0, 600, 200), occluded=True)
    assert lenient["regime"].startswith("OCCLUSION_LENIENT")
    assert lenient["score"] >= strict["score"]
