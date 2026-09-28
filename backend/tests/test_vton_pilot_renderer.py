"""Pilot-tier rendering: contract shape, measured verification, honest refusal.

These tests never touch the network. The engine call is stubbed so the logic
under test is the part that decides WHAT to believe about a render — which is
where the dangerous failures live. An engine can return HTTP 200 and an image
that is simply the person again, and everything downstream would treat that as
a successful try-on.
"""
from __future__ import annotations

import base64
import io
from typing import Any, Dict

import pytest
from PIL import Image

from backend.app.providers.vton import pilot_renderer as pr
from backend.app.providers.vton.registry import LicenseTier


def _png(colour, size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


def _data_url(colour) -> str:
    return "data:image/png;base64," + base64.b64encode(_png(colour)).decode()


class _FakeResult:
    def __init__(self, path, engine="idm_vton_hf", commercial=False):
        self.image_path = path
        self.engine = engine
        self.license = "CC BY-NC-SA 4.0"
        self.commercial = commercial
        self.elapsed_seconds = 1.0
        self.category = "dress"


@pytest.fixture
def stub_engine(monkeypatch, tmp_path):
    """Replace the Space call with a controllable local renderer."""
    # A DIFFERENT colour per call. With a constant colour the second layer
    # would be pixel-identical to the first and the renderer would correctly
    # reject it as "did not change the person" — a stub artefact, not a bug.
    palette = [(10, 200, 10), (10, 10, 220), (220, 160, 10), (200, 10, 200)]
    state: Dict[str, Any] = {"colour": None, "calls": 0, "fail": False}

    def fake_render(spec, *, person_image_path, garment_image_path,
                    category, garment_description="", timeout=None):
        state["calls"] += 1
        if state["fail"]:
            raise RuntimeError("engine exploded")
        colour = state["colour"] or palette[(state["calls"] - 1) % len(palette)]
        out = tmp_path / f"out_{state['calls']}.png"
        out.write_bytes(_png(colour))
        return _FakeResult(str(out), engine=spec.key, commercial=spec.commercial)

    monkeypatch.setattr(pr.hf, "render", fake_render)
    return state


# ── the licence tier must not be widened by a typo ────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("pilot", LicenseTier.PILOT),
    ("PILOT", LicenseTier.PILOT),
    ("  pilot ", LicenseTier.PILOT),
    ("commercial", LicenseTier.COMMERCIAL),
    ("piolt", LicenseTier.COMMERCIAL),   # typo
    ("", LicenseTier.COMMERCIAL),
    (None, LicenseTier.COMMERCIAL),
])
def test_tier_parsing_fails_closed(raw, expected):
    """Anything unrecognised must RESTRICT which engines may run."""
    assert pr.resolve_tier(raw) is expected


# ── the contract downstream code depends on ───────────────────────────────

def test_render_returns_the_gpu_worker_contract(stub_engine):
    out = pr.render_layers(
        person_image=_data_url((0, 0, 0)),
        garments=[{"image_url": _data_url((255, 0, 0)), "title": "Silk Maxi Dress"}],
        tier=LicenseTier.PILOT,
    )
    # Exactly the keys _call_gpu_worker's callers read.
    assert out["rendered_image_data_url"].startswith("data:image/")
    assert "verify" in out and "PASS" in out["verify"]
    assert out["model_used"]
    assert out["engine_tier"] == "pilot"


def test_verify_pass_is_measured_from_pixels(stub_engine):
    """A real change must be evidenced, not assumed."""
    out = pr.render_layers(
        person_image=_data_url((0, 0, 0)),
        garments=[{"image_url": _data_url((255, 0, 0)), "title": "Maxi Dress"}],
        tier=LicenseTier.PILOT,
    )
    assert out["verify"]["PASS"] is True
    assert out["verify"]["metric_pixel_change"] > pr.MIN_PIXEL_CHANGE
    assert out["verify"]["metric_color_shift"] > pr.MIN_COLOR_SHIFT


