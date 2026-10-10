"""Grounding must judge the answer against EVERY look on offer, and the response
must say honestly where its text came from.

DEFECTS THESE TESTS PIN (reproduced 2026-10-10, live, via /api/v1/stylist/chat)
--------------------------------------------------------------------------------
1. The brand guard only knew the PRIMARY look's brands, while the model was asked
   to describe every look shown. A correct description of the second look named a
   catalogue brand from that look and was refused, so the whole model answer was
   replaced by the grounded template. The shopper saw an unrelated template.
2. The fallback text and footer did not say why the model's answer was not used.
   Now answer_source is "provider", "grounding_rejected", "providers_unavailable",
   or "no_provider_configured".

No network and no paid call: the provider legs are stubbed. These tests prove the
decision logic and the returned payload, not model quality.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.app.core.config import settings
from backend.app.providers.orchestrator import get_orchestrator


def _item(brand: str, title: str = "Item") -> dict:
    return {"brand_name": brand, "product_title": title, "position": "top"}


PRIMARY = {"title": "Look one", "items": [_item("Reiss", "Silk slip dress")]}
SECOND = {"title": "Look two", "items": [_item("Massimo Dutti", "Navy blazer")]}
CATALOGUE_BRANDS = ["COS", "Massimo Dutti", "Reiss", "Zara"]


# ── verifier ─────────────────────────────────────────────────────────

def test_answer_about_second_look_brand_is_accepted():
    orch = get_orchestrator()
    text = "For the second look, the Massimo Dutti navy blazer works with the trousers."
    assert orch._verify_grounding(text, PRIMARY, CATALOGUE_BRANDS, [SECOND]) is True


def test_same_answer_is_refused_when_second_look_is_not_offered():
    # The old behaviour: the guard saw only the primary look.
    orch = get_orchestrator()
    text = "For the second look, the Massimo Dutti navy blazer works with the trousers."
    assert orch._verify_grounding(text, PRIMARY, CATALOGUE_BRANDS, None) is False


def test_brand_offered_nowhere_is_still_refused():
    orch = get_orchestrator()
    text = "Pair the silk slip with a Zara jacket."  # Zara is in the catalogue, not offered
    assert orch._verify_grounding(text, PRIMARY, CATALOGUE_BRANDS, [SECOND]) is False


def test_brand_outside_catalogue_is_not_judged_here():
    # Brands outside the catalogue cannot be checked by this guard. This is a
    # documented limitation, so the answer is not refused on that ground.
    orch = get_orchestrator()
    text = "A Gucci belt would finish this."
    assert orch._verify_grounding(text, PRIMARY, CATALOGUE_BRANDS, [SECOND]) is True


def test_empty_answer_is_refused():
    orch = get_orchestrator()
    assert orch._verify_grounding("   ", PRIMARY, CATALOGUE_BRANDS, [SECOND]) is False


# ── formatter: answer_source ─────────────────────────────────────────

def test_accepted_provider_answer_is_labelled_provider():
    orch = get_orchestrator()
    out = orch._format_response(
        "The silk slip dress works with the Massimo Dutti navy blazer.",
        "prompt", {"occasion": "Work & Business"}, "NVIDIA test-model",
        PRIMARY, CATALOGUE_BRANDS, [SECOND],
    )
    assert out["answer_source"] == "provider"
    assert out["provider_used"] == "NVIDIA test-model"
    assert "Massimo Dutti" in out["styling_advice_text"]


def test_refused_provider_answer_is_labelled_grounding_rejected(monkeypatch):
    orch = get_orchestrator()
    out = orch._format_response(
        "Wear a Zara jacket over it.", "prompt", {"occasion": "Work & Business"},
        "NVIDIA test-model", PRIMARY, CATALOGUE_BRANDS, [SECOND],
    )
    assert out["answer_source"] == "grounding_rejected"
    # The template is still a grounded one, never a claim that a provider answered.
    assert out["provider_used"].startswith("CONFIT Grounded Styling Engine")


# ── orchestrator routing: providers_unavailable vs no_provider_configured ──

def _run(prompt="Any outfit idea."):
    return asyncio.run(get_orchestrator().generate_styling_advice(prompt=prompt))


def test_no_provider_leg_available_is_no_provider_configured(monkeypatch):
    orch = get_orchestrator()
    monkeypatch.setattr(orch, "is_provider_available", lambda provider: False)
    out = _run()
    assert out["answer_source"] == "no_provider_configured"
    assert out["provider_used"].startswith("CONFIT Grounded Styling Engine")


def test_every_available_leg_failing_is_providers_unavailable(monkeypatch):
    orch = get_orchestrator()
    monkeypatch.setattr(orch, "is_provider_available", lambda provider: provider == "nvidia")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "nvidia", raising=False)
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "test-key-not-real", raising=False)

    async def boom(*_a, **_k):
        raise RuntimeError("simulated outage")

    monkeypatch.setattr(orch, "_call_nvidia_chain", boom)
    out = _run()
    assert out["answer_source"] == "providers_unavailable"
    assert out["provider_used"].startswith("CONFIT Grounded Styling Engine")


def test_successful_leg_is_provider_and_never_fallback(monkeypatch):
    orch = get_orchestrator()
    monkeypatch.setattr(orch, "is_provider_available", lambda provider: provider == "nvidia")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "nvidia", raising=False)
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "test-key-not-real", raising=False)

    async def ok(*_a, **_k):
        return ("A calm navy look with brown shoes suits a work meeting.", "stub-model")

    monkeypatch.setattr(orch, "_call_nvidia_chain", ok)
    out = _run()
    assert out["answer_source"] == "provider"
    assert out["provider_used"] == "NVIDIA stub-model"
    assert out["styling_advice_text"].startswith("A calm navy look")


def test_response_schema_exposes_answer_source():
    # The schema documents exactly these values; a rename here must update both.
    from backend.app.schemas.stylist import StylistMessageOut

    assert "answer_source" in StylistMessageOut.model_fields
