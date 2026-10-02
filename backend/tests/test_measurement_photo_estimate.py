"""Feature 05 (body measurements from a photo) — backend contract tests.

Pins the /measurements/sessions/{id}/photo-estimate pipeline against the
LIVE worker contract (mirrors the real response captured from
confit-anthropometry-worker on 2026-10-02, job live-smoke-001):

  * happy path: consented owner session + photo -> honest measurement set
    persisted (height from the direct-geometry stature, chest/hip/inseam
    only where the worker kept them, shoulder/waist NEVER fabricated),
    quality-derived confidence, ±2-3 cm note and exclusions passed through;
  * worker refusals (out-of-envelope pose etc.) -> 422 with the worker's
    actionable guidance, session marked failed;
  * worker unavailable (timeout/unreachable/not configured) -> 503
    retryable, no rows;
  * consent missing -> 403; foreign/unknown session -> 404; guests are
    owner-gated by X-Session-Token;
  * provider-level unit tests: response validation (missing disclosures,
    invalid sources, commercial flag) and HTTP error envelopes.
"""
from __future__ import annotations


import io
import json

import httpx
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.core import config as config_mod
from backend.app.providers.anthropometry_provider import (
    AnthropometryProvider,
    _validate_worker_response,
)
from backend.tests.conftest import TestingSessionLocal

from sqlalchemy import text

DEAD_REDIS = "redis://127.0.0.1:63790/9"


# ── the real worker response shape (live 2026-10-02) ────────────────────────
def _worker_ok(quality: str = "partial") -> dict:
    body = {
        "status": "completed",
        "sex": "male",
        "quality": quality,
        "measurements": [
            {"name": "Chest Circumference (mm)", "value_mm": 774.7, "value_cm": 77.5, "source": "model"},
            {"name": "Head Circumference (mm)", "value_mm": 569.5, "value_cm": 57.0, "source": "model"},
            {"name": "Stature (mm)", "value_mm": 1539.7, "value_cm": 154.0, "source": "model"},
            {"name": "Arm Length (Shoulder to Elbow)", "value_mm": 246.2, "value_cm": 24.6, "source": "direct_geometry"},
            {"name": "Arm Length (Shoulder to Wrist)", "value_mm": 486.6, "value_cm": 48.7, "source": "direct_geometry"},
            {"name": "Inseam (Hip to Ankle)", "value_mm": 889.3, "value_cm": 88.9, "source": "direct_geometry"},
            {"name": "Stature", "value_mm": 1760.1, "value_cm": 176.0, "source": "direct_geometry"},
        ],
        "measurement_count": 7,
        "excluded": [
            {"name": "Ankle Circumference (mm)", "value_mm": 81.1, "reason": "outside_anatomical_range"},
            {"name": "Hip Circumference, Maximum (mm)", "value_mm": 633.2, "reason": "outside_anatomical_range"},
        ],
        "excluded_count": 2,
        "measurement_method": "ai_estimate",
        "accuracy_note": "±2-3 cm",
        "disclaimer": "AI-estimated measurements are approximate (±2-3 cm) and derived from a single photo.",
        "landmark_source": "mediapipe_pose_world_approx",
        "pose_quality": {"yaw_deg": 7.9, "shoulder_tilt_deg": 10.1, "arm_bend_ratio": 0.023, "knee_angle_deg": 150.0},
        "scale_calibration": {"applied": True, "source": "user_reported_height", "factor": 1.1643, "reported_height_cm": 176.0},
        "engine": "landmarks2anthropometry_visapp2024_cpu",
        "model": {
            "name": "Landmarks2Anthropometry (VISAPP 2024, Bayesian ridge per measurement)",
            "vendor_commit": "de2df48dd428dce457339141c709d7510e0e6f2b",
            "landmark_detector": "mediapipe pose_landmarker_heavy (Apache-2.0)",
            "license": "unlicensed-research-only",
            "commercial": False,
        },
        "timings": {"total_seconds": 0.12, "model_seconds": 0.001},
    }
    if quality == "full":
        body["excluded"] = []
        body["excluded_count"] = 0
        body["measurements"].insert(0, {"name": "Hip Circumference, Maximum (mm)", "value_mm": 933.2, "value_cm": 93.3, "source": "model"})
    return body


def _worker_envelope(body: dict) -> dict:
    body = dict(body)
    body["estimation_available"] = True
    return body


def _jpg_bytes() -> bytes:
    img = Image.new("RGB", (64, 160), (120, 120, 120))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def broker_down(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "REDIS_URL", DEAD_REDIS, raising=False)


@pytest.fixture
def worker_env(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "ANTHROPOMETRY_WORKER_URL",
                        "https://anthro-worker.test/estimate", raising=False)
    monkeypatch.setattr(config_mod.settings, "ANTHROPOMETRY_WORKER_ADMIN_TOKEN",
                        "test-admin-token", raising=False)


