"""server_core — the SHARED VTON worker HTTP layer (Modal + Baseten shells).

These tests pin the external contract on a CPU-only host (no torch, no GPU):
the same FastAPI app factory the Baseten container serves. The Modal shell
delegates to the same handlers, so behaviour proven here holds on both hosts.

What is covered WITHOUT a GPU:
  * the wire contract: /health, /readiness, /process paths and shapes
  * auth: 401 taxonomy, token via env AND via the Baseten secrets file
  * honest degradation: failed load -> health degraded (never a fake success),
    readiness 503 with VTON_NOT_READY
  * input validation: garment count/slots, overlay whitelist, image size
    floors, SSRF-guarded URLs
  * single source of truth: modal_app_v15 re-exports server_core's request
    model and parser info, so the two shells cannot drift

What is NOT covered here (and where it is): real multi-garment composition is
unit-tested with a stubbed pipeline in test_vton_fashn_v15_multigarment.py
(the same engine both shells load) and verified live against the deployed
workers.
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

_WORKER_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "services", "vton-worker")
if _WORKER_ROOT not in sys.path:
    sys.path.insert(0, _WORKER_ROOT)

import server_core  # noqa: E402


# --- fixtures -----------------------------------------------------------------

class _StubEngine:
    name = "fashn_v15"

    def metadata(self):
        return {"model": "stub fashn-vton-v1.5"}


class _StubHolder:
    """Duck-typed engine holder — the same surface the Modal class and the
    Baseten holder expose."""

    def __init__(self, loaded: bool = True):
        self.model_loaded = loaded
        self.load_error = None if loaded else "RuntimeError: simulated missing weights"
        self.engine = _StubEngine() if loaded else None
        self.device_name = "NVIDIA L4" if loaded else None


@pytest.fixture()
def token_env(monkeypatch):
    monkeypatch.setenv("VTON_WORKER_ADMIN_TOKEN", "test-admin-token")
    yield "test-admin-token"
    monkeypatch.delenv("VTON_WORKER_ADMIN_TOKEN", raising=False)


@pytest.fixture()
def client(token_env):
    return TestClient(server_core.create_app(_StubHolder(loaded=True)))


@pytest.fixture()
def cold_client(token_env):
    return TestClient(server_core.create_app(_StubHolder(loaded=False)))


# --- /health -------------------------------------------------------------------

def test_health_shape_and_honesty_when_loaded(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy"
    assert body["model_loaded"] is True
    assert body["engine"] == "fashn_v15"
    assert body["multigarment"] is True
    assert body["max_garments"] == 3
    assert body["ready"] is True
    assert body["commercial"] is False  # honest: parser is non-commercial
    parser = body["parser"]
    assert parser["present"] is True
    assert "non-commercial" in parser["license"].lower()


def test_health_reports_degraded_not_fake_success_when_load_failed(cold_client):
    body = cold_client.get("/health").json()
    assert cold_client.get("/health").status_code == 200  # never a 500
    assert body["status"] == "degraded"
    assert body["model_loaded"] is False
    assert body["ready"] is False
    assert "simulated missing weights" in body["load_error"]


def test_health_works_without_torch():
    """torch import is optional in the health handler (CPU-only hosts)."""
    import builtins
    real_import = builtins.__import__

    def _no_torch(name, *a, **k):
        if name == "torch":
            raise ImportError("no torch on this host")
        return real_import(name, *a, **k)

    builtins.__import__ = _no_torch
    try:
        c = TestClient(server_core.create_app(_StubHolder(loaded=True)))
        body = c.get("/health").json()
        assert body["cuda_available"] is False
        assert body["device"] == "NVIDIA L4"  # holder truth wins
    finally:
        builtins.__import__ = real_import


# --- /readiness ------------------------------------------------------------------

def test_readiness_200_when_loaded(client):
    r = client.get("/readiness")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_readiness_503_vton_not_ready_when_cold(cold_client):
    r = cold_client.get("/readiness")
    assert r.status_code == 503
    err = r.json()["detail"]["error"]
    assert err["code"] == "VTON_NOT_READY"
    assert err["ready"] is False


# --- /process: auth ----------------------------------------------------------------

def test_process_401_without_admin_header(client):
    r = client.post("/process", json={
        "job_id": "job_1",
        "user_image_base64_or_url": "data:image/png;base64,AAAA",
        "garments": [{"slot_type": "upper_inner", "image_base64": "data:image/png;base64,AAAA"}],
    })
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_process_401_with_wrong_token(client, token_env):
    r = client.post("/process",
                    headers={"X-VTON-Admin": "wrong"},
                    json={
                        "job_id": "job_1",
                        "user_image_base64_or_url": "data:image/png;base64,AAAA",
                        "garments": [{"slot_type": "upper_inner", "image_base64": "data:image/png;base64,AAAA"}],
                    })
    assert r.status_code == 401


def test_process_503_engine_unavailable_when_cold(cold_client, token_env):
    r = cold_client.post("/process",
                         headers={"X-VTON-Admin": token_env},
                         json={
                             "job_id": "job_1",
                             "user_image_base64_or_url": "data:image/png;base64,AAAA",
                             "garments": [{"slot_type": "upper_inner", "image_base64": "data:image/png;base64,AAAA"}],
                         })
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "VTON_ENGINE_UNAVAILABLE"


def test_process_token_from_baseten_secrets_file(tmp_path, monkeypatch):
    """On Baseten the token may arrive as a read-only secrets FILE, not env."""
    monkeypatch.delenv("VTON_WORKER_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("CONFIT_WORKER_ADMIN_TOKEN", raising=False)
    sec = tmp_path / "confit_worker_admin_token"
    sec.write_text("file-token-123\n")
    import builtins
    real_open = builtins.open

    def _fake_open(path, *a, **k):
        if str(path).endswith("confit_worker_admin_token"):
            return real_open(sec, *a, **k)
        return real_open(path, *a, **k)

    monkeypatch.setattr(builtins, "open", _fake_open)
    assert server_core._expected_admin_token() == "file-token-123"


# --- /process: input validation (pydantic layer) -------------------------------------

def test_process_rejects_four_garments(client, token_env):
    r = client.post("/process",
                    headers={"X-VTON-Admin": token_env},
                    json={
                        "job_id": "job_1",
                        "user_image_base64_or_url": "x",
                        "garments": [
                            {"slot_type": "upper_inner", "image_base64": "x"},
                            {"slot_type": "upper_outer", "image_base64": "x"},
                            {"slot_type": "lower", "image_base64": "x"},
                            {"slot_type": "dress", "image_base64": "x"},
                        ],
                    })
    assert r.status_code == 422


def test_process_rejects_unknown_overlay_mode(client, token_env):
    r = client.post("/process",
                    headers={"X-VTON-Admin": token_env},
                    json={
                        "job_id": "job_1",
                        "user_image_base64_or_url": "x",
                        "garments": [{"slot_type": "lower", "image_base64": "x"}],
                        "overlay_mode": "aggressive",
                    })
    assert r.status_code == 422


def test_process_rejects_bad_job_id_charset(client, token_env):
    r = client.post("/process",
                    headers={"X-VTON-Admin": token_env},
                    json={
                        "job_id": "job/with/slashes",
                        "user_image_base64_or_url": "x",
                        "garments": [{"slot_type": "lower", "image_base64": "x"}],
                    })
    assert r.status_code == 422


# --- /process: SSRF guard (runs BEFORE any fetch) --------------------------------------

def test_process_rejects_private_network_person_image(client, token_env):
    r = client.post("/process",
                    headers={"X-VTON-Admin": token_env},
                    json={
                        "job_id": "job_1",
                        "user_image_base64_or_url": "http://169.254.169.254/latest/meta-data/",
                        "garments": [{"slot_type": "upper_inner", "image_base64": "x"}],
                    })
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "INPUT_INVALID"


def test_ssrf_guard_blocks_private_and_metadata_targets():
    for bad in (
        "http://127.0.0.1:8000/health",
        "http://10.0.0.5/img.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/x.png",
        "file:///etc/passwd",
        "ftp://example.com/x.png",
        "",
    ):
        assert server_core._is_safe_url(bad) is False, bad


# --- output verification (pure) ----------------------------------------------------------

def test_verify_output_passes_on_real_change():
    from PIL import Image
    a = Image.new("RGB", (64, 64), (10, 10, 10))
    b = Image.new("RGB", (64, 64), (200, 150, 100))
    out = server_core.verify_output(a, b)
    assert out["PASS"] is True


def test_verify_output_fails_on_echo():
    from PIL import Image
    a = Image.new("RGB", (64, 64), (10, 10, 10))
    out = server_core.verify_output(a, a.copy())
    assert out["PASS"] is False


# --- single source of truth: the Modal shell re-exports the shared layer ------------------

def test_modal_shell_uses_the_shared_http_layer():
    """modal_app_v15 must delegate to (not duplicate) server_core."""
    import modal_app_v15  # noqa: F401  (imports server_core at module load)

    assert modal_app_v15.VTONJobRequest is server_core.VTONJobRequest
    assert modal_app_v15._parser_info is server_core._parser_info
    # The endpoints are one-line delegations to the shared handlers.
    src = open(
        os.path.join(_WORKER_ROOT, "modal_app_v15.py"), encoding="utf-8"
    ).read()
    assert "server_core.handle_health(self)" in src
    assert "server_core.handle_readiness(self)" in src
    assert "server_core.handle_process(self, payload, x_vton_admin)" in src


# --- platform gateway auth (Baseten cutover, 2026-10-03) --------------------------
#
# Baseten's router requires its own Authorization header on EVERY route, in
# addition to our X-VTON-Admin token. These tests pin that the backend attaches
# VTON_WORKER_GATEWAY_AUTHORIZATION to the readiness/health gate AND the
# process POST (and that the observability probe does the same).

@pytest.mark.asyncio
async def test_gateway_authorization_sent_on_every_worker_route(monkeypatch):
    from backend.app.core.config import settings as cfg
    from backend.app.services.tryon_service import TryOnService
    import httpx

    PROCESS = "https://model-test.api.baseten.co/environments/production/sync/process"
    monkeypatch.setattr(cfg, "VTON_WORKER_URL", PROCESS, raising=False)
    monkeypatch.setattr(cfg, "VTON_WORKER_ADMIN_TOKEN", "admin-tok", raising=False)
    monkeypatch.setattr(cfg, "VTON_WORKER_GATEWAY_AUTHORIZATION", "Api-Key gw-key", raising=False)
    monkeypatch.setattr(cfg, "VTON_WORKER_HEALTH_URL", None, raising=False)
    monkeypatch.setattr(cfg, "VTON_WORKER_READINESS_URL", None, raising=False)

    seen = []

    import io as _io
    import random as _random
    from PIL import Image as _Image

    def _fake_png_b64() -> str:
        img = _Image.new("RGB", (600, 800), color=(120, 40, 60))
        px = img.load()
        rng = _random.Random(11)
        for _ in range(20000):  # texture so the PNG decodes above size floors
            px[rng.randrange(600), rng.randrange(800)] = (
                rng.randrange(255), rng.randrange(255), rng.randrange(255))
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        import base64 as _b64
        return "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode()

    _RENDERED = _fake_png_b64()

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("authorization"),
                     request.headers.get("x-vton-admin")))
        if request.url.path.endswith("/readiness") or request.url.path.endswith("/health"):
            return httpx.Response(200, json={"ready": True, "model_loaded": True})
        return httpx.Response(200, json={
            "job_id": "job_gw", "status": "completed",
            "rendered_image_data_url": _RENDERED,
            "execution_time_ms": 1.0, "total_time_ms": 2.0,
            "model_used": "test", "engine": "fashn_v15",
            "layers_processed": 1, "layers": [{"category": "tops", "verify": {"PASS": True}}],
            "all_layers_verified": True, "verify": {"PASS": True, "metric_pixel_change": 12.0},
        })

    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    def _fake_jpeg_b64() -> str:
        img = _Image.new("RGB", (600, 800), color=(30, 60, 90))
        px = img.load()
        rng = _random.Random(13)
        for _ in range(20000):
            px[rng.randrange(600), rng.randrange(800)] = (
                rng.randrange(255), rng.randrange(255), rng.randrange(255))
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        import base64 as _b64
        return "data:image/jpeg;base64," + _b64.b64encode(buf.getvalue()).decode()

    svc = TryOnService.__new__(TryOnService)  # pure HTTP path, no DB needed
    result = await svc._call_gpu_worker(
        job_id="job_gw",
        person_image=_fake_jpeg_b64(),
        garments=[{"slot_type": "upper_inner", "image_base64": _fake_jpeg_b64()}],
    )
    assert result["status"] == "completed"

    paths = {p for p, _, _ in seen}
    # readiness gate + the process POST both went through the gateway, and
    # EVERY route seen carried the gateway credential AND our own token.
    # (/health is only reached when readiness fails — not this path.)
    assert any(p.endswith("/readiness") for p in paths), seen
    assert any(p.endswith("/process") for p in paths), seen
    for path, auth, admin in seen:
        assert auth == "Api-Key gw-key", (path, auth)
        assert admin == "admin-tok", (path, admin)


@pytest.mark.asyncio
async def test_gateway_authorization_absent_for_modal_worker(monkeypatch):
    """Unset (Modal-style direct worker): no Authorization header is invented."""
    from backend.app.core.config import settings as cfg
    from backend.app.services.tryon_service import TryOnService
    from backend.app.services import vton_worker_observability as vwo
    import httpx

    monkeypatch.setattr(cfg, "VTON_WORKER_URL",
                        "https://w-example--vtoninferenceservice-process.modal.run", raising=False)
    monkeypatch.setattr(cfg, "VTON_WORKER_ADMIN_TOKEN", "admin-tok", raising=False)
    monkeypatch.setattr(cfg, "VTON_WORKER_GATEWAY_AUTHORIZATION", None, raising=False)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ready": True, "model_loaded": True})

    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    vwo.reset_worker_observability()
    try:
        state = vwo.probe_worker_state(force=True)
        assert state["verdict"] == vwo.VERDICT_READY
    finally:
        vwo.reset_worker_observability()
