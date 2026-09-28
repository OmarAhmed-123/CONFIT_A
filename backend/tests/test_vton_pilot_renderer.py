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