@pytest.fixture
def estimation_ok(monkeypatch):
    """Mock at the HTTP boundary (_call_worker) so the REAL provider
    validation (_validate_worker_response) runs inside every API test —
    the mock only removes the network, never the contract checks."""
    async def fake_call(self, data_url, sex, height_cm=None):  # noqa: ARG001
        return _worker_envelope(_worker_ok())
    monkeypatch.setattr(AnthropometryProvider, "_call_worker", fake_call)


@pytest.fixture
def estimation_full(monkeypatch):
    async def fake_call(self, data_url, sex, height_cm=None):  # noqa: ARG001
        body = _worker_ok("full")
        body["scale_calibration"] = {
            "applied": height_cm is not None,
            "source": "user_reported_height" if height_cm is not None else "mediapipe_monocular_scale",
            "factor": 1.1643 if height_cm is not None else 1.0,
            "reported_height_cm": height_cm,
        }
        return _worker_envelope(body)
    monkeypatch.setattr(AnthropometryProvider, "_call_worker", fake_call)


@pytest.fixture
def estimation_refused(monkeypatch):
    async def fake_call(self, data_url, sex, height_cm=None):  # noqa: ARG001
        return {
            "estimation_available": False,
            "reason": "worker_refused:POSE_OUT_OF_ENVELOPE",
            "guidance": "body turned 40° from the camera — please face the camera directly",
            "job_id": "anthro_x",
        }
    monkeypatch.setattr(AnthropometryProvider, "_call_worker", fake_call)


@pytest.fixture
def estimation_timeout(monkeypatch):
    async def fake_call(self, data_url, sex, height_cm=None):  # noqa: ARG001
        return {"estimation_available": False, "reason": "anthropometry_worker_timeout",
                "guidance": "The measurement took too long. Please try again."}
    monkeypatch.setattr(AnthropometryProvider, "_call_worker", fake_call)


def _register(client: TestClient, label: str) -> dict:
    import uuid
    email = f"anthro_{label}_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": f"Anthro {label}",
    })
    assert res.status_code == 201, res.text
    return {**{"Authorization": f"Bearer {res.json()['access_token']}"},
            "X-Session-Token": f"guest-{label}-{uuid.uuid4().hex[:8]}"}


def _create_session(client: TestClient, headers: dict, consent: bool = True) -> int:
    res = client.post("/api/v1/measurements/sessions", headers=headers,
                      json={"capture_mode": "server_side", "consent_granted": consent})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _post_estimate(client: TestClient, headers: dict, session_id: int,
                   sex: str = "male", height_cm: float | None = 176.0):
    data = {"file": ("body.jpg", _jpg_bytes(), "image/jpeg"),
            "sex": (None, sex)}
    if height_cm is not None:
        data["height_cm"] = (None, str(height_cm))
    return client.post(
        f"/api/v1/measurements/sessions/{session_id}/photo-estimate",
        headers=headers, files=data)


# ───────────────────────── API contract ─────────────────────────

def test_photo_estimate_happy_path_persists_honest_mapping(
        client, broker_down, worker_env, estimation_ok):
    headers = _register(client, "ida")
    sid = _create_session(client, headers)
    res = _post_estimate(client, headers, sid)
    assert res.status_code == 200, res.text
    body = res.json()

    # Mandatory disclosures pass through verbatim.
    assert body["accuracy_note"] == "±2-3 cm"
    assert "±2-3 cm" in body["disclaimer"]
    assert body["landmark_source"] == "mediapipe_pose_world_approx"
    assert body["model"]["license"] == "unlicensed-research-only"
    assert body["model"]["commercial"] is False
    assert body["quality"] == "partial"

    # Height prefers the direct-geometry stature (anchored to the reported
    # height), NOT the model's lower estimate.
    stored = body["stored_measurements"]
    assert stored["height_cm"] == pytest.approx(176.0)
    assert stored["chest_cm"] == pytest.approx(77.5)
    assert stored["inseam_cm"] == pytest.approx(88.9)
    # The worker did not estimate shoulder/waist -> NULL, never a default.
    assert stored["shoulder_width_cm"] is None
    assert stored["waist_cm"] is None
    # Hip was excluded by the worker (implausible) -> not persisted.
    assert stored["hip_cm"] is None

    assert body["source"] == "ai_photo_estimate"
    assert body["confidence_score"] == 60  # quality-derived, not fabricated 95
    assert body["result_id"] > 0
    assert [e["reason"] for e in body["excluded"]] == ["outside_anatomical_range"] * 2

    # The session completed and the result row is real.
    with TestingSessionLocal() as db:
        row = db.execute(
            text("SELECT height_cm, chest_cm, hip_cm, source, confidence_score, "
                 "calibration_reference_used FROM measurement_results "
                 "WHERE id = :i"), {"i": body["result_id"]}).mappings().one()
        assert dict(row) == {
            "height_cm": pytest.approx(176.0), "chest_cm": pytest.approx(77.5),
            "hip_cm": None, "source": "ai_photo_estimate",
            "confidence_score": 60,
            "calibration_reference_used": "user_reported_height",
        }
        sess = db.execute(text("SELECT status, capture_mode FROM measurement_sessions "
                               "WHERE id = :i"), {"i": sid}).mappings().one()
        assert dict(sess) == {"status": "completed", "capture_mode": "server_side"}


