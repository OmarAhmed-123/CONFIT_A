"""VTON complete gap-closure regression tests (2026-09-19).

Pins the exact gaps found in the 2026-09-19 complete VTON gap audit and
their root-cause fixes (report: docs/vton/VTON_COMPLETE_GAP_CLOSURE_REPORT_20260919.md):

G1  NO SILENT PERSON SUBSTITUTION at the API layer: the request schemas and
    service signatures no longer default ``avatar_model_id`` to a stock
    person; no photo + no explicit avatar => VTON_INPUT_INVALID.
G2  NO SILENT DEFAULT PRODUCT: POST /try-on/sessions with no garments
    fails explicitly instead of quietly rendering product 1.
G3  GDPR ART. 17 RETENTION ON JOB ROWS: tryon_jobs carry expires_at /
    consent_retained; the hourly purge daemon purges expired unconsented
    job rows (person photo data URLs) as well as session rows; and an
    opportunistic read-time purge enforces the same property when the
    beat worker is not running (serverless).
G4  VERIFIABLE TRACEABILITY CERTIFICATE: VTON-CERT-* is a content hash of
    the actually delivered render (recomputable by the recipient), not a
    hash of job_id+timestamp.
G5  SSRF GUARD FAILS CLOSED: if the SSRF check itself cannot run, the URL
    is blocked (the old path failed open and logged "allowing").
G6  OBSERVABILITY WITHOUT SENSITIVE DATA: logged image URLs never carry
    query strings (signed credentials).
G7  HONEST ANIMATED OUTCOME: the animated response and session row reflect
    the actual keyframe verification (no hardcoded "Optimal Garment Fit" /
    95 / "Identity Preserved").
G8  SLEEVE-GATE THRESHOLD METADATA: the v2.4 any-skin threshold (0.15) is
    reported alongside the other gate thresholds in the decision dict.

The GPU worker is mocked at the httpx boundary (no network, no GPU) — the
same deterministic mock contract as test_vton_person_reference.py.
"""

import base64
import inspect
import io
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.app.models.tryon import TryOnJob
from backend.app.schemas.tryon import (
    AnimationTryOnRequest,
    MultiGarmentTryOnRequest,
    TryOnJobCreate,
    TryOnRequest,
)
from backend.app.services import tryon_service
from backend.app.services.tryon_service import (
    TryOnService,
    _log_safe_url,
    _purge_vton_row_if_expired,
    resolve_person_reference,
    vton_cert_hash,
)
from backend.app.services.vton_sleeve_gate import ANATOMY_ANY_SKIN_REFUSE, evaluate_sleeves_sync
from backend.app.workers.tasks import purge_expired_sessions_task
from backend.tests.conftest import TestingSessionLocal as SessionLocal


PROCESS = "https://acct--test-vton-worker-process.modal.run"
SKIN = (210, 170, 140)

# Per-product flat-lay block colors (pairwise > dE 40 apart, and > dE 40 from
# the skin tone — the same contract as test_vton_person_reference.py). Each
# animated layer must be rendered in ITS OWN garment's color: the S31 change
# probe measures dE(output, input), so a second layer painted the same color
# as the first reads "no change" = not applied (correct gate behavior).
GARMENT_URL_COLORS = {
    "photo-1602810318383": (180, 40, 40),   # oxford (p3) — bright red
    "photo-1507679799987": (30, 80, 180),   # tuxedo (p2) — bright blue
}
DEFAULT_GARMENT_COLOR = (60, 60, 60)
_KNOWN_FLAT_COLORS = list(GARMENT_URL_COLORS.values()) + [DEFAULT_GARMENT_COLOR]

from backend.app.services.vton_sleeve_gate import _rgb_to_lab, garment_dominant_lab


