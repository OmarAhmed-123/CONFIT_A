"""Sequential-chain capability adaptation — zero-GPU tests.

THE PRODUCTION SITUATION THIS PINS
----------------------------------
The deployed production worker (fashn_vton_segfee) is SINGLE-CATEGORY: it
rejects >1 garment per /process call with HTTP 422 at the pydantic gate,
BEFORE any GPU time is spent. The backend adapts honestly:

  * the whole-outfit call is attempted FIRST (the fashn_v15 contract — a
    multi-garment-capable worker serves it in one call and the chain never
    runs);
  * on the single-garment 422 signature specifically, the outfit renders as
    a SEQUENTIAL CHAIN — one call per layer, layer i+1 rendering on layer
    i's verified output (the same chain the animated path uses per
    keyframe);
  * every other 422 (unsupported slot, bad image, ...) is a real input
    error and fails honestly — the chain is a TRANSPORT adaptation, never
    a quality fallback;
  * a chain layer whose verify.PASS is not True aborts with the canonical
    VTON_LAYER_NOT_APPLIED — a partial outfit is never a success.

All tests run the REAL ``_call_gpu_worker`` gate through a fake
``httpx.AsyncClient`` that mimics the deployed worker's exact 422 body.
Zero GPU, no network, sqlite test DB only.
"""
from __future__ import annotations

import base64
import io
import random
import uuid

import pytest
from PIL import Image

UNIQUE = uuid.uuid4().hex[:8]

# The deployed worker's EXACT rejection body (fashn_vton_segfee, pydantic
# value_error on garments) — pinned so the adaptation's signature match
# stays aligned with production reality.
SINGLE_GARMENT_422 = (
    "fashn_vton_segfee is single-category; max 1 garment per job (got 2)"
)


def _person_png_data_url() -> str:
    rng = random.Random(20261003)
    w, h = 300, 512
    img = Image.new("RGB", (w, h), color=(120, 110, 100))
    px = img.load()
    for _ in range(4000):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = (rng.randrange(90, 160), rng.randrange(80, 150), rng.randrange(70, 140))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _render_png_data_url(n: int) -> str:
    img = Image.new("RGB", (300, 512), color=(40 * n % 250, 60, 80))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class _FakeResp:
    def __init__(self, code: int, payload):
        self.status_code = code
        self.text = str(payload)
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeSegfeeWorker:
    """Fake httpx.AsyncClient mimicking the deployed single-category worker.

    * GET readiness -> 200 {"ready": true, "engine": "fashn_vton_segfee"}
    * POST with >1 garment -> 422 with the production rejection text
    * POST with 1 garment -> 200 verified render (distinct image per call)

    Records every process payload (person + garments) and every rendered
    data URL so tests can assert the CHAIN semantics: layer k+1's person
    image must be exactly layer k's render.
    """

    mode = "single_garment"          # or "multi" (fashn_v15-style worker)
    pass_on_call: dict = {}          # {call_index: bool} override, default True
    calls: list = []                 # [{"person": str, "garments": list}]
    renders: list = []               # data URLs returned, in order

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _FakeResp(200, {"ready": True, "engine": "fashn_vton_segfee", "model_loaded": True})

    async def post(self, url=None, json=None, **k):
        idx = len(self.calls) + 1
        garments = (json or {}).get("garments", [])
        self.calls.append({
            "person": (json or {}).get("user_image_base64_or_url"),
            "garments": garments,
            "job_id": (json or {}).get("job_id"),
        })
        if len(garments) > 1 and self.mode == "single_garment":
            # The deployed worker's pydantic gate — BEFORE any GPU work.
            return _FakeResp(422, {"detail": [{
                "type": "value_error", "loc": ["body", "garments"],
                "msg": f"Value error, fashn_vton_segfee is single-category; "
                       f"max 1 garment per job (got {len(garments)})",
            }]})
        passed = self.pass_on_call.get(idx, True)
        data_url = _render_png_data_url(idx)
        self.renders.append(data_url)
        return _FakeResp(200, {
            "rendered_image_data_url": data_url,
            "model_used": "fashn-vton-v1.5 (fashn_vton_segfee, segmentation-free; fork 7c0f10af)",
            "fit_verdict": "n/a",
            "engine": "fashn_vton_segfee",
            "layers_processed": 1,
            "execution_time_ms": 1234,
            "verify": {
                "PASS": passed,
                "metric_pixel_change": 40.0 if passed else 0.2,
                "metric_color_shift": 0.05 if passed else 0.001,
                "metric_image_stddev": 40.0 if passed else 3.0,
            },
        })