def test_photo_estimate_full_quality_maps_hip_and_confidence(
        client, broker_down, worker_env, estimation_full):
    headers = _register(client, "ful")
    sid = _create_session(client, headers)
    res = _post_estimate(client, headers, sid, sex="female", height_cm=None)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["quality"] == "full"
    assert body["confidence_score"] == 75
    assert body["stored_measurements"]["hip_cm"] == pytest.approx(93.3)
    # Without a height hint the calibration source is the monocular scale.
    assert body["scale_calibration"]["applied"] is False
    with TestingSessionLocal() as db:
        row = db.execute(text("SELECT calibration_reference_used FROM measurement_results "
                              "WHERE id = :i"), {"i": body["result_id"]}).scalar()
        assert row == "mediapipe_monocular_scale"


def test_worker_refusal_is_422_with_guidance_and_marks_session_failed(
        client, broker_down, worker_env, estimation_refused):
    headers = _register(client, "ref")
    sid = _create_session(client, headers)
    res = _post_estimate(client, headers, sid)
    assert res.status_code == 422, res.text
    err = res.json()["detail"]["error"]
    assert err["code"] == "POSE_OUT_OF_ENVELOPE"
    assert "face the camera" in err["message"]
    with TestingSessionLocal() as db:
        status = db.execute(text("SELECT status FROM measurement_sessions WHERE id=:i"),
                            {"i": sid}).scalar()
        assert status == "failed"
        count = db.execute(text("SELECT COUNT(*) FROM measurement_results WHERE session_id=:i"),
                           {"i": sid}).scalar()
        assert count == 0  # nothing persisted on refusal


def test_worker_unavailable_is_503_retryable_no_rows(
        client, broker_down, worker_env, estimation_timeout):
    headers = _register(client, "tmo")
    sid = _create_session(client, headers)
    res = _post_estimate(client, headers, sid)
    assert res.status_code == 503, res.text
    assert res.json()["detail"]["error"]["code"] == "ANTHROPOMETRY_UNAVAILABLE"
    with TestingSessionLocal() as db:
        status = db.execute(text("SELECT status FROM measurement_sessions WHERE id=:i"),
                            {"i": sid}).scalar()
        assert status == "created"  # retryable
        count = db.execute(text("SELECT COUNT(*) FROM measurement_results WHERE session_id=:i"),
                           {"i": sid}).scalar()
        assert count == 0


def test_missing_consent_is_403_even_with_valid_photo(
        client, broker_down, worker_env, estimation_ok):
    headers = _register(client, "con")
    sid = _create_session(client, headers, consent=False)
    res = _post_estimate(client, headers, sid)
    assert res.status_code == 403, res.text
    assert res.json()["detail"]["error"]["code"] == "MEASUREMENT_CONSENT_MISSING"


def test_foreign_session_is_404_and_guest_flow_works(
        client, broker_down, worker_env, estimation_ok):
    owner = _register(client, "own")
    sid = _create_session(client, owner)
    stranger = _register(client, "str")
    res = _post_estimate(client, stranger, sid)
    assert res.status_code == 404, res.text

    # Guest flow: fresh client (no auth cookies -> CSRF not engaged), the
    # app-wide X-Session-Token header IS the identity.
    from backend.app.main import app as main_app
    guest_client = TestClient(main_app)
    guest_headers = {"X-Session-Token": "guest-token-abc"}
    res = guest_client.post("/api/v1/measurements/sessions", headers=guest_headers,
                            json={"capture_mode": "server_side", "consent_granted": True})
    assert res.status_code == 201, res.text
    gsid = res.json()["id"]
    res = _post_estimate(guest_client, guest_headers, gsid)
    assert res.status_code == 200, res.text
    # ...and a different token cannot touch it.
    res = _post_estimate(guest_client, {"X-Session-Token": "guest-token-other"}, gsid)
    assert res.status_code == 404, res.text


@pytest.mark.parametrize("bad_call", [
    {"sex": "other", "height": 176.0},
    {"sex": "male", "height": 400.0},
])
def test_input_validation(client, broker_down, worker_env, estimation_ok, bad_call):
    headers = _register(client, "val")
    sid = _create_session(client, headers)
    res = _post_estimate(client, headers, sid, sex=bad_call["sex"], height_cm=bad_call["height"])
    assert res.status_code == 422, res.text


