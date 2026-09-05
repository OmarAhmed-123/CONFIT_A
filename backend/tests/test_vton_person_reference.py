"""VTON person/pose reference contract (2026-09-05 pose-preservation directive).

Rules pinned here (service + API level):

1. NO SILENT SUBSTITUTION: a job with no person image and no explicit avatar
   fails as VTON_INPUT_INVALID — no stock photo is substituted behind the
   user's back.
2. EXPLICIT AVATAR MODE: an unknown avatar_model_id is rejected; a known one
   resolves to that avatar asset (the row records it).
3. PHOTO WINS: an uploaded person image always takes precedence over the
   (default) avatar id the frontend co-sends.
4. NEVER A GARMENT: the person reference is never taken from a product /
   garment asset.
5. PRE-INFERENCE VALIDATION: too-small / undecodable person images fail as
   VTON_INPUT_INVALID before any GPU call (mock worker sees no process call).
6. SSRF: unsafe person URLs are rejected before the GPU call.
7. DUPLICATE SELECTION: repeated product_ids are deduped explicitly.

The GPU worker is mocked at the httpx boundary (no network, no GPU).
"""

import base64
import io
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.models.tryon import TryOnJob
from backend.tests.conftest import TestingSessionLocal as SessionLocal

PROCESS = "https://acct--test-vton-worker-process.modal.run"


def _rendered_data_url(layer: int = 0) -> str:
    """Deterministic per-layer render: each inference layer produces a
    DISTINCT image (a real GPU call always changes the pixels — the service
    echo-check relies on that)."""
    img = Image.new("RGB", (320, 568), color=(70 + 10 * layer, 90, 120))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _small_person_data_url(size=(32, 32)) -> str:
    img = Image.new("RGB", size, color=(200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def mock_worker(monkeypatch):
    """Routes ALL httpx traffic (worker legs AND person/garment fetches)
    through a deterministic mock. Records which process calls happened."""
    calls = {"process": [], "person_fetches": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host.endswith("-process.modal.run"):
            calls["process"].append(json.loads(request.content or b"{}"))
            return httpx.Response(200, json={
                "status": "completed",
                "rendered_image_data_url": _rendered_data_url(layer=len(calls["process"]) - 1),
                "model_used": "fashn-vton-v1.5 (test)",
                "verify": {"PASS": True, "metric_pixel_change": 40.0},
            })
        if host.endswith("-health.modal.run"):
            return httpx.Response(200, json={
                "status": "healthy", "model_loaded": True, "ready": True,
                "device": "NVIDIA A10", "git_sha": "testsha",
            })
        # person/garment image fetches (unsplash etc.)
        calls["person_fetches"] += 1
        import random

        rng = random.Random(7)
        img = Image.new("RGB", (600, 800), color=(90, 90, 140))
        px = img.load()
        for _ in range(20000):  # texture so the JPEG stays > 10KB
            px[rng.randrange(600), rng.randrange(800)] = (
                rng.randrange(60, 180), rng.randrange(60, 180), rng.randrange(60, 180))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return httpx.Response(200, content=buf.getvalue(),
                              headers={"content-type": "image/jpeg"})

    state = {"transport": httpx.MockTransport(handler)}
    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = state["transport"]
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", PROCESS, raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_HEALTH_URL", None, raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_READINESS_URL", None, raising=False)
    monkeypatch.delenv("VTON_WORKER_HEALTH_URL", raising=False)
    monkeypatch.delenv("VTON_WORKER_READINESS_URL", raising=False)
    return calls


def _job_row(job_id: str):
    db = SessionLocal()
    try:
        return db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
    finally:
        db.close()


PERSON = "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"


# ── 1. no silent substitution ─────────────────────────────────────────────
def test_service_rejects_missing_person_reference(mock_worker):
    """Service-level invariant: with NO person image and NO avatar id, the
    service must raise VTON_INPUT_INVALID — it never fabricates a person.
    (The public schema documents ``avatar_athletic_m`` as its default, so a
    bare API call is an *explicit* avatar-mode request, not a silent one.)"""
    import asyncio

    from backend.app.services.tryon_service import TryOnService

    TestClient(app)  # ensure app/db fixtures are up
    db = SessionLocal()
    try:
        service = TryOnService(db)
        with pytest.raises(Exception) as ei:  # ValidationDomainError
            asyncio.run(service.create_and_enqueue_vton_job(
                product_ids=[1],
                user_image_url=None,
                user_image_base64=None,
                avatar_model_id=None,
            ))
        assert "VTON_INPUT_INVALID" in str(ei.value), str(ei.value)
        assert mock_worker["process"] == []
    finally:
        db.close()


def test_unknown_avatar_id_is_rejected(mock_worker):
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1], "avatar_model_id": "avatar_evil_1"}
    )
    assert res.status_code == 422, res.text
    assert "unknown avatar_model_id" in res.text
    assert mock_worker["process"] == []


