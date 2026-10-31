"""A framing refusal must reach the customer AS a framing refusal.

The worker now refuses a non-full-body upload with HTTP 422 and
``VTON_PERSON_FRAMING_INVALID`` before spending GPU. That is only honest end to
end if the backend keeps the code instead of re-labelling it:

    worker 422  ->  backend taxonomy  ->  job.error_code  ->  UI copy

Before this, the mapping chain in ``tryon_service`` had no branch for the code,
so it fell through to ``GPU_WORKER_ERROR`` — which tells the shopper the GPU
broke, when in fact their photo was a portrait. It also loses the guided hint,
so the one thing the customer could do about it (upload a full-body photo) is
never shown.

Zero GPU: a fake httpx client stands in for the worker, so the real mapping code
in the production source is what gets exercised.
"""
from __future__ import annotations

import base64
import io
import random
import uuid

import pytest
from PIL import Image

UNIQUE = uuid.uuid4().hex[:8]

WORKER_MESSAGE = (
    "VTON_PERSON_FRAMING_INVALID: this photo does not show the whole body. "
    "A try-on needs a full-length photo — head to feet, standing, arms slightly "
    "away from your body. Please upload a full-body photo."
)


def _person_png_data_url() -> str:
    """Pose-plausible person fixture: textured so it clears the size floor.

    A flat grey fill compresses below the worker's minimum-bytes guard and the
    request is refused as INPUT_INVALID before the worker is ever consulted,
    which would make this test pass for the wrong reason.
    """
    rng = random.Random(20261025)
    w, h = 300, 512
    img = Image.new("RGB", (w, h), color=(120, 110, 100))
    px = img.load()
    for _ in range(6000):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self._payload}")


class _FramingRefusalClient:
    """Readiness OK; every process call returns the worker's framing refusal."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _FakeResp(200, {"ready": True})

    async def post(self, *a, **k):
        return _FakeResp(422, {
            "detail": {
                "error": {
                    "code": "VTON_PERSON_FRAMING_INVALID",
                    "message": WORKER_MESSAGE,
                    "evidence": {"lowest_region": "shoulders", "reason": "no_leg_keypoints"},
                    "diffusion_performed": False,
                }
            }
        })


@pytest.fixture
def framing_refusing_worker(monkeypatch):
    monkeypatch.setenv("VTON_WORKER_URL", "https://worker.invalid/process")
    monkeypatch.setattr("httpx.AsyncClient", _FramingRefusalClient)
    return _FramingRefusalClient


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _register(client, email: str, password: str = "Passw0rd!ForTests123") -> str:
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "full_name": "Framing Test",
    })
    assert res.status_code in (200, 201), res.text
    return res.json()["access_token"]


# ================================================================ unit: mapping
def test_the_mapping_keeps_the_framing_code():
    from backend.app.services.tryon_service import _map_worker_error_code

    assert _map_worker_error_code(WORKER_MESSAGE) == "VTON_PERSON_FRAMING_INVALID"


@pytest.mark.parametrize("text,expected", [
    ("VTON_LAYER_NOT_APPLIED: layer 1 not verified", "VTON_LAYER_NOT_APPLIED"),
    ("VTON_AUTH_FAILURE: 401", "VTON_AUTH_FAILURE"),
    ("VTON_WORKER_NOT_READY: loading", "VTON_WORKER_NOT_READY"),
    ("VTON_TIMEOUT: 90s", "VTON_TIMEOUT"),
    ("something else entirely", "GPU_WORKER_ERROR"),
])
def test_the_rest_of_the_taxonomy_is_unchanged(text, expected):
    """Regression: adding a branch must not re-label any existing failure."""
    from backend.app.services.tryon_service import _map_worker_error_code

    assert _map_worker_error_code(text) == expected


@pytest.mark.parametrize("text", [
    "VTON_PERSON_FRAMING_INVALID: ...",
    "VTON_INPUT_INVALID: person image too small",
    "VTON_GARMENT_ASSET_INVALID: bad asset",
])
def test_input_side_failures_are_never_reported_as_gpu_errors(text):
    """The customer can act on these; calling them GPU errors is a lie."""
    from backend.app.services.tryon_service import _map_worker_error_code

    assert _map_worker_error_code(text) != "GPU_WORKER_ERROR"


# ================================================================= e2e: the job
def test_a_portrait_upload_fails_with_the_framing_code_not_a_gpu_error(
    client, framing_refusing_worker
):
    tok = _register(client, "frame_" + UNIQUE + "@test.dev")
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
    assert out["error_code"] == "VTON_PERSON_FRAMING_INVALID", (
        "a framing refusal was re-labelled: the shopper is told the GPU broke "
        f"when their photo was the problem (got {out['error_code']!r})"
    )
    # The guided hint has to survive into the message the UI shows.
    message = out.get("error_message") or ""
    assert "full-body" in message.lower() or "full body" in message.lower(), message
    # And no image is handed back for a refused upload.
    assert out.get("result_image_data_url") is None