def test_unsupported_mime_rejected_before_worker(
        client, broker_down, worker_env, estimation_ok):
    headers = _register(client, "mim")
    sid = _create_session(client, headers)
    res = client.post(
        f"/api/v1/measurements/sessions/{sid}/photo-estimate",
        headers=headers,
        files={"file": ("body.gif", b"GIF89a", "image/gif"), "sex": (None, "male")})
    assert res.status_code == 422, res.text


def test_unconfigured_worker_is_503_not_fake_success(client, broker_down):
    # No worker_env fixture: ANTHROPOMETRY_WORKER_URL unset in test settings.
    headers = _register(client, "unc")
    sid = _create_session(client, headers)
    res = _post_estimate(client, headers, sid)
    assert res.status_code == 503, res.text
    assert res.json()["detail"]["error"]["code"] == "ANTHROPOMETRY_UNAVAILABLE"


# ───────────────────────── provider unit tests ─────────────────────────

def test_validate_accepts_real_worker_body():
    body, problem = _validate_worker_response(_worker_ok())
    assert problem is None


def test_validate_rejects_missing_disclosures():
    for mutate in (
        lambda b: b.pop("accuracy_note"),
        lambda b: b.pop("disclaimer"),
        lambda b: b.update(quality="excellent"),
        lambda b: b.update(measurement_method="precise_scan"),
        lambda b: b["model"].update(commercial=True),
        lambda b: b["measurements"][0].update(source="tape_measure"),
        lambda b: b.update(measurements=[]),
    ):
        body = _worker_ok()
        mutate(body)
        _, problem = _validate_worker_response(body)
        assert problem, body


def test_provider_not_configured_is_honest():
    import asyncio
    from unittest.mock import patch
    provider = AnthropometryProvider()
    with patch.object(config_mod.settings, "ANTHROPOMETRY_WORKER_URL", None):
        result = asyncio.run(provider.estimate_from_photo("data:image/jpeg;base64,AA", "male"))
    assert result["estimation_available"] is False
    assert result["reason"] == "anthropometry_not_configured"


def test_provider_maps_http_errors_to_honest_envelopes(worker_env):
    """Mock ONLY the HTTP layer (AsyncClient.post) so the provider's real
    error-mapping code runs — the service tests above remove the whole
    _call_worker; this pins the boundary itself."""
    import asyncio

    def run(status_code: int, payload: dict | None = None):
        provider = AnthropometryProvider()

        class FakeResp:
            def __init__(self):
                self.status_code = status_code
                self.text = json.dumps(payload or {})
            def json(self):
                if payload is None:
                    raise ValueError("no json")
                return payload

        class FakeClient:
            def __init__(self, timeout=None):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False
            async def post(self, url, headers=None, json=None):
                return FakeResp()

        async def call():
            with patch.object(httpx, "AsyncClient", FakeClient):
                return await provider._call_worker("data:image/jpeg;base64,AA", "male", None)

        return asyncio.run(call())

    refused = run(422, {"detail": {"error": {"code": "POSE_OUT_OF_ENVELOPE",
                                             "message": "please face the camera"}}})
    assert refused["reason"] == "worker_refused:POSE_OUT_OF_ENVELOPE"
    assert refused["guidance"] == "please face the camera"

    auth = run(401)
    assert auth["reason"] == "anthropometry_worker_auth_failure"

    infra = run(500)
    assert infra["reason"] == "anthropometry_worker_infra_error"

    badjson = run(200)
    assert badjson["reason"] == "anthropometry_worker_invalid_response"

    ok = run(200, _worker_ok())
    assert ok["status"] == "completed"
    assert "backend_call_seconds" in ok


def test_provider_sends_dedicated_token_and_height(worker_env):
    import asyncio
    captured = {}

    class FakeResp:
        status_code = 200
        text = "{}"
        def json(self):
            return _worker_ok()

    class FakeClient:
        def __init__(self, timeout=None):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None):
            captured.update(url=url, headers=headers, payload=json)
            return FakeResp()

    async def call():
        provider = AnthropometryProvider()
        with patch.object(httpx, "AsyncClient", FakeClient):
            return await provider._call_worker("data:image/jpeg;base64,AA", "female", 168.0)

    result = asyncio.run(call())
    assert result["status"] == "completed"
    assert captured["url"] == "https://anthro-worker.test/estimate"
    assert captured["headers"]["X-VTON-Admin"] == "test-admin-token"
    assert captured["payload"]["sex"] == "female"
    assert captured["payload"]["height_cm"] == 168.0
    assert captured["payload"]["job_id"].startswith("anthro_")


# keep the unused-import linters honest