def _lab_closest_flat(lab) -> tuple:
    best, best_d = None, None
    for c in _KNOWN_FLAT_COLORS:
        d = sum((x - y) ** 2 for x, y in zip(_rgb_to_lab(c), lab)) ** 0.5
        if best_d is None or d < best_d:
            best, best_d = c, d
    return best


def _flat_lay_bytes(url: str) -> bytes:
    color = DEFAULT_GARMENT_COLOR
    for key, c in GARMENT_URL_COLORS.items():
        if key in url:
            color = c
            break
    img = Image.new("RGB", (320, 320), (250, 250, 250))
    _paint_region(img, (0.2, 0.8, 0.2, 0.8), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()
_TORSO = (0.28, 0.72, 0.28, 0.56)
_FOREARMS = ((0.52, 0.70, 0.40, 0.55), (0.28, 0.46, 0.40, 0.55))


def _paint_region(img: Image.Image, box, color) -> None:
    px = img.load()
    w, h = img.size
    x0, x1, y0, y1 = box
    for y in range(int(y0 * h), int(y1 * h)):
        for x in range(int(x0 * w), int(x1 * w)):
            px[x, y] = color


def _person_jpeg_bytes() -> bytes:
    import random

    rng = random.Random(7)
    img = Image.new("RGB", (600, 800), color=SKIN)
    px = img.load()
    for _ in range(20000):
        px[rng.randrange(600), rng.randrange(800)] = (
            min(255, max(0, SKIN[0] + rng.randrange(-15, 16))),
            min(255, max(0, SKIN[1] + rng.randrange(-15, 16))),
            min(255, max(0, SKIN[2] + rng.randrange(-15, 16))),
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _person_data_url() -> str:
    return "data:image/jpeg;base64," + base64.b64encode(_person_jpeg_bytes()).decode()


def _rendered_data_url(layer: int = 0, paint: tuple | None = (30, 80, 180)) -> str:
    img = Image.new("RGB", (320, 568), color=(70 + 10 * layer, 90, 120))
    if paint is not None:
        _paint_region(img, _TORSO, paint)
        for box in _FOREARMS:
            _paint_region(img, box, paint)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _rendered_from_payload(payload: dict) -> tuple | None:
    """The faithful render for a process call: painted in the call's own
    garment's dominant flat-lay color (what a correctly applied long-sleeve
    garment looks like to the S31 probe)."""
    garments = payload.get("garments") or [{}]
    b64 = (garments[0] or {}).get("image_base64")
    if b64 and str(b64).startswith("data:"):
        try:
            raw = base64.b64decode(str(b64).split(",", 1)[1])
            lab = garment_dominant_lab(Image.open(io.BytesIO(raw)).convert("RGB"))
            if lab != (0.0, 0.0, 0.0):
                return _lab_closest_flat(lab)
        except Exception:  # noqa: BLE001
            return None
    return None


@pytest.fixture
def mock_worker(monkeypatch):
    """Deterministic worker mock: health OK; process calls succeed with a
    faithful applied-garment render (torso + forearm bands painted the
    garment's flat-lay block color — what the S31 sleeve probe sees on a
    correctly rendered long-sleeve garment). ``fail_process_from`` (set by
    tests) makes the Nth process call return 503 (transient worker
    unavailability) to exercise the partial-animation honest-outcome path."""
    from backend.app.services.tryon_service import VTON_AVATARS

    calls = {"process": 0, "fail_from": None}
    person_urls = set(VTON_AVATARS.values())

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host.endswith("-process.modal.run"):
            calls["process"] += 1
            if calls["fail_from"] is not None and calls["process"] >= calls["fail_from"]:
                return httpx.Response(503, json={
                    "error": {"code": "VTON_ENGINE_UNAVAILABLE",
                              "message": "Reason: transient worker unavailability (mock)"},
                })
            payload = json.loads(request.content or b"{}")
            paint = _rendered_from_payload(payload)
            return httpx.Response(200, json={
                "status": "completed",
                "rendered_image_data_url": _rendered_data_url(
                    layer=calls["process"] - 1, paint=paint),
                "model_used": "fashn-vton-v1.5 (test)",
                "verify": {"PASS": True, "metric_pixel_change": 40.0},
            })
        if host.endswith("-health.modal.run"):
            return httpx.Response(200, json={
                "status": "healthy", "model_loaded": True, "ready": True,
                "device": "NVIDIA A10", "git_sha": "testsha",
            })
        url = str(request.url)
        # person / avatar image fetches -> skin-toned person
        if any(u.split("?")[0] in url for u in person_urls):
            raw = _person_jpeg_bytes()
            return httpx.Response(200, content=raw, headers={"content-type": "image/jpeg"})
        # garment thumbnails -> per-product synthetic flat-lay
        return httpx.Response(200, content=_flat_lay_bytes(url),
                              headers={"content-type": "image/jpeg"})

    import httpx as _httpx

    transport = _httpx.MockTransport(handler)

    orig_async = _httpx.AsyncClient

    class _MockAsyncClient(orig_async):
        def __init__(self, *a, **kw):
            kw.pop("transport", None)
            super().__init__(*a, transport=transport, **kw)

    monkeypatch.setattr(_httpx, "AsyncClient", _MockAsyncClient)
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "VTON_WORKER_URL", PROCESS, raising=False)
    return calls


# =========================================================================
# G1 — explicit person reference at the API layer (no silent stock person)
# =========================================================================

def test_g1_schemas_have_no_silent_avatar_default():
    for model in (TryOnJobCreate, TryOnRequest, MultiGarmentTryOnRequest, AnimationTryOnRequest):
        field = model.model_fields["avatar_model_id"]
        assert field.default is None, f"{model.__name__}.avatar_model_id must default to None (no silent stock person)"


def test_g1_service_signatures_have_no_silent_avatar_default():
    for fn in (
        TryOnService.create_and_enqueue_vton_job,
        TryOnService.execute_multi_garment_tryon,
        TryOnService.execute_animated_tryon,
        TryOnService.execute_tryon,
    ):
        sig = inspect.signature(fn)
        assert sig.parameters["avatar_model_id"].default is None, f"{fn.__name__} must default avatar_model_id to None"


def test_g1_no_person_reference_raises():
    with pytest.raises(Exception) as ei:
        resolve_person_reference(None, None, None)
    assert "VTON_INPUT_INVALID" in str(ei.value)


def test_g1_api_empty_person_reference_rejected(client, mock_worker):
    """A render request with garments but NO person reference (and no
    explicit avatar) must fail as 422 VTON_INPUT_INVALID — the old code
    silently rendered a stock avatar."""
    resp = client.post("/api/v1/tryon/multi-render", json={"product_ids": [1]})
    assert resp.status_code == 422, resp.text
    body = resp.json()
    # ConfitException handler shape: canonical VTON code travels in the message
    assert "VTON_INPUT_INVALID" in body["error"]["message"]
    assert mock_worker["process"] == 0  # no GPU call for a rejected reference


def test_g1_explicit_avatar_still_works(client, mock_worker):
    resp = client.post(
        "/api/v1/tryon/multi-render",
        json={"product_ids": [1], "avatar_model_id": "avatar_athletic_m"},
    )
    assert resp.status_code == 200, resp.text
    assert mock_worker["process"] == 1


# =========================================================================
# G2 — no silent default product 1
# =========================================================================

def test_g2_session_endpoint_empty_request_rejected(client):
    resp = client.post("/api/v1/try-on/sessions", json={})
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["detail"]["error"]["code"] == "VTON_INPUT_INVALID"


# =========================================================================
# G3 — GDPR Art. 17 retention on job rows
# =========================================================================

def test_g3_job_creation_sets_retention(client, mock_worker):
    job_resp = client.post(
        "/api/v1/tryon/jobs",
        json={"product_ids": [1], "user_image_base64": _person_data_url()},
    )
    assert job_resp.status_code == 202, job_resp.text
    job_id = job_resp.json()["job_id"]

    db = SessionLocal()
    try:
        job = db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        assert job is not None
        assert job.consent_retained in (False, 0)
        assert job.expires_at is not None
        # default (unconsented) retention ≈ 24h
        delta = job.expires_at - job.created_at
        assert abs(delta - timedelta(hours=24)) < timedelta(minutes=5)
        assert job.input_person_image_url.startswith("data:image/")
    finally:
        db.close()


def test_g3_consent_extends_retention(client, mock_worker):
    job_resp = client.post(
        "/api/v1/tryon/jobs",
        json={
            "product_ids": [1],
            "user_image_base64": _person_data_url(),
            "consent_retain_photo": True,
        },
    )
    assert job_resp.status_code == 202, job_resp.text
    job_id = job_resp.json()["job_id"]
    db = SessionLocal()
    try:
        job = db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        assert job.consent_retained in (True, 1)
        delta = job.expires_at - job.created_at
        assert abs(delta - timedelta(hours=720)) < timedelta(minutes=5)
    finally:
        db.close()


def _make_job(job_id: str, *, expires_at, consent: bool, person_data_url: str) -> None:
    db = SessionLocal()
    try:
        db.add(TryOnJob(
            job_id=job_id,
            status="completed",
            current_stage="harmonized_and_verified",
            input_person_image_url=person_data_url,
            garment_ids_json="[1]",
            garment_layers_json="[]",
            model_used="fashn-vton-v1.5 (test)",
            metrics_json="{}",
            expires_at=expires_at,
            consent_retained=consent,
        ))
        db.commit()
    finally:
        db.close()


def test_g3_purge_task_purges_expired_unconsented_job_rows(monkeypatch):
    now = datetime.now(timezone.utc)
    _make_job("vton_job_gc_purged", expires_at=now - timedelta(hours=1),
              consent=False, person_data_url="data:image/png;base64,AAAA")
    _make_job("vton_job_gc_kept_consent", expires_at=now - timedelta(hours=1),
              consent=True, person_data_url="data:image/png;base64,BBBB")
    _make_job("vton_job_gc_kept_future", expires_at=now + timedelta(hours=1),
              consent=False, person_data_url="data:image/png;base64,CCCC")

    # the celery task uses the app-level SessionLocal; point it at the test DB
    from backend.app import workers

    monkeypatch.setattr(workers.tasks, "SessionLocal", SessionLocal)
    result = purge_expired_sessions_task()
    assert result["purged_job_count"] >= 1

    db = SessionLocal()
    try:
        purged = db.query(TryOnJob).filter(TryOnJob.job_id == "vton_job_gc_purged").first()
        assert purged.input_person_image_url == "[PURGED_FOR_PRIVACY]"
        kept_c = db.query(TryOnJob).filter(TryOnJob.job_id == "vton_job_gc_kept_consent").first()
        assert kept_c.input_person_image_url == "data:image/png;base64,BBBB"
        kept_f = db.query(TryOnJob).filter(TryOnJob.job_id == "vton_job_gc_kept_future").first()
        assert kept_f.input_person_image_url == "data:image/png;base64,CCCC"
    finally:
        db.close()


def test_g3_read_time_opportunistic_purge():
    """Serverless production does not run the beat worker: the retention
    property must still hold at read time."""
    now = datetime.now(timezone.utc)
    _make_job("vton_job_gc_lazy", expires_at=now - timedelta(hours=2),
              consent=False, person_data_url="data:image/png;base64,DDDD")
    # delivery token binding: guest job (user_id NULL) must present its
    # one-time token (canonical ownership contract)
    from backend.app.services.vton_delivery import TemporaryImageStore

    token = "gc-lazy-token"
    db = SessionLocal()
    try:
        job = db.query(TryOnJob).filter(TryOnJob.job_id == "vton_job_gc_lazy").first()
        job.delivery_token_hash = TemporaryImageStore._token_hash(token)
        db.commit()
    finally:
        db.close()

    service = TryOnService(SessionLocal())
    out = service.get_vton_job_status("vton_job_gc_lazy", caller_user_id=None, delivery_token=token)
    assert out["status"] == "completed"

    db = SessionLocal()
    try:
        row = db.query(TryOnJob).filter(TryOnJob.job_id == "vton_job_gc_lazy").first()
        assert row.input_person_image_url == "[PURGED_FOR_PRIVACY]"
    finally:
        db.close()


def test_g3_purge_helper_semantics():
    now = datetime.now(timezone.utc)
    future = type("Row", (), {})()
    future.expires_at = now + timedelta(hours=1)
    future.consent_retained = False
    future.input_user_image_url = "data:image/png;base64,XXXX"
    future.input_person_image_url = None
    assert _purge_vton_row_if_expired(future) is False
    assert future.input_user_image_url == "data:image/png;base64,XXXX"

    expired = type("Row", (), {})()
    expired.expires_at = now - timedelta(hours=1)
    expired.consent_retained = False
    expired.input_user_image_url = "data:image/png;base64,YYYY"
    expired.input_person_image_url = "data:image/jpeg;base64,ZZZZ"
    assert _purge_vton_row_if_expired(expired) is True
    assert expired.input_user_image_url == "[PURGED_FOR_PRIVACY]"
    assert expired.input_person_image_url == "[PURGED_FOR_PRIVACY]"

    consented = type("Row", (), {})()
    consented.expires_at = now - timedelta(hours=1)
    consented.consent_retained = True
    consented.input_user_image_url = "data:image/png;base64,WWWW"
    assert _purge_vton_row_if_expired(consented) is False


# =========================================================================
# G4 — verifiable VTON-CERT traceability
# =========================================================================

def test_g4_cert_hash_format_and_determinism():
    h1 = vton_cert_hash(job_id="j1", model_used="m", rendered_data_url="data:image/png;base64,AAA")
    h2 = vton_cert_hash(job_id="j1", model_used="m", rendered_data_url="data:image/png;base64,AAA")
    h3 = vton_cert_hash(job_id="j1", model_used="m", rendered_data_url="data:image/png;base64,AAB")
    assert h1 == h2
    assert h1 != h3
    assert re.fullmatch(r"VTON-CERT-[0-9A-F]{16}", h1)


def test_g4_cert_hash_verifiable_from_delivered_artifact(client, mock_worker):
    """The certificate hash persisted on the job must be recomputable from
    the exact data URL the client received (BRD G3.1: verifiable
    disclosure), unlike the old job_id+timestamp hash."""
    resp = client.post(
        "/api/v1/tryon/jobs",
        json={"product_ids": [1], "user_image_base64": _person_data_url()},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    job_id = body["job_id"]
    delivered = body.get("result_image_data_url")
    assert delivered, "completion response must carry the guaranteed delivery vehicle"
    # guest job: polling is bound to the one-time delivery token (ownership
    # contract, no existence leakage)
    token = body["delivery"]["token"]
    status = client.get(f"/api/v1/tryon/jobs/{job_id}", params={"delivery_token": token}).json()
    assert status["status"] == "completed"
    cert = status["metrics"]["traceability_hash"]
    assert cert.startswith("VTON-CERT-")
    assert cert == vton_cert_hash(
        job_id=job_id,
        model_used=body.get("model_used") or "fashn-vton-v1.5 (test)",
        rendered_data_url=delivered,
    )


# =========================================================================
# G5 — SSRF guard fails closed
# =========================================================================

def test_g5_ssrf_guard_fail_closed(client, monkeypatch):
    """If the SSRF guard cannot run, the URL must be BLOCKED (the old code
    failed open with 'ssrf_check_failed_allowing')."""
    monkeypatch.setitem(sys.modules, "backend.app.core.security", None)  # import -> ImportError
    service = TryOnService(SessionLocal())
    import asyncio

    result = asyncio.run(
        service._fetch_image_as_base64("https://example.com/img.jpg?sig=SECRET")
    )
    assert result is None  # blocked, not fetched


# =========================================================================
# G6 — observability without sensitive data
# =========================================================================

def test_g6_log_safe_url_strips_query_and_fragment():
    assert _log_safe_url("https://cdn.example.com/img.jpg?sig=SECRET&exp=1#frag") == "https://cdn.example.com/img.jpg"
    assert _log_safe_url("data:image/png;base64,AAA?x=1") == "data:image/png (data URL redacted)"
    assert _log_safe_url("") == ""
    assert "SECRET" not in _log_safe_url("https://x.io/a/b.png?token=SECRET")
    assert "AAA" not in _log_safe_url("data:image/png;base64,AAA")


# =========================================================================
# G7 — honest animated outcome
# =========================================================================

def test_g7_animated_partial_failure_honest_response_and_session(client, mock_worker):
    """Frame 2 fails with a transient 503 (worker unavailable): the
    response and the session row must reflect the ACTUAL keyframe
    verification — no hardcoded 'Optimal Garment Fit' / 95 / 'Identity
    Preserved'."""
    mock_worker["fail_from"] = 2
    resp = client.post("/api/v1/tryon/animation-render", json={
        "product_ids": [3, 2],
        "user_image_url": _person_data_url(),
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["fit_confidence_score"] == 50
    assert body["body_fit_verdict"] == "Only 1 of 2 layer(s) rendered - 1 layer(s) failed"
    assert "Identity Preserved" not in body["ai_disclosure"]
    assert "CatVTON" not in body["ai_disclosure"]
    assert "fashn" in body["ai_disclosure"]
    assert body["verification"]["frames_requested"] == 2
    assert body["verification"]["frames_succeeded"] == 1
    assert body["verification"]["failed_frames"] == [2]

    kfs = body["keyframes_sequence"]
    assert kfs[0].get("failed") is not True
    assert kfs[1].get("failed") is True

    # the session row carries the same honest values
    session_id = body["session_id"]
    db = SessionLocal()
    try:
        from backend.app.models.tryon import TryOnSession

        sess = db.query(TryOnSession).filter(TryOnSession.id == session_id).first()
        assert sess.fit_confidence_score == 50
        assert "Only 1 of 2" in sess.body_fit_verdict
    finally:
        db.close()


def test_g7_animated_full_success_honest_verdict(client, mock_worker):
    resp = client.post("/api/v1/tryon/animation-render", json={
        "product_ids": [3, 2],
        "user_image_url": _person_data_url(),
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fit_confidence_score"] == 100
    assert body["body_fit_verdict"] == "All 2 layer(s) rendered and engine-verified"
    assert "Identity Preserved" not in body["ai_disclosure"]


# =========================================================================
# G8 — sleeve-gate threshold metadata completeness
# =========================================================================

def test_g8_decision_reports_v24_any_skin_threshold():
    img = Image.new("RGB", (32, 32), (200, 200, 200))
    decision = evaluate_sleeves_sync(
        slot_type="upper_outer",
        sleeve_length="long",
        output_img=img,
        input_img=img,
        garment_img=img,
    )
    thresholds = decision["thresholds"]
    assert thresholds["anatomy_any_skin_refuse"] == ANATOMY_ANY_SKIN_REFUSE == 0.15
    # v2.4 rule intact: the frozen thresholds are all present and unchanged
    assert thresholds["pass"] == 0.35
    assert thresholds["fail"] == 0.15
    assert thresholds["anatomy_new_skin_refuse"] == 0.10
    assert thresholds["anatomy_wrist_reach_refuse"] == 0.05
    assert thresholds["change"] == 20.0
