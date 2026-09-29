"""Gender-correct outfits, and occasions the shopper actually says.

THE DEFECTS, MEASURED ON PRODUCTION 2026-09-30
-----------------------------------------------
    "mens casual weekend look, shirt and trousers"
    -> outfit containing "Strappy Metallic Leather Heeled Sandals"

    "عايز حاجه رجالي للخروجه"        -> engine none, 0 outfits
    "I want a mens outfit for going out" -> engine none, 0 outfits

Two separate causes:
  * `products` had NO gender column. The only "gender" was `gender_mode`,
    a try-on render parameter describing the PHOTO. The composer had
    nothing to filter on, so it ignored the request.
  * "going out" was absent from `_OCCASION_KEYWORDS`, the most ordinary
    phrasing there is, so intent fell back to default and the stylist
    asked the shopper to rephrase.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.services.styling.garment_gender import (
    MENS,
    UNISEX,
    WOMENS,
    gender_from_query,
    infer_gender,
    is_compatible,
)
from backend.app.services.styling_engine import StylingEngine


# ── classifying the real catalogue ─────────────────────────────────────────

@pytest.mark.parametrize("title,slug,expected", [
    ("Tuxedo Peak Lapel Evening Dinner Jacket", "outerwear", MENS),
    ("Silk Jacquard Evening Necktie", "accessories", MENS),
    ("Goodyear Welted Leather Oxford Shoes", "footwear", MENS),
    ("Fine Merino Rib-Knit Polo Shirt", "tops", MENS),
    ("Strappy Metallic Leather Heeled Sandals", "footwear", WOMENS),
    ("Silk Slip Column Maxi Dress with Drape Neckline", "dresses", WOMENS),
    ("Structured Metallic Evening Box Clutch", "accessories", WOMENS),
    ("Relaxed Organic Poplin Oxford Shirt", "tops", UNISEX),
    ("Pleated Tapered Virgin Wool Trousers", "bottoms", UNISEX),
])
def test_every_real_catalogue_product_classifies_correctly(title, slug, expected):
    assert infer_gender(title, slug) == expected


def test_an_ambiguous_name_is_unisex_not_a_guess():
    """Claiming a gender we cannot read is how the original bug happened."""
    assert infer_gender("Everyday Item", None) == UNISEX
    assert infer_gender("", "") == UNISEX
    assert infer_gender(None, None) == UNISEX


# ── reading the request, in both languages ─────────────────────────────────

@pytest.mark.parametrize("query,expected", [
    ("mens casual weekend look", MENS),
    ("I want a men's outfit", MENS),
    ("عايز حاجه رجالي للخروجه", MENS),
    ("حاجة حريمي للفرح", WOMENS),
    ("women's evening dress", WOMENS),
    ("a nice outfit", None),
    ("", None),
])
def test_the_request_is_read_in_arabic_and_english(query, expected):
    assert gender_from_query(query) is expected


def test_an_unstated_gender_does_not_narrow_the_catalogue():
    """None must mean 'no filter', never a silent default to one gender."""
    assert gender_from_query("something for dinner") is None
    assert is_compatible(WOMENS, None) is True
    assert is_compatible(MENS, None) is True


# ── the filter ─────────────────────────────────────────────────────────────

def test_the_exact_production_failure_is_excluded():
    """Heeled sandals must not enter a men's outfit."""
    sandals = infer_gender("Strappy Metallic Leather Heeled Sandals", "footwear")
    assert is_compatible(sandals, MENS) is False


def test_unisex_stays_eligible_for_a_gendered_request():
    """Excluding neutral items would leave too few slots for a full outfit."""
    shirt = infer_gender("Relaxed Organic Poplin Oxford Shirt", "tops")
    assert shirt == UNISEX
    assert is_compatible(shirt, MENS) is True
    assert is_compatible(shirt, WOMENS) is True


def test_an_unknown_stored_value_does_not_empty_the_catalogue():
    """A bad backfill must degrade to permissive, not to nothing."""
    assert is_compatible("mystery", MENS) is True
    assert is_compatible(None, MENS) is True


# ── the occasion vocabulary ────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", ["going out", "outing", "drinks", "night out"])
def test_going_out_is_a_recognised_occasion(phrase):
    """The most ordinary phrasing returned zero results before this."""
    assert StylingEngine._target_occasion_keywords(phrase), phrase


def test_arabic_going_out_reaches_the_occasion_matcher():
    from backend.app.services.query_translation import apply_lexicon

    translated, hits = apply_lexicon("عايز حاجه رجالي للخروجه")
    assert hits >= 1
    assert "going out" in translated.lower(), translated
    assert StylingEngine._target_occasion_keywords(translated)


# ── end to end against the real endpoint ───────────────────────────────────

def _chat(client: TestClient, prompt: str) -> dict:
    r = client.post("/api/v1/stylist/chat", json={"prompt": prompt})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_mens_request_returns_no_womens_garment(client: TestClient) -> None:
    """The headline defect, asserted against every returned item."""
    body = _chat(client, "mens casual weekend look, shirt and trousers")

    from backend.app.models.catalog import Product
    from backend.tests.conftest import TestingSessionLocal

    offending = []
    with TestingSessionLocal() as db:
        for outfit in body.get("recommendations") or []:
            for item in outfit.get("items") or []:
                pid = item.get("product_id")
                if pid is None:
                    continue
                product = db.get(Product, pid)
                if product is None:
                    continue
                if not is_compatible(getattr(product, "gender", None), MENS):
                    offending.append((pid, item.get("product_title")))

    assert not offending, f"women's garments in a men's outfit: {offending}"


def test_an_unqualified_request_still_returns_something(client: TestClient) -> None:
    """The filter must not narrow a request that stated no gender."""
    body = _chat(client, "formal wedding look, evening")
    assert body.get("recommendations"), "the gender filter over-narrowed"