@pytest.fixture
def segfee_worker(monkeypatch):
    _FakeSegfeeWorker.calls = []
    _FakeSegfeeWorker.renders = []
    _FakeSegfeeWorker.pass_on_call = {}
    _FakeSegfeeWorker.mode = "single_garment"
    monkeypatch.setenv("VTON_WORKER_URL", "https://worker.invalid/process")
    monkeypatch.setattr("httpx.AsyncClient", _FakeSegfeeWorker)
    return _FakeSegfeeWorker


# ============================================================ sync multi-render
class TestSyncMultiRenderChain:
    def test_two_garments_chain_on_single_category_worker(self, client, segfee_worker):
        """2 garments on the deployed single-category worker: the outfit
        still renders, as an honest sequential chain."""
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1, 3],
            "user_image_base64": _person_png_data_url(),
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "completed"
        assert body["composition_mode"] == "sequential_chain"
        assert (body.get("verification") or {}).get("all_layers_verified") is True
        # 3 process POSTs: 1 rejected whole-outfit call + 2 chained layers.
        assert len(segfee_worker.calls) == 3, [c["job_id"] for c in segfee_worker.calls]
        # The rejected first call carried BOTH garments.
        assert len(segfee_worker.calls[0]["garments"]) == 2
        # Each chained call carried exactly ONE garment.
        assert all(len(c["garments"]) == 1 for c in segfee_worker.calls[1:])
        # CHAIN SEMANTICS: layer 2's person image IS layer 1's render.
        assert segfee_worker.calls[2]["person"] == segfee_worker.renders[0]
        # Honest disclosure names the REAL engine, not a hardcoded brand.
        assert "CatVTON" not in body["ai_disclosure"]
        assert "fashn" in body["ai_disclosure"].lower()

    def test_single_garment_never_triggers_chain(self, client, segfee_worker):
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1],
            "user_image_base64": _person_png_data_url(),
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "completed"
        assert body["composition_mode"] == "single_call"
        assert len(segfee_worker.calls) == 1

    def test_multi_capable_worker_takes_one_call(self, client, segfee_worker):
        segfee_worker.mode = "multi"  # fashn_v15-style: whole outfit in one call
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1, 3],
            "user_image_base64": _person_png_data_url(),
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "completed"
        assert body["composition_mode"] == "single_call"
        # Exactly ONE process POST — the whole outfit, no chain.
        assert len(segfee_worker.calls) == 1
        assert len(segfee_worker.calls[0]["garments"]) == 2

    def test_unrelated_422_fails_honestly_without_chain(self, client, segfee_worker):
        """A 422 that is NOT the single-garment signature (unsupported slot,
        bad image, ...) is a real input error: no chain, no second call."""
        # Rewire the fake to reject with an unrelated reason.
        class _Unrelated(_FakeSegfeeWorker):
            async def post(self, url=None, json=None, **k):
                garments = (json or {}).get("garments", [])
                self.calls.append({"person": (json or {}).get("user_image_base64_or_url"), "garments": garments})
                if len(garments) > 1:
                    return _FakeResp(422, {"detail": [{
                        "msg": "Value error, fashn_vton_segfee does not support "
                               "slot_type/category 'footwear': only tops/bottoms/one-pieces.",
                    }]})
                return await super().post(url=url, json=json, **k)

        _Unrelated.calls = []
        _Unrelated.renders = []
        _Unrelated.pass_on_call = {}
        _Unrelated.mode = "single_garment"
        import httpx as _httpx
        original = _httpx.AsyncClient
        _httpx.AsyncClient = _Unrelated
        try:
            res = client.post("/api/v1/try-on/multi-render", json={
                "product_ids": [1, 3],
                "user_image_base64": _person_png_data_url(),
            })
        finally:
            _httpx.AsyncClient = original
        assert res.status_code >= 400
        assert "VTON_INPUT_INVALID" in res.text
        # NO sequential adaptation: exactly one (rejected) worker call.
        assert len(_Unrelated.calls) == 1

    def test_unverified_chain_layer_aborts_honestly(self, client, segfee_worker):
        """Layer 2 not verified as applied -> canonical VTON_LAYER_NOT_APPLIED,
        never a partial-outfit success."""
        # pass_on_call indexes POST CALLS, and the rejected whole-outfit
        # call consumes index 1 (it 422s before rendering). So chain layer
        # 1 renders on call index 2 and chain layer 2 on call index 3.
        segfee_worker.pass_on_call = {3: False}
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1, 3],
            "user_image_base64": _person_png_data_url(),
        })
        assert res.status_code == 502, res.text
        assert "VTON_LAYER_NOT_APPLIED" in res.text
        # The chain ran: 1 rejected + 2 layers (the second one unverified —
        # the canonical gate inside _call_gpu_worker aborts on its PASS=False).
        assert len(segfee_worker.calls) == 3