# ── 2. explicit avatar mode ───────────────────────────────────────────────
def test_avatar_mode_uses_the_explicit_avatar_asset(mock_worker):
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1], "avatar_model_id": "avatar_athletic_m"}
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["job_id"]
    row = _job_row(job_id)
    assert row is not None
    from backend.app.services.tryon_service import VTON_AVATARS
    assert row.input_person_image_url == VTON_AVATARS["avatar_athletic_m"]
    # the person reference is NOT any catalog product thumbnail
    for pid in (1,):
        assert not str(row.input_person_image_url).endswith(str(pid))


# ── 3. uploaded photo wins over the co-sent avatar ────────────────────────
def test_uploaded_photo_wins_over_avatar(mock_worker):
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1], "user_image_url": PERSON,
        "avatar_model_id": "avatar_athletic_m"}
    )
    assert res.status_code == 202, res.text
    row = _job_row(res.json()["job_id"])
    assert row.input_person_image_url == PERSON
    from backend.app.services.tryon_service import VTON_AVATARS
    assert row.input_person_image_url != VTON_AVATARS["avatar_athletic_m"]


# ── 5. pre-inference person validation (before any GPU call) ──────────────
def test_tiny_person_image_rejected_before_gpu(mock_worker):
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1], "user_image_base64": _small_person_data_url()}
    )
    assert res.status_code == 202  # job flow; the job itself fails explicitly
    job = res.json()
    assert job["status"] == "failed", job
    assert job["error_code"] == "VTON_INPUT_INVALID", job
    assert "too small" in (job.get("error_message") or ""), job
    assert mock_worker["process"] == [], "GPU must not be called with a tiny person"


def test_undecodable_person_rejected_before_gpu(mock_worker):
    client = TestClient(app)
    bad = "data:image/png;base64," + base64.b64encode(b"not an image at all " * 20).decode()
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1], "user_image_base64": bad}
    )
    job = res.json()
    assert job["status"] == "failed"
    assert job["error_code"] == "VTON_INPUT_INVALID"
    assert mock_worker["process"] == []


# ── 6. SSRF stays active on the person reference ──────────────────────────
def test_ssrf_person_url_rejected_before_gpu(mock_worker):
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1], "user_image_url": "http://169.254.169.254/latest/meta-data/"}
    )
    job = res.json()
    assert job["status"] == "failed"
    assert job["error_code"] == "VTON_INPUT_INVALID"
    assert mock_worker["process"] == []


# ── 7. duplicate selection deduped explicitly ─────────────────────────────
def test_duplicate_product_ids_deduped(mock_worker):
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1, 1, 1, 2], "user_image_url": PERSON}
    )
    assert res.status_code == 202, res.text
    row = _job_row(res.json()["job_id"])
    ids = json.loads(row.garment_ids_json)
    assert sorted(ids) == [1, 2], ids
    # and the worker received each garment exactly once (one garment per
    # inference call; the union of sequential calls covers both)
    pids = [g["product_id"] for c in mock_worker["process"] for g in c["garments"]]
    assert sorted(pids) == [1, 2], pids


# ── 8. a valid full-outfit job still completes (no over-validation) ───────
def test_valid_full_outfit_job_completes(mock_worker):
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1, 2, 4], "user_image_url": PERSON}
    )
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["status"] == "completed", job
    assert (job.get("result_image_data_url") or "").startswith("data:image")
    assert job["delivery"]["carrier"] == "in_response"
    assert job["delivery"]["guaranteed_field"] == "result_image_data_url"