def test_an_unchanged_render_is_rejected_not_reported_as_success(stub_engine):
    """The dangerous case: HTTP 200 with the person unchanged.

    Everything downstream would treat that as a successful try-on, so the
    chain must advance and ultimately refuse.
    """
    stub_engine["colour"] = (0, 0, 0)  # identical to the person image
    with pytest.raises(pr.PilotRenderUnavailable) as exc:
        pr.render_layers(
            person_image=_data_url((0, 0, 0)),
            garments=[{"image_url": _data_url((255, 0, 0)), "title": "Maxi Dress"}],
            tier=LicenseTier.PILOT,
        )
    assert "did not change the person" in str(exc.value)


def test_engine_failure_advances_the_chain_then_refuses(stub_engine):
    stub_engine["fail"] = True
    with pytest.raises(pr.PilotRenderUnavailable):
        pr.render_layers(
            person_image=_data_url((0, 0, 0)),
            garments=[{"image_url": _data_url((255, 0, 0)), "title": "Maxi Dress"}],
            tier=LicenseTier.PILOT,
        )
    # Every engine in the dress chain was attempted before giving up.
    assert stub_engine["calls"] >= 2


# ── refusals ───────────────────────────────────────────────────────────────

def test_accessories_are_refused_rather_than_rendered(stub_engine):
    """No garment-VTON model is trained on bags. Declining is the honest act."""
    with pytest.raises(pr.PilotRenderUnavailable) as exc:
        pr.render_layers(
            person_image=_data_url((0, 0, 0)),
            garments=[{"image_url": _data_url((9, 9, 9)),
                       "title": "Structured Metallic Evening Box Clutch"}],
            tier=LicenseTier.PILOT,
        )
    assert "VTON_CATEGORY_UNSUPPORTED" in str(exc.value)
    assert stub_engine["calls"] == 0, "an accessory must never reach an engine"


def test_commercial_tier_without_a_worker_refuses(stub_engine):
    """The only clean engine needs the GPU worker; no worker, no render."""
    with pytest.raises(pr.PilotRenderUnavailable):
        pr.render_layers(
            person_image=_data_url((0, 0, 0)),
            garments=[{"image_url": _data_url((255, 0, 0)), "title": "Maxi Dress"}],
            tier=LicenseTier.COMMERCIAL,
            worker_configured=False,
        )
    assert stub_engine["calls"] == 0


def test_no_garments_is_rejected(stub_engine):
    with pytest.raises(ValueError, match="at least one garment"):
        pr.render_layers(person_image=_data_url((0, 0, 0)), garments=[],
                         tier=LicenseTier.PILOT)


# ── multi-garment ──────────────────────────────────────────────────────────

def test_multiple_garments_are_applied_sequentially(stub_engine):
    """Each layer feeds the next, and each is reported separately."""
    out = pr.render_layers(
        person_image=_data_url((0, 0, 0)),
        garments=[
            {"image_url": _data_url((255, 0, 0)), "title": "Silk Maxi Dress"},
            {"image_url": _data_url((0, 0, 255)), "title": "Wool Blazer"},
        ],
        tier=LicenseTier.PILOT,
    )
    assert stub_engine["calls"] == 2
    assert len(out["layers"]) == 2
    assert [l["category"] for l in out["layers"]] == ["dress", "outerwear"]
    assert out["model_used"].count("+") == 1


def test_a_pilot_render_is_flagged_as_not_commercially_safe(stub_engine):
    """Assets made with non-commercial weights must stay identifiable."""
    out = pr.render_layers(
        person_image=_data_url((0, 0, 0)),
        garments=[{"image_url": _data_url((255, 0, 0)), "title": "Maxi Dress"}],
        tier=LicenseTier.PILOT,
    )
    assert out["commercial_safe"] is False
    assert all(l["license"] for l in out["layers"])


