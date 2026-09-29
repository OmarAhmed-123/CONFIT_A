"""A configured-but-dead GPU worker must fall back to a pilot engine.

THE DEFECT THIS LOCKS DOWN
--------------------------
Production verification of the previous pass:

    POST /api/v1/tryon/multi-render
    -> HTTP 503 after 35.0s
       VTON_WORKER_NOT_READY: worker unreachable after 3 attempt(s)

VTON_WORKER_URL IS set in production, pointing at a Modal app that is out of
credit. The pilot hook only covered `not worker_url`, so every render spent
35 seconds on retries and then refused — while a pilot engine that could
have served sat unused, and /try-on/capabilities simultaneously reported
`available` because the CAPABILITY classifier had been taught about pilot
engines and the RENDER path had not.

Two surfaces answering the same question differently is the defect this
repository keeps re-learning. These tests pin the render path specifically.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from backend.app.core.config import settings
from backend.app.services.tryon_service import TryOnService


def _service() -> TryOnService:
    return TryOnService.__new__(TryOnService)


def _pilot_result() -> Dict[str, Any]:
    return {
        "rendered_image_data_url": "data:image/png;base64,AAAA",
        "model_used": "idm_vton_hf",
        "verify": {"PASS": True, "metric_pixel_change": 21.0,
                   "metric_color_shift": 0.08},
        "engine_tier": "pilot",
        "layers": [],
        "commercial_safe": False,
    }


@pytest.fixture
def stub_pilot(monkeypatch):
    """Replace the pilot renderer; the network is never touched."""
    calls: Dict[str, Any] = {"count": 0, "reasons": [], "raise": None}

    def fake_render_layers(**kwargs):
        calls["count"] += 1
        calls["reasons"].append(kwargs.get("tier"))
        if calls["raise"]:
            raise calls["raise"]
        # Honour the licence tier: the real renderer resolves an EMPTY chain
        # under COMMERCIAL with no healthy worker and raises. A stub that
        # served regardless would hide the gate this suite exists to protect.
        from backend.app.providers.vton.registry import LicenseTier

        if kwargs.get("tier") is LicenseTier.COMMERCIAL:
            from backend.app.providers.vton.pilot_renderer import (
                PilotRenderUnavailable,
            )

            raise PilotRenderUnavailable(
                "no commercially licensed engine without a healthy worker"
            )
        return _pilot_result()

    import backend.app.providers.vton.pilot_renderer as pr

    monkeypatch.setattr(pr, "render_layers", fake_render_layers)
    return calls


def _call(svc, **over):
    kwargs = dict(
        job_id="t-1",
        person_image="data:image/jpeg;base64,AAAA",
        garments=[{"product_id": 5, "image_url": "https://example.com/g.jpg",
                   "title": "Silk Maxi Dress"}],
    )
    kwargs.update(over)
    return asyncio.run(svc._call_gpu_worker(**kwargs))


def test_unconfigured_worker_falls_back_to_pilot(monkeypatch, stub_pilot):
    svc = _service()
    monkeypatch.setattr(svc, "_get_worker_config", lambda: (None, ""), raising=False)
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "pilot", raising=False)

    result = _call(svc)
    assert result["model_used"] == "idm_vton_hf"
    assert stub_pilot["count"] == 1


def test_unreachable_worker_falls_back_instead_of_raising(monkeypatch, stub_pilot):
    """The exact production state: URL set, Modal app out of credit."""
    svc = _service()
    monkeypatch.setattr(
        svc, "_get_worker_config",
        lambda: ("https://dead.modal.run/process", "tok"), raising=False,
    )
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "pilot", raising=False)

    class _DeadClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise RuntimeError("workspace is disabled")
        async def post(self, *a, **k): raise RuntimeError("workspace is disabled")

    # `_call_gpu_worker` does `import httpx` inside the function, so the
    # library itself is the patch point, not the module attribute.
    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **k: _DeadClient())
    # Capture the real sleep FIRST: a stub that calls asyncio.sleep(0) after
    # patching asyncio.sleep recurses forever.
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: _real_sleep(0))

    result = _call(svc)
    assert result["model_used"] == "idm_vton_hf", (
        "a dead worker must hand off to the pilot chain, not refuse"
    )
    assert stub_pilot["count"] == 1


def test_commercial_tier_still_refuses_a_dead_worker(monkeypatch, stub_pilot):
    """The licence gate is not bypassed by the worker being down."""
    svc = _service()
    monkeypatch.setattr(
        svc, "_get_worker_config",
        lambda: ("https://dead.modal.run/process", "tok"), raising=False,
    )
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "commercial", raising=False)

    class _DeadClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise RuntimeError("workspace is disabled")
        async def post(self, *a, **k): raise RuntimeError("workspace is disabled")

    # `_call_gpu_worker` does `import httpx` inside the function, so the
    # library itself is the patch point, not the module attribute.
    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **k: _DeadClient())
    # Capture the real sleep FIRST: a stub that calls asyncio.sleep(0) after
    # patching asyncio.sleep recurses forever.
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: _real_sleep(0))

    with pytest.raises(RuntimeError) as exc:
        _call(svc)
    message = str(exc.value)
    # The ORIGINAL worker failure must lead — that is what an operator acts
    # on. The pilot outcome is appended as context, labelled as a licence
    # refusal rather than a crash, so the two are never confused.
    assert message.startswith(("VTON_WORKER", "VTON_ENGINE", "GPU_WORKER")), message
    assert "pilot_unavailable" in message
    assert "pilot_error" not in message, "a licence refusal is not a crash"


def test_pilot_failure_surfaces_the_original_worker_error(monkeypatch, stub_pilot):
    """A pilot that also fails must not mask why the worker failed."""
    svc = _service()
    monkeypatch.setattr(svc, "_get_worker_config", lambda: (None, ""), raising=False)
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "pilot", raising=False)
    stub_pilot["raise"] = RuntimeError("space is down")

    with pytest.raises(RuntimeError, match="VTON_ENGINE_UNAVAILABLE"):
        _call(svc)


def test_the_pilot_reason_is_surfaced_not_swallowed(monkeypatch, stub_pilot):
    """When both paths fail, the caller must learn WHY the pilot declined.

    The first version returned None from `_try_pilot_render` and re-raised
    only the worker error, so a 503 read "worker unreachable" whether the
    pilot had been tried, refused on licence, or crashed inside the engine.
    On a serverless plan without log access that difference is the entire
    diagnosis, so it belongs in the error.
    """
    svc = _service()
    monkeypatch.setattr(svc, "_get_worker_config", lambda: (None, ""), raising=False)
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "pilot", raising=False)
    stub_pilot["raise"] = RuntimeError("read-only file system: /home/sbx_user")

    with pytest.raises(RuntimeError) as exc:
        _call(svc)

    message = str(exc.value)
    assert "VTON_ENGINE_UNAVAILABLE" in message
    assert "pilot_error" in message, "the pilot outcome must be reported"
    assert "read-only file system" in message, (
        "the engine's own reason must survive to the caller"
    )


def test_a_licence_refusal_is_labelled_differently_from_a_crash(
    monkeypatch, stub_pilot
):
    """'Not permitted' and 'broke' are different operator actions."""
    svc = _service()
    monkeypatch.setattr(svc, "_get_worker_config", lambda: (None, ""), raising=False)
    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "commercial", raising=False)

    with pytest.raises(RuntimeError) as exc:
        _call(svc)
    assert "pilot_unavailable" in str(exc.value)


def test_animation_failure_preserves_both_causes():
    """The animation handler must not overwrite the layer's own error.

    It used to replace whatever went wrong with a fixed
    "Animated try-on requires GPU worker" sentence, discarding the
    per-engine reason the render path had just attached. Every animation
    failure therefore read identically, whatever had actually happened —
    which is why diagnosing it took several deploys.
    """
    import inspect

    from backend.app.services import tryon_service as ts

    source = inspect.getsource(ts.TryOnService.execute_animated_tryon)
    assert "layer_error" in source, (
        "the originating layer error must travel with the animation failure"
    )
    assert "provider_error" in source, (
        "the provider fallback's own error must be reported too"
    )
    # The bare, information-free sentence must be gone.
    assert "Animated try-on requires GPU worker. " not in source