# ---------------------------------------------------------------------------
# Full-outfit chaining (worker contract: max 1 garment per inference call)
# ---------------------------------------------------------------------------

@pytest.fixture
def flaky_worker(monkeypatch):
    """Same as ``mock_worker`` but the SECOND process call fails with 500 —
    used to prove a mid-chain layer failure fails the whole job honestly."""
    calls = {"process": []}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host.endswith("-process.modal.run"):
            calls["process"].append(json.loads(request.content or b"{}"))
            if len(calls["process"]) == 1:
                return httpx.Response(200, json={
                    "status": "completed",
                    "rendered_image_data_url": _rendered_data_url(layer=0),
                    "model_used": "fashn-vton-v1.5 (test)",
                    "verify": {"PASS": True, "metric_pixel_change": 40.0},
                })
            return httpx.Response(500, json={"detail": "boom on layer 2"})
        if host.endswith("-health.modal.run"):
            return httpx.Response(200, json={
                "status": "healthy", "model_loaded": True, "ready": True,
                "device": "NVIDIA A10", "git_sha": "testsha",
            })
        import random

        rng = random.Random(7)
        img = Image.new("RGB", (600, 800), color=(90, 90, 140))
        px = img.load()
        for _ in range(20000):
            px[rng.randrange(600), rng.randrange(800)] = (
                rng.randrange(60, 180), rng.randrange(60, 180), rng.randrange(60, 180))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return httpx.Response(200, content=buf.getvalue(),
                              headers={"content-type": "image/jpeg"})

    state = {"transport": httpx.MockTransport(handler)}
    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = state["transport"]
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", PROCESS, raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_HEALTH_URL", None, raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_READINESS_URL", None, raising=False)
    monkeypatch.delenv("VTON_WORKER_HEALTH_URL", raising=False)
    monkeypatch.delenv("VTON_WORKER_READINESS_URL", raising=False)
    return calls


def test_full_outfit_chains_single_garment_inferences(mock_worker):
    """A 2-garment job must run 2 sequential single-garment inferences where
    layer 2 renders on layer 1's OUTPUT (complete outfit on the uploaded
    person) — never one combined multi-garment call (the deployed worker
    rejects those: 'max 1 garment per job')."""
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1, 2], "user_image_url": PERSON})
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["status"] == "completed", job

    assert len(mock_worker["process"]) == 2, "2 garments -> 2 sequential inferences"
    for c in mock_worker["process"]:
        assert len(c["garments"]) == 1, "worker never receives a multi-garment call"
    assert [g["product_id"] for g in mock_worker["process"][0]["garments"]] == [1]
    assert [g["product_id"] for g in mock_worker["process"][1]["garments"]] == [2]

    # layer 1 anchors the resolved person; layer 2 renders on layer 1's
    # output; the job result is the FINAL frame (complete outfit).
    render_1, render_2 = _rendered_data_url(layer=0), _rendered_data_url(layer=1)
    assert mock_worker["process"][0]["user_image_base64_or_url"].startswith("data:image")
    assert mock_worker["process"][1]["user_image_base64_or_url"] == render_1, (
        "layer 2 must render on layer 1's output (sequential architecture)")
    assert job["result_image_data_url"] == render_2, "result is the FINAL frame"

    row = _job_row(res.json()["job_id"])
    metrics = json.loads(row.metrics_json)
    assert metrics["garments_requested"] == 2
    assert [l["product_id"] for l in metrics["outfit_layers"]] == [1, 2], (
        "metrics prove the WHOLE selected outfit was applied, in order")


def test_chain_layer_failure_fails_job_honestly(flaky_worker):
    """If the second layer's inference fails, the job must FAIL — a partial
    first-layer image may never be presented as the completed full outfit."""
    client = TestClient(app)
    res = client.post("/api/v1/try-on/jobs", json={
        "product_ids": [1, 2], "user_image_url": PERSON})
    job = res.json()
    assert job["status"] == "failed", job
    assert job.get("result_image_data_url") in (None, ""), "no partial result as success"
    assert job.get("error_code") is not None
    assert len(flaky_worker["process"]) == 2, "both layers were attempted in order"