def test_availability_requires_a_usable_transport(monkeypatch):
    """`available` must mean THIS process can render, not that a Space exists.

    Every pilot engine is reached through gradio_client, which is absent from
    the Vercel function on purpose. Reporting availability there would open
    every try-on CTA and fail at the end — the 2026-09-22 over-promising
    defect rebuilt on a new cause.
    """
    import builtins

    from backend.app.core.config import settings
    from backend.app.services import vton_worker_observability as vwo

    monkeypatch.setattr(settings, "VTON_LICENSE_TIER", "pilot", raising=False)
    assert vwo.pilot_engines_available() is True, "baseline: transport present"

    real_import = builtins.__import__

    def no_gradio(name, *args, **kwargs):
        if name == "gradio_client":
            raise ImportError("not installed in this runtime")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_gradio)
    assert vwo.pilot_engines_available() is False, (
        "without the transport the platform must not claim it can render"
    )


def test_hf_cache_is_redirected_to_tmp_before_import(monkeypatch, tmp_path):
    """Serverless filesystems are read-only except /tmp.

    `gradio_client` pulls in `huggingface_hub`, which writes a cache tree
    under $HOME. On Vercel that raises OSError(30, 'Read-only file system')
    and the engine appears to fail for no visible reason — which is exactly
    what production showed while `vton_renderable` reported True.
    """
    from backend.app.providers.vton import hf_space_client as hf

    for key in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "XDG_CACHE_HOME"):
        monkeypatch.delenv(key, raising=False)

    hf._prepare_hf_cache()

    import os

    assert os.environ["HF_HOME"].startswith("/tmp")
    assert os.environ["HUGGINGFACE_HUB_CACHE"].startswith("/tmp")
    assert os.path.isdir(os.environ["HF_HOME"]), "the cache dir must exist"


def test_an_existing_hf_home_is_respected(monkeypatch):
    """A container with a writable HOME keeps its own cache."""
    from backend.app.providers.vton import hf_space_client as hf

    monkeypatch.setenv("HF_HOME", "/workspace/hf")
    hf._prepare_hf_cache()
    import os

    assert os.environ["HF_HOME"] == "/workspace/hf"


# ── the shape the SERVICE actually emits ──────────────────────────────────

def test_slot_type_decides_the_category_not_the_title(stub_engine):
    """The production failure, pinned.

    `tryon_service` builds garments as {"product_id", "slot_type",
    "image_base64"} — no title, no category name. Text inference saw only
    None and fell through to the ACCESSORY default, so production refused a
    DRESS with "no engine may render 'accessory'". The slot the pipeline
    already computed is authoritative.
    """
    out = pr.render_layers(
        person_image=_data_url((0, 0, 0)),
        garments=[{"product_id": 5, "slot_type": "dress",
                   "image_base64": _data_url((255, 0, 0))}],
        tier=LicenseTier.PILOT,
    )
    assert out["layers"][0]["category"] == "dress"
    assert stub_engine["calls"] == 1


@pytest.mark.parametrize("slot,expected", [
    ("upper_inner", "upper_body"),
    ("upper_outer", "outerwear"),
    ("lower", "lower_body"),
    ("dress", "dress"),
])
def test_every_renderable_slot_maps_to_a_servable_category(slot, expected, stub_engine):
    out = pr.render_layers(
        person_image=_data_url((0, 0, 0)),
        garments=[{"product_id": 1, "slot_type": slot,
                   "image_base64": _data_url((255, 0, 0))}],
        tier=LicenseTier.PILOT,
    )
    assert out["layers"][0]["category"] == expected


def test_bare_base64_without_a_data_prefix_is_accepted(stub_engine):
    """`_fetch_image_as_base64` returns bare base64; rejecting it failed the
    normal pre-fetch path for every request."""
    import base64 as _b64

    bare = _b64.b64encode(_png((0, 0, 255))).decode()
    out = pr.render_layers(
        person_image=_data_url((0, 0, 0)),
        garments=[{"product_id": 1, "slot_type": "dress", "image_base64": bare}],
        tier=LicenseTier.PILOT,
    )
    assert out["verify"]["PASS"] is True


def test_an_accessory_slot_is_still_refused(stub_engine):
    with pytest.raises(pr.PilotRenderUnavailable, match="VTON_CATEGORY_UNSUPPORTED"):
        pr.render_layers(
            person_image=_data_url((0, 0, 0)),
            garments=[{"product_id": 9, "slot_type": "footwear",
                       "image_base64": _data_url((9, 9, 9))}],
            tier=LicenseTier.PILOT,
        )
