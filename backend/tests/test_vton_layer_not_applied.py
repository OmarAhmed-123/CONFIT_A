"""Hard-fail on unverified VTON layers — zero-GPU tests.

Canonical invariant (``assert_layer_applied``, invoked from ``_call_gpu_worker``):
a garment layer is valid ONLY when the engine's ``verify.PASS`` is exactly True.
ANY layer with ``verify_pass != True`` => the request is FAILED with the single
canonical code ``VTON_LAYER_NOT_APPLIED`` — never a completed/partial success,
never a partial image exposed as a result.

The e2e tests run the REAL ``_call_gpu_worker`` gate (via a fake
``httpx.AsyncClient`` that returns a ``PASS=False`` process response) — NOT a
mocked ``_call_gpu_worker`` — so the failure-handling code path in the real
production source is exercised. Zero GPU, no worker, sqlite test DB only.
"""
from __future__ import annotations

import base64
import io
import random
import uuid

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.app.services.tryon_service import (
    assert_layer_applied,
    aggregate_layer_verification,
)

UNIQUE = uuid.uuid4().hex[:8]


def _person_png_data_url() -> str:
    """Pose-plausible person fixture (short side >= 256px, > 10KB, seeded)."""
    rng = random.Random(20260905)
    w, h = 300, 512
    img = Image.new("RGB", (w, h), color=(120, 110, 100))
    px = img.load()
    for _ in range(4000):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = (rng.randrange(90, 160), rng.randrange(80, 150), rng.randrange(70, 140))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _result_png_data_url() -> str:
    img = Image.new("RGB", (300, 512), color=(180, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class _FakeResp:
    def __init__(self, code: int, payload: dict):
        self.status_code = code
        self.text = ""
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Fake httpx.AsyncClient: readiness OK, process returns a configurable PASS.

    Returns a DISTINCT image per layer (so a layer's output differs from its
    input — the pre-existing echo guard stays quiet), mimicking a real worker
    where each applied garment changes the image.
    """
    pass_value = True
    _call_count = 0

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _FakeResp(200, {"ready": True})

    async def post(self, *a, **k):
        _FakeAsyncClient._call_count += 1
        n = _FakeAsyncClient._call_count
        unapplied = not _FakeAsyncClient.pass_value
        if unapplied:
            # A not-applied layer: output is ~identical to input (low change).
            # Distinct-per-call base still avoids a byte-identical echo, but the
            # worker's own verify gate (PASS=False) is what drives the failure.
            color = (120, 110, 100)
        else:
            color = (50 * n, 60, 80)
        img = Image.new("RGB", (300, 512), color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        return _FakeResp(200, {
            "rendered_image_data_url": data_url,
            "model_used": "test-model (http-mocked)",
            "fit_verdict": "n/a",
            "layers_processed": 1,
            "execution_time_ms": 42,
            "verify": {
                "PASS": _FakeAsyncClient.pass_value,
                "metric_pixel_change": 0.2 if unapplied else 40.0,
                "metric_color_shift": 0.001 if unapplied else 0.05,
                "metric_image_stddev": 3.0 if unapplied else 40.0,
            },
        })


@pytest.fixture
def fake_http_worker(monkeypatch):
    _FakeAsyncClient._call_count = 0
    monkeypatch.setenv("VTON_WORKER_URL", "https://worker.invalid/process")
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _register(client: TestClient, email: str, password: str = "Passw0rd!ForTests123") -> dict:
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "full_name": "Layer-Fail Test",
    })
    assert res.status_code in (200, 201), res.text
    return res.json()


# ===================================================================== unit: gate
class TestAssertLayerApplied:
    def test_pass_true_no_raise(self):
        assert_layer_applied({"PASS": True, "metric_pixel_change": 40.0}, "job_l1")  # no raise

    def test_pass_false_raises_canonical_code(self):
        with pytest.raises(RuntimeError) as ei:
            assert_layer_applied(
                {"PASS": False, "metric_pixel_change": 0.2,
                 "metric_color_shift": 0.001, "metric_image_stddev": 3.0}, "job_l2")
        msg = str(ei.value)
        assert "VTON_LAYER_NOT_APPLIED" in msg
        assert "job_l2" in msg

    def test_pass_none_raises(self):
        with pytest.raises(RuntimeError) as ei:
            assert_layer_applied({"PASS": None}, "job_x")
        assert "VTON_LAYER_NOT_APPLIED" in str(ei.value)

    def test_missing_verify_raises(self):
        with pytest.raises(RuntimeError) as ei:
            assert_layer_applied({}, "job_y")
        assert "VTON_LAYER_NOT_APPLIED" in str(ei.value)

    def test_single_canonical_code_no_competing_codes(self):
        # The exact same semantic failure must map to ONE canonical code.
        for verify in ({"PASS": False}, {"PASS": None}, {}):
            with pytest.raises(RuntimeError) as ei:
                assert_layer_applied(verify, "job")
            assert str(ei.value).startswith("VTON_LAYER_NOT_APPLIED:")


# ============================================================= unit: aggregation
class TestAggregateStillConsistent:
    def test_all_verified(self):
        agg = aggregate_layer_verification([
            {"verify_pass": True}, {"verify_pass": True},
        ])
        assert agg["all_layers_verified"] is True

    def test_any_unverified(self):
        agg = aggregate_layer_verification([
            {"verify_pass": True}, {"verify_pass": False},
        ])
        assert agg["all_layers_verified"] is False
        assert agg["layers_failed"] == 1


# ===================================================== e2e: async job (real gate)
class TestAsyncHardFail:
    def test_unverified_layer_fails_job_truthfully(self, client, fake_http_worker):
        _FakeAsyncClient.pass_value = False  # engine did NOT apply the garment
        creds = _register(client, "lfa_a_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        res = client.post("/api/v1/try-on/jobs", json={
            "product_ids": [1],
            "user_image_base64": _person_png_data_url(),
            "avatar_model_id": "avatar_athletic_m",
            "gender_mode": "male",
            "output_aspect": "9:16",
            "consent_retain_photo": False,
        }, headers=_auth(tok))
        assert res.status_code == 202, res.text
        out = res.json()
        assert out["status"] == "failed", out
        assert out["error_code"] == "VTON_LAYER_NOT_APPLIED", out
        # No partial/unverified image is exposed as a success result.
        assert out.get("result_image_data_url") is None
        assert "VTON_LAYER_NOT_APPLIED" in (out.get("error_message") or "")

    def test_verified_single_garment_still_completes(self, client, fake_http_worker):
        _FakeAsyncClient.pass_value = True  # engine applied + verified the garment
        creds = _register(client, "lfa_b_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        res = client.post("/api/v1/try-on/jobs", json={
            "product_ids": [1],
            "user_image_base64": _person_png_data_url(),
            "avatar_model_id": "avatar_athletic_m",
            "gender_mode": "male",
            "output_aspect": "9:16",
            "consent_retain_photo": False,
        }, headers=_auth(tok))
        assert res.status_code == 202, res.text
        out = res.json()
        assert out["status"] == "completed", out
        assert (out.get("result_image_data_url") or "").startswith("data:image/png")


# ============================================== e2e: sync multi-render (real gate)
class TestSyncHardFail:
    def test_unverified_layer_returns_502_not_success(self, client, fake_http_worker):
        _FakeAsyncClient.pass_value = False
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1, 3],
            "user_image_base64": _person_png_data_url(),
        })
        assert res.status_code == 502, res.text
        assert "VTON_LAYER_NOT_APPLIED" in res.text

    def test_verified_outfit_still_succeeds(self, client, fake_http_worker):
        _FakeAsyncClient.pass_value = True  # every layer verified
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1, 3],
            "user_image_base64": _person_png_data_url(),
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "completed"
        # A completed result is by construction fully verified.
        assert (body.get("verification") or {}).get("all_layers_verified") is True
