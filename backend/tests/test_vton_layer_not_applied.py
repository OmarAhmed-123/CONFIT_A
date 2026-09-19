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

S31 sleeve-integrity note (2026-09-16): production now also runs a per-layer
sleeve gate on garments declared ``sleeve_length='long'`` (the seeded blazer /
tuxedo / oxford are all declared long-sleeve). A faithful fake worker must
therefore emulate a FAITHFULLY APPLIED garment: the "verified" render carries
the garment's dominant color on the torso + forearm bands (what a correctly
rendered long-sleeve garment looks like to the S31 differential probe), and
the person fixture is a skin-toned image (bare forearms — the calibrated
negative-control geometry). Garment thumbnails are served by the fake as
synthetic flat-lays (white background + chromatic block) so the tests stay
hermetic (no network) and each garment's reference color is well separated
from skin and from the other garments' colors (avoids the documented
same-family-color over-refusal of the differential probe when layers chain).
"""
from __future__ import annotations

import base64
import io
import math
import random
import uuid

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.app.services.tryon_service import (
    assert_layer_applied,
    aggregate_layer_verification,
)
from backend.app.services.vton_sleeve_gate import garment_dominant_lab, _rgb_to_lab

UNIQUE = uuid.uuid4().hex[:8]

# Synthetic flat-lay colors (well separated in Lab — pairwise > ΔE 40 and
# > ΔE 40 from the skin tone below — so the differential sleeve probe never
# sees a same-family-color contamination between chained layers).
GARMENT_URL_COLORS = {
    "photo-1594938298603": (27, 31, 59),    # blazer (p1) — navy
    "photo-1507679799987": (30, 80, 180),   # tuxedo (p2) — bright blue
    "photo-1602810318383": (180, 40, 40),   # oxford (p3) — bright red
}
DEFAULT_GARMENT_COLOR = (60, 60, 60)        # other seed thumbnails (lower/none slots)

# Skin tone for the person fixture (warm mid skin; > ΔE 40 from every
# garment color above — the bare-forearm negative control).
SKIN = (210, 170, 140)

# Normalized render regions: torso + the two calibrated forearm bands (the
# same boxes the production S31 probe samples).
_TORSO = (0.28, 0.72, 0.28, 0.56)
_FOREARMS = ((0.52, 0.70, 0.40, 0.55), (0.28, 0.46, 0.40, 0.55))


def _paint_region(img: Image.Image, box, color) -> None:
    px = img.load()
    w, h = img.size
    x0, x1, y0, y1 = box
    for y in range(int(y0 * h), int(y1 * h)):
        for x in range(int(x0 * w), int(x1 * w)):
            px[x, y] = color


def _flat_lay_bytes(url: str) -> bytes:
    """Synthetic garment flat-lay: white studio background + chromatic block
    (``garment_dominant_lab`` skips min(rgb)>235, so it lands exactly on the
    block color). Deterministic per URL fragment."""
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


def _dominant_lab_from_flat_lay(data_url: str | None):
    """Measure the garment reference color the SAME way production does
    (garment_dominant_lab on the flat-lay), so the fake render's painted
    color and the differential probe's reference agree by construction."""
    if not data_url or not data_url.startswith("data:"):
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
        lab = garment_dominant_lab(Image.open(io.BytesIO(raw)).convert("RGB"))
        return lab if lab != (0.0, 0.0, 0.0) else None
    except Exception:  # noqa: BLE001
        return None


def _person_png_data_url() -> str:
    """Pose-plausible SKIN-TONED person fixture (short side >= 256px, > 10KB,
    seeded). The forearm bands are bare skin — the calibrated negative
    control for the S31 differential sleeve probe."""
    rng = random.Random(20260905)
    w, h = 300, 512
    img = Image.new("RGB", (w, h), color=SKIN)
    px = img.load()
    for _ in range(4000):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = (
            min(255, max(0, SKIN[0] + rng.randrange(-15, 16))),
            min(255, max(0, SKIN[1] + rng.randrange(-15, 16))),
            min(255, max(0, SKIN[2] + rng.randrange(-15, 16))),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _result_png_data_url() -> str:
    img = Image.new("RGB", (300, 512), color=(180, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class _FakeResp:
    def __init__(self, code: int, payload: dict | None = None, content: bytes = b""):
        self.status_code = code
        self.text = ""
        self.content = content
        self._payload = payload or {}
        self.headers = {"content-type": "image/jpeg"}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Fake httpx.AsyncClient: readiness OK, garment flat-lays, and a process
    response whose PASS is configurable.

    Returns a DISTINCT image per layer (so a layer's output differs from its
    input — the pre-existing echo guard stays quiet). A "verified" render is
    a faithful applied garment: the torso + forearm bands carry the garment's
    dominant color (what a correctly rendered long-sleeve garment looks like
    to the S31 differential probe). A "not applied" render is a plain
    garment-color-free image, and verify.PASS=False drives the failure.
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
        url = str(a[0]) if a else ""
        if "images.unsplash.com" in url:
            return _FakeResp(200, content=_flat_lay_bytes(url))
        return _FakeResp(200, payload={"ready": True})

    async def post(self, *a, **k):
        _FakeAsyncClient._call_count += 1
        n = _FakeAsyncClient._call_count
        unapplied = not _FakeAsyncClient.pass_value
        if unapplied:
            # A not-applied layer: output is ~identical to input (low change),
            # garment-color-free. Distinct-per-call base still avoids a
            # byte-identical echo, but the worker's own verify gate
            # (PASS=False) is what drives the failure.
            base_color = (120, 110, 100)
            garment_lab = None
        else:
            base_color = (50 * n, 60, 80)
            payload = k.get("json") or {}
            garments = payload.get("garments") or [{}]
            garment_lab = _dominant_lab_from_flat_lay((garments[0] or {}).get("image_base64"))
        img = Image.new("RGB", (300, 512), color=base_color)
        if garment_lab is not None:
            # A correctly applied long-sleeve garment: torso + forearms
            # garment-colored — the S31 probe's "new garment color" signal.
            # The flat-lay block is a flat RGB, so painting with the block
            # color makes the probe's ΔE against its own measured reference
            # ~0 (within JPEG/median rounding, far inside the ΔE 40 radius).
            color = _lab_closest_flat(garment_lab)
            _paint_region(img, _TORSO, color)
            for box in _FOREARMS:
                _paint_region(img, box, color)
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


def _lab_closest_flat(lab) -> tuple:
    """The fake flat-lay colors are known; return the block color whose
    production-measured Lab is closest to ``lab`` (inverse of the median
    measurement, without a Lab->RGB solver)."""
    candidates = list(GARMENT_URL_COLORS.values()) + [DEFAULT_GARMENT_COLOR]
    best, best_d = None, None
    for c in candidates:
        d = math.sqrt(sum((x - y) ** 2 for x, y in zip(_rgb_to_lab(c), lab)))
        if best_d is None or d < best_d:
            best, best_d = c, d
    return best


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
