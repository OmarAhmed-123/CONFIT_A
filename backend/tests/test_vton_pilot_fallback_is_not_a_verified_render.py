"""A pilot render that applied nothing must never come back as success.

The GPU worker path runs every layer through ``assert_layer_applied``: a render
counts only when the engine's ``verify.PASS`` is exactly True. The pilot
fallback — the free HF-Space chain used when the worker is unreachable — computed
its own ``verify.PASS`` and returned it, but nothing asserted on it. So when a
pilot engine answered 200 with an unchanged person (ZeroGPU quota, a 404
``/upload``, an engine that silently no-ops), the job was persisted as
``completed`` and the shopper was handed an image the platform had not verified.

Two honest outcomes are acceptable, and this file pins both:
  * route the pilot result through the same ``assert_layer_applied`` gate, so a
    not-applied render fails with the canonical ``VTON_LAYER_NOT_APPLIED``; or
  * return ``502 VTON_LAYER_NOT_APPLIED`` to the caller.
What is not acceptable — and is what the first test reproduces — is
``status: completed`` with zero verified layers.

Consumer check (who reads the pilot response, and on what field): the sync
``/try-on/multi-render`` path reads ``rendered_image_data_url`` and
``verification.all_layers_verified``; the async job path reads the same dict and
persists ``status``. Neither inspects ``verify`` itself, which is exactly why the
missing assertion was invisible to every existing test.
"""
from __future__ import annotations

import base64
import io
import random
import uuid

import pytest
from PIL import Image

UNIQUE = uuid.uuid4().hex[:8]


def _person_png_data_url() -> str:
    rng = random.Random(424242)
    w, h = 320, 512
    img = Image.new("RGB", (w, h), color=(118, 112, 104))
    px = img.load()
    for _ in range(6000):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _unchanged_person() -> str:
    return _person_png_data_url()


def _pilot_result(pass_value):
    """The exact shape ``pilot_renderer.render_layers`` returns."""
    return {
        "rendered_image_data_url": _unchanged_person(),
        "model_used": "pilot-fake",
        "verify": {
            "PASS": pass_value,
            "metric_pixel_change": 0.0 if not pass_value else 42.0,
            "metric_color_shift": 0.0 if not pass_value else 0.05,
            "metric_image_stddev": 3.0,
        },
        "engine_tier": "commercial",
        "layers": [],
        "commercial_safe": True,
    }


@pytest.fixture
def pilot_only(monkeypatch):
    """No worker configured, and the pilot chain returns whatever we set."""
    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    import backend.app.providers.vton.pilot_renderer as pilot

    state = {"pass": True, "called": 0}

    def _fake_render_layers(**kwargs):
        state["called"] += 1
        return _pilot_result(state["pass"])

    monkeypatch.setattr(pilot, "render_layers", _fake_render_layers)
    return state


def _call_worker(pilot_pass: bool):
    """Drive the REAL ``_call_gpu_worker`` with the pilot chain as the only backend.

    The HTTP path is not used here because the test catalogue's photos are
    on-model and the garment-asset guard (correctly) refuses them before any
    render is attempted; that guard is somebody else's invariant and this test
    must not weaken it to reach the code under test.
    """
    import asyncio

    from backend.app.services.tryon_service import TryOnService

    service = TryOnService(db=None)  # type: ignore[arg-type]
    return asyncio.run(service._call_gpu_worker(
        job_id="job_pilot_" + UNIQUE,
        person_image=_person_png_data_url(),
        garments=[{"slot_type": "upper_inner", "category": "tops",
                   "image_base64": _person_png_data_url()}],
    ))


def test_a_pilot_render_that_applied_nothing_raises_the_canonical_code(pilot_only):
    """THE BUG: verify.PASS=False from the pilot was accepted and returned."""
    pilot_only["pass"] = False          # engine answered 200, person unchanged
    with pytest.raises(RuntimeError) as excinfo:
        _call_worker(False)
    message = str(excinfo.value)
    assert message.startswith("VTON_LAYER_NOT_APPLIED"), (
        "a pilot render with verify.PASS=False must fail with the canonical "
        f"code the worker path uses; got: {message[:200]}"
    )
    assert "VTON_LAYER_NOT_APPLIED" != "GPU_WORKER_ERROR"


def test_a_verified_pilot_render_is_returned(pilot_only):
    """The guard must not break the working fallback."""
    pilot_only["pass"] = True
    result = _call_worker(True)
    assert result["verify"]["PASS"] is True
    assert (result.get("rendered_image_data_url") or "").startswith("data:image")


def test_the_pilot_result_goes_through_the_same_gate_as_the_worker_path():
    """One gate, two callers — the unification the owner asked for."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "services" / "tryon_service.py"
    text = src.read_text()
    start = text.index("async def _try_pilot_render")
    end = text.index("if not worker_url:", start)
    block = text[start:end]
    assert "assert_layer_applied" in block, (
        "the pilot result is accepted without going through the same "
        "assert_layer_applied gate the worker path uses"
    )
