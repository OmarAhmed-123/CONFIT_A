"""VTON integrity regression guards.

These tests encode the acceptance criteria from the VTON root-cause analysis
so the defects cannot return silently:

- D1: no completed job may point at a bundled static asset.
- D2: known fabricated metric constants must never appear.
- A7: without a GPU worker, jobs fail truthfully (no substitute image).
- D6: the worker rejects unknown slot types; every seeded catalogue category
  maps to a supported worker slot.
"""

import importlib.util
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.app.services.tryon_service import CATEGORY_TO_VTON_SLOT

client = TestClient(app)

# Load the worker's segmentation module directly from its file path
# (the directory name 'vton-worker' is not a valid Python package name).
_SEGMENTATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "services", "vton-worker", "pipeline", "segmentation.py"
)
_spec = importlib.util.spec_from_file_location("vton_segmentation", _SEGMENTATION_PATH)
_segmentation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_segmentation)
AgnosticMaskGenerator = _segmentation.AgnosticMaskGenerator


def _submit_job(**overrides):
    payload = {
        "product_ids": [1],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "consent_retain_photo": False,
    }
    payload.update(overrides)
    res = client.post("/api/v1/try-on/jobs", json=payload)
    assert res.status_code == 202
    return res.json()


def test_job_never_returns_a_static_asset():
    """D1 guard: no job may point at a bundled static file."""
    out = _submit_job(product_ids=[1, 2, 5])
    assert "/tryon_results/" not in (out["output_image_url"] or "")


def test_completed_job_metrics_are_never_literal():
    """D2 guard: the known fake constants must never appear in any response."""
    out = _submit_job()
    metrics = out["metrics"]
    assert metrics.get("ssim_score") != 0.914
    assert metrics.get("lpips_score") != 0.046
    assert metrics.get("identity_preservation_score") not in (98.5, 0.985)
    assert metrics.get("inference_time_ms") != 420.0


def test_without_worker_job_fails_truthfully(monkeypatch):
    """A7 guard: no configured worker ⇒ status failed, no image, no metrics."""
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    out = _submit_job()
    assert out["status"] == "failed"
    assert out["error_code"] == "VTON_ENGINE_UNAVAILABLE"
    assert out["output_image_url"] is None
    assert out["metrics"] == {}


def test_worker_rejects_unknown_slot():
    """D6 guard: an unknown slot is a hard error, never a default mask."""
    img = Image.new("RGB", (768, 1024), color=(200, 200, 200))
    with pytest.raises(ValueError, match="Unsupported slot_type"):
        AgnosticMaskGenerator.create_agnostic_mask(img, "tops")
    with pytest.raises(ValueError, match="Unsupported slot_type"):
        AgnosticMaskGenerator.create_agnostic_mask(img, "dresses")


@pytest.mark.parametrize("slug,expected", [
    ("outerwear", "upper_outer"),
    ("tops", "upper_inner"),
    ("bottoms", "lower"),
    ("dresses", "dress"),
    ("footwear", "footwear"),
    ("accessories", "accessory"),
])
def test_every_catalogue_category_maps_to_a_supported_slot(slug, expected):
    """D6 guard: fails the build if a new category is added without a mapping."""
    assert CATEGORY_TO_VTON_SLOT[slug] == expected
    assert expected in AgnosticMaskGenerator.SUPPORTED_SLOTS


@pytest.mark.parametrize("slug", list(CATEGORY_TO_VTON_SLOT.keys()))
def test_every_mapped_slot_produces_a_mask(slug):
    """Every mapped slot must actually render a mask region (no fall-through)."""
    import numpy as np

    img = Image.new("RGB", (768, 1024), color=(200, 200, 200))
    mask = AgnosticMaskGenerator.create_agnostic_mask(img, CATEGORY_TO_VTON_SLOT[slug])
    coverage = float((np.array(mask) > 128).mean())
    assert coverage > 0.01, f"slot for '{slug}' produced an empty mask"