# ================================================================ async job path
class TestAsyncJobChain:
    def _auth(self, tok):
        return {"Authorization": f"Bearer {tok}"}

    def _register(self, client: object, email: str) -> dict:
        res = client.post("/api/v1/auth/register", json={
            "email": email, "password": "Passw0rd!ForTests123", "full_name": "Chain Test",
        })
        assert res.status_code in (200, 201), res.text
        return res.json()

    def test_job_completes_via_chain_with_metrics(self, client, segfee_worker):
        creds = self._register(client, "chain_a_" + UNIQUE + "@test.dev")
        res = client.post("/api/v1/try-on/jobs", json={
            "product_ids": [1, 3],
            "user_image_base64": _person_png_data_url(),
            "avatar_model_id": "avatar_athletic_m",
            "gender_mode": "male",
            "output_aspect": "9:16",
            "consent_retain_photo": False,
        }, headers=self._auth(creds["access_token"]))
        assert res.status_code == 202, res.text
        out = res.json()
        assert out["status"] == "completed", out
        assert (out.get("result_image_data_url") or "").startswith("data:image/png")
        # Chain ran: 1 rejected whole-outfit call + 2 single-garment layers.
        assert len(segfee_worker.calls) == 3
        assert len(segfee_worker.calls[0]["garments"]) == 2
        assert segfee_worker.calls[2]["person"] == segfee_worker.renders[0]

    def test_job_fails_honestly_when_layer_unverified(self, client, segfee_worker):
        # Chain layer 1 renders on POST index 2 (index 1 = rejected multi call).
        segfee_worker.pass_on_call = {2: False}
        creds = self._register(client, "chain_b_" + UNIQUE + "@test.dev")
        res = client.post("/api/v1/try-on/jobs", json={
            "product_ids": [1, 3],
            "user_image_base64": _person_png_data_url(),
            "avatar_model_id": "avatar_athletic_m",
            "gender_mode": "male",
            "output_aspect": "9:16",
            "consent_retain_photo": False,
        }, headers=self._auth(creds["access_token"]))
        assert res.status_code == 202, res.text
        out = res.json()
        assert out["status"] == "failed", out
        assert out["error_code"] == "VTON_LAYER_NOT_APPLIED", out
        assert out.get("result_image_data_url") is None
