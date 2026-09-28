"""Try-on engine routing: licence gating, category refusal, ordering.

The assertion that matters most is the LICENCE one. Most open virtual-try-on
weights are CC BY-NC-SA, and this project has already gone to the trouble of
forking FASHN to strip a restricted parser so that exactly one engine is
commercially clean. A routing bug that let a research engine serve commercial
traffic would undo that work silently — the renders would look fine.
"""
from __future__ import annotations

import pytest

from backend.app.providers.vton.registry import (
    ENGINES,
    GarmentCategory,
    LicenseTier,
    describe_chain,
    infer_category,
    resolve_chain,
)


# ── the licence gate ───────────────────────────────────────────────────────

@pytest.mark.parametrize("category", [
    GarmentCategory.UPPER, GarmentCategory.LOWER,
    GarmentCategory.DRESS, GarmentCategory.OUTERWEAR,
])
def test_commercial_tier_admits_only_commercially_clean_engines(category):
    chain = resolve_chain(
        category, LicenseTier.COMMERCIAL,
        worker_configured=True, allow_flatlay_only=True,
    )
    for spec in chain:
        assert spec.commercial is True, (
            f"{spec.key} is licensed '{spec.license}' and must never serve "
            f"commercial traffic"
        )


def test_commercial_tier_is_empty_without_the_gpu_worker():
    """The only clean engine runs on the worker. No worker, no commercial try-on.

    Returning nothing is correct: the alternative is quietly falling back to a
    non-commercial engine, which is the exact failure this gate exists to stop.
    """
    chain = resolve_chain(
        GarmentCategory.DRESS, LicenseTier.COMMERCIAL,
        worker_configured=False, allow_flatlay_only=True,
    )
    assert chain == []


def test_pilot_tier_may_use_research_weights():
    chain = resolve_chain(GarmentCategory.DRESS, LicenseTier.PILOT)
    assert chain, "the pilot must have something to render with"
    assert any(not s.commercial for s in chain)


def test_flipping_the_tier_retires_every_research_engine():
    """One environment variable must be enough to go commercial."""
    pilot = {s.key for s in resolve_chain(
        GarmentCategory.DRESS, LicenseTier.PILOT,
        worker_configured=True, allow_flatlay_only=True)}
    commercial = {s.key for s in resolve_chain(
        GarmentCategory.DRESS, LicenseTier.COMMERCIAL,
        worker_configured=True, allow_flatlay_only=True)}
    assert commercial < pilot, "commercial must be a strict subset of pilot"
    assert all(ENGINES[k].commercial for k in commercial)


# ── accessories must be refused, not guessed ───────────────────────────────

def test_accessories_have_no_chain_in_any_tier():
    """No garment-VTON model is trained on bags, shoes or eyewear."""
    for tier in (LicenseTier.PILOT, LicenseTier.COMMERCIAL):
        assert resolve_chain(
            GarmentCategory.ACCESSORY, tier,
            worker_configured=True, allow_flatlay_only=True,
        ) == [], "an accessory must be refused, never routed to a clothing model"


# ── ordering and the flat-lay guard ────────────────────────────────────────

def test_chain_is_ordered_by_priority():
    chain = resolve_chain(
        GarmentCategory.DRESS, LicenseTier.PILOT,
        worker_configured=True, allow_flatlay_only=True)
    assert [s.priority for s in chain] == sorted(s.priority for s in chain)


def test_the_verified_engine_leads_the_pilot_chain_on_live_imagery():
    """IDM-VTON is the only engine observed to cope with on-model photos."""
    chain = resolve_chain(GarmentCategory.DRESS, LicenseTier.PILOT)
    assert chain[0].key == "idm_vton_hf"


def test_flatlay_only_engines_are_excluded_from_live_catalogue_routing():
    """OOTDiffusion painted the garment photo's BACKGROUND onto the person.

    CONFIT's catalogue is on-model lifestyle photography, so engines needing
    an isolated cut-out must stay out of the default chain.
    """
    default = {s.key for s in resolve_chain(GarmentCategory.DRESS, LicenseTier.PILOT)}
    assert "ootd_hf" not in default
    widened = {s.key for s in resolve_chain(
        GarmentCategory.DRESS, LicenseTier.PILOT, allow_flatlay_only=True)}
    assert "ootd_hf" in widened


def test_every_engine_records_how_it_was_checked():
    for key, spec in ENGINES.items():
        assert spec.verified, f"{key} has no verification note"
        assert spec.license, f"{key} has no licence recorded"


# ── category inference ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Silk Slip Column Maxi Dress with Drape Neck", GarmentCategory.DRESS),
    ("Tuxedo Peak Lapel Evening Dinner Jacket", GarmentCategory.OUTERWEAR),
    ("Tailored Italian Wool Double-Breasted Blazer", GarmentCategory.OUTERWEAR),
    ("Slim Fit Chino Trousers", GarmentCategory.LOWER),
    ("Cotton Poplin Shirt", GarmentCategory.UPPER),
    ("Structured Metallic Evening Box Clutch", GarmentCategory.ACCESSORY),
    ("Goodyear Welted Leather Oxford Shoes", GarmentCategory.ACCESSORY),
    ("Silk Jacquard Evening Necktie", GarmentCategory.ACCESSORY),
])
def test_infer_category_on_real_catalogue_titles(text, expected):
    assert infer_category(text) is expected


def test_outerwear_wins_over_a_dress_substring():
    """'Tuxedo Peak Lapel Evening Dinner Jacket' must not match 'dress'."""
    assert infer_category("Evening Dinner Jacket") is GarmentCategory.OUTERWEAR


def test_unknown_text_refuses_rather_than_guessing():
    assert infer_category("") is GarmentCategory.ACCESSORY
    assert infer_category(None) is GarmentCategory.ACCESSORY
    assert infer_category("mystery item 42") is GarmentCategory.ACCESSORY


def test_describe_chain_is_reportable_for_every_category():
    d = describe_chain(LicenseTier.PILOT, worker_configured=False)
    assert d["tier"] == "pilot"
    assert set(d["categories"]) == {c.value for c in GarmentCategory}
    assert d["categories"]["accessory"] == []
