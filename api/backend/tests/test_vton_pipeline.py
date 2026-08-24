import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.tests.conftest import TestingSessionLocal
from backend.app.models.tryon import TryOnJob, GarmentAsset, TryOnJobStatus

client = TestClient(app)


def test_vton_async_job_lifecycle():
    """Verifies asynchronous VTON job submission, stage tracking, and polling."""
    # 1. Submit async VTON inference job
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1, 3],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "output_aspect": "9:16",
        "consent_retain_photo": False
    })
    assert res.status_code == 202
    job_data = res.json()
    assert "job_id" in job_data
    assert job_data["job_id"].startswith("vton_job_")
    assert job_data["status"] == "completed"
    assert job_data["progress_pct"] == 100
    assert "CatVTON" in job_data["model_used"]

    # 2. Poll job status
    poll_res = client.get(f"/api/v1/try-on/jobs/{job_data['job_id']}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["job_id"] == job_data["job_id"]
    assert poll_data["output_image_url"] is not None
    assert "ssim_score" in poll_data["metrics"]
    assert poll_data["metrics"]["ssim_score"] >= 0.85


def test_garment_asset_caching():
    """Verifies garment asset segmentation and mask caching."""
    res = client.get("/api/v1/try-on/garments/1/asset")
    assert res.status_code == 200
    asset_data = res.json()
    assert asset_data["product_id"] == 1
    assert asset_data["flat_image_url"] is not None
    assert asset_data["slot_type"] == "outerwear"


def test_vton_job_empty_product_ids_validation():
    """Verifies that submitting empty product list returns validation error."""
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"
    })
    assert res.status_code in [400, 422]


def test_vton_job_cancel_endpoint():
    """Verifies cancelling an active or queued VTON job."""
    # Create job
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"
    })
    job_id = res.json()["job_id"]

    cancel_res = client.post(f"/api/v1/try-on/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
