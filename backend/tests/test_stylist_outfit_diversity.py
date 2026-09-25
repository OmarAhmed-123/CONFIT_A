"""An "alternative" look must actually BE an alternative (defect D-2).

MEASURED DEFECT (2026-09-24, local stack, anonymous caller)
    POST /api/v1/stylist/chat {"prompt": "I need a smart casual outfit for an art
    gallery opening under $300"}

    look 101  "The Evening & Party Silk Column Silhouette"   items=[3, 4, 6]
    look 102  "The Modern Tonal Evening & Party Look"        items=[3, 4, 6]

The same three products, twice, with two different invented titles, on a code path
commented "DIVERSE & NON-OVERLAPPING", and with ``composition_warnings: []`` — i.e.
nothing anywhere told the shopper. Root cause: when the alternate pools were empty
every ``alt_*`` line fell back to ``slot_map[...][0]``, which is exactly what look 1
had already taken, and no code compared the two product sets.

WHAT THESE TESTS PIN (positive / negative / edge / no-alternative / mutation)
  * distinct products     -> the alternative is published;
  * identical products    -> it is suppressed, with a truthful reason on the record;
  * partial overlap       -> follows the documented Jaccard threshold, both sides;
  * no alternative at all -> one look is returned and the response SAYS so;
  * the threshold itself  -> a mutation that disables the check must fail these tests.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.styling.composer import OutfitComposer
from backend.app.services.styling.diversity import (
    MIN_DISTINCTNESS_OVERLAP,
    is_distinct,
    jaccard,
    product_ids,
)
from backend.tests.conftest import TestingSessionLocal


def _real_catalogues():
    """Real seeded products, in the two shapes that matter.

    Using the ORM entities (not hand-built fakes) means the slot classifier, the
    price arithmetic and the budget enforcement are the SAME code that runs in
    production. The "one per slot" catalogue reproduces the measured defect shape:
    when every alternate pool is empty, look 2 collapses into look 1.
    """
    from backend.app.core.database import SessionLocal
    from backend.app.repositories.catalog_repository import CatalogRepository
    from backend.app.services.styling.ontology import classify_product_slot
    from backend.app.services.styling.composer import OutfitComposer

    db = SessionLocal()
    try:
        products = CatalogRepository(db).filter_products(limit=100)
        assert len(products) >= 2, "the seeded test catalogue is too small for this test"

        one_per_slot = {}
        for p in products:
            slot, _ = classify_product_slot(p)
            one_per_slot.setdefault(slot, p)

        c = OutfitComposer()
        out = {}
        for label, catalogue in (("one_per_slot", list(one_per_slot.values())), ("full", products)):
            intent = c.parse_intent(prompt="smart casual work outfit", occasion_hint="work")
            meta: Dict[str, Any] = {}
            outfits = c.compose_outfits(
                available_products=catalogue, intent=intent, max_outfits=2, meta_out=meta
            )
            out[label] = {
                "outfits": [
                    {
                        "id": o["id"],
                        "title": o["title"],
                        "product_ids": sorted(product_ids(o)),
                        "alternatives_published": o.get("alternatives_published", 0),
                        "alternatives_suppressed": o.get("alternatives_suppressed", 0),
                        "warnings": list(o.get("composition_warnings") or []),
                    }
                    for o in outfits
                ],
                "meta": meta,
            }
        return out
    finally:
        db.close()



# ── a controlled catalogue that reproduces the measured shape ─────────────────
#
# The seeded test catalogue cannot reproduce the defect (it ships two footwear and
# two accessory options, so a distinct second look always exists). The measured
# production shape was: ONE usable product per slot. This fixture builds exactly
# that, and a variant with real alternatives, then removes both afterwards.
import uuid as _uuid


def _make_product(db, *, title, price, category_slug, style_tags, occasion_tags, nonce):
    from backend.app.models.catalog import Product, Category
    from backend.app.models.user import BrandProfile

    category = db.query(Category).filter(Category.slug == category_slug).first()
    if category is None:
        category = Category(name=category_slug.title(), name_ar=category_slug, slug=category_slug)
        db.add(category)
        db.flush()
    brand = db.query(BrandProfile).first()
    assert brand is not None, "the seeded test DB has no brand to attach products to"
    product = Product(
        brand_id=brand.id,
        category_id=category.id,
        title=title,
        title_ar=title,
        slug=f"diversity-{nonce}-{title.lower().replace(' ', '-')}",
        description="Test product",
        description_ar="منتج اختبار",
        base_price=price,
        currency="USD",
        material="Cotton",
        style_tags=f'["{style_tags}"]',
        occasion_tags=f'["{occasion_tags}"]',
        color_family="Navy",
        dominant_hex="#1B1F3B",
        thumbnail_url="https://example.invalid/p.jpg",
        images="[]",
        size_chart_json="{}",
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


class _ControlledCatalogue:
    """Insert a deterministic catalogue; delete it in teardown."""

    def __init__(self, *, with_alternatives: bool):
        self.with_alternatives = with_alternatives
        self.ids: List[int] = []

    def __enter__(self):
        from backend.app.core.database import SessionLocal
        self.db = SessionLocal()
        nonce = _uuid.uuid4().hex[:8]
        spec = [
            ("Base Oxford Shirt", 95.0, "tops"),
            ("Base Wool Trousers", 165.0, "bottoms"),
            ("Base Leather Oxfords", 245.0, "footwear"),
        ]
        if self.with_alternatives:
            spec += [
                ("Alt Linen Shirt", 88.0, "tops"),
                ("Alt Cotton Chinos", 120.0, "bottoms"),
                ("Alt Suede Loafers", 210.0, "footwear"),
            ]
        for title, price, slug in spec:
            product = _make_product(
                self.db, title=title, price=price, category_slug=slug,
                style_tags="smart_casual", occasion_tags="work", nonce=nonce,
            )
            self.ids.append(product.id)
        self.db.commit()
        return self

    def __exit__(self, *exc):
        from backend.app.models.catalog import Product
        try:
            self.db.query(Product).filter(Product.id.in_(self.ids)).delete(synchronize_session=False)
            self.db.commit()
        finally:
            self.db.close()
        return False

    def compose(self):
        from backend.app.repositories.catalog_repository import CatalogRepository
        from backend.app.services.styling.composer import OutfitComposer

        products = [p for p in CatalogRepository(self.db).filter_products(limit=200) if p.id in set(self.ids)]
        c = OutfitComposer()
        intent = c.parse_intent(prompt="smart casual work outfit", occasion_hint="work")
        meta: Dict[str, Any] = {}
        outfits = c.compose_outfits(available_products=products, intent=intent, max_outfits=2, meta_out=meta)
        return [
            {
                "id": o["id"],
                "product_ids": sorted(product_ids(o)),
                "warnings": list(o.get("composition_warnings") or []),
                "alternatives_suppressed": o.get("alternatives_suppressed", 0),
            }
            for o in outfits
        ], meta


# ── the unit rule ─────────────────────────────────────────────────────────────
def test_jaccard_and_threshold_boundaries():
    assert jaccard({1, 2}, {1, 2}) == 1.0
    assert jaccard({1, 2}, {3, 4}) == 0.0
    assert jaccard({1, 2, 3, 4}, {1, 2}) == 0.5          # exactly at the limit
    assert jaccard(set(), set()) == 0.0                  # no evidence, not "identical"

    primary = {"items": [{"product_id": 1}, {"product_id": 2}, {"product_id": 3}, {"product_id": 4}]}
    # 4-of-4 shared -> rejected
    assert is_distinct({"items": [{"product_id": 1}, {"product_id": 2}, {"product_id": 3}, {"product_id": 4}]}, [primary]) is False
    # 2-of-6 shared (Jaccard 0.33) -> accepted, the "same shoes, new everything else" case
    assert is_distinct({"items": [{"product_id": 3}, {"product_id": 4}, {"product_id": 9}, {"product_id": 10}]}, [primary]) is True
    # no resolvable ids -> cannot be verified, so not distinct
    assert is_distinct({"items": [{"title": "no ids"}]}, [primary]) is False


def test_the_same_products_in_a_different_order_are_still_the_same_outfit():
    """§18: order is presentation, not content.

    Two looks that contain the same products are the same outfit however the slots
    are arranged — the shopper can see they are identical. A set comparison must
    therefore be order-insensitive; a sequence comparison would publish this pair.
    """
    from backend.app.services.styling.diversity import is_distinct, jaccard

    primary = {"product_ids": [3, 4, 6], "title": "The Essential Look"}
    reordered = {"product_ids": [6, 3, 4], "title": "A Different-Looking Title"}
    assert jaccard(primary["product_ids"], reordered["product_ids"]) == 1.0
    assert not is_distinct(reordered, [primary]), (
        "the same product set in a different order was accepted as a distinct alternative"
    )


def test_the_threshold_is_the_documented_value():
    assert MIN_DISTINCTNESS_OVERLAP == 0.5, (
        "the constant changed; the docstring in styling/diversity.py explains why 0.5 "
        "was chosen and must be revisited together with it"
    )


# ── negative: the measured defect ─────────────────────────────────────────────
def test_identical_second_look_is_suppressed_and_explained():
    """NEGATIVE: one product per slot, so every alternate pool is empty — the exact
    shape that produced two identical looks under two different titles."""
    with _ControlledCatalogue(with_alternatives=False) as cat:
        outfits, meta = cat.compose()

    ids = [o["product_ids"] for o in outfits]
    assert len(ids) == len(set(map(tuple, ids))), f"the same products were published twice: {ids}"
    assert meta["requested"] == 2

    assert meta["suppressed"] == 1, f"the duplicate was published: {ids}"
    assert meta["published"] == 1
    assert "overlap" in meta["reasons"][0]
    # the suppression is on the record the CLIENT receives, not just in a log
    assert outfits[0]["alternatives_suppressed"] == 1
    assert any("alternative suppressed" in w for w in outfits[0]["warnings"])


def test_no_two_published_looks_ever_repeat_a_product_set():
    """The invariant itself, on both catalogue shapes plus the seeded one."""
    collected = {}
    for label, with_alt in (("one_per_slot", False), ("with_alternatives", True)):
        with _ControlledCatalogue(with_alternatives=with_alt) as cat:
            collected[label] = cat.compose()[0]
    for label, result in _real_catalogues().items():
        collected[f"seeded:{label}"] = result["outfits"]

    for label, outfits in collected.items():
        seen: List[set] = []
        for o in outfits:
            ids = set(o["product_ids"])
            for previous in seen:
                assert jaccard(ids, previous) < MIN_DISTINCTNESS_OVERLAP, (
                    f"[{label}] two published looks overlap too much: {ids} vs {previous}"
                )
            seen.append(ids)


# ── positive ──────────────────────────────────────────────────────────────────
def test_a_genuinely_different_second_look_is_published():
    """POSITIVE: with a real alternative present, the second look IS offered —
    so the fix cannot be 'always return one look'."""
    with _ControlledCatalogue(with_alternatives=True) as cat:
        outfits, meta = cat.compose()

    assert meta["suppressed"] == 0, meta["reasons"]
    assert len(outfits) == 2, f"a real alternative existed and was not published: {outfits}"
    first, second = set(outfits[0]["product_ids"]), set(outfits[1]["product_ids"])
    assert jaccard(first, second) < MIN_DISTINCTNESS_OVERLAP
    assert first != second


# ── edge: partial overlap follows the documented threshold, on both sides ─────
def test_partial_overlap_below_threshold_is_kept_above_is_dropped():
    primary = {"items": [{"product_id": i} for i in (1, 2, 3, 4)]}
    # 2 shared out of 6 distinct -> 0.33 -> kept
    kept = {"items": [{"product_id": i} for i in (3, 4, 5, 6)]}
    assert is_distinct(kept, [primary]) is True
    # 3 shared out of 5 distinct -> 0.6 -> dropped
    dropped = {"items": [{"product_id": i} for i in (2, 3, 4, 5)]}
    assert is_distinct(dropped, [primary]) is False


# ── no alternative at all: truthful fallback, not silence ─────────────────────
def test_when_no_alternative_exists_the_answer_says_so():
    """Suppression is only honest if it is VISIBLE — otherwise one look is returned
    and the client cannot tell it apart from 'we only ever had one'."""
    with _ControlledCatalogue(with_alternatives=False) as cat:
        outfits, meta = cat.compose()
    assert meta["suppressed"] == 1
    reason = meta["reasons"][0]
    assert "not offered twice" in reason
    assert outfits[0].get("alternatives_published", 0) == 0


# ── the endpoint: the record the shopper's client actually receives ───────────
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_endpoint_suppresses_the_duplicate_and_reports_it(client: TestClient):
    import json
    from backend.app.core.config import settings
    from unittest.mock import patch

    with patch.object(settings, "AI_PROVIDERS", ""):
        r = client.post(
            "/api/v1/stylist/chat",
            json={"prompt": "I need a smart casual outfit for an art gallery opening under $300",
                  "occasion": "work", "budget_limit": 300},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    recs = body["recommendations"]

    ids = [sorted(product_ids(o)) for o in recs]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            assert a != b, f"the API published the same product set twice: {ids}"

    published = body["intent_detected"].get("alternatives")
    if len(recs) == 1:
        assert published, "a suppressed alternative must be reported, not hidden"
        assert published["suppressed"] >= 1

    # and the stored record carries it too
    db = TestingSessionLocal()
    try:
        from backend.app.models.stylist import StylistMessage
        row = db.query(StylistMessage).filter(StylistMessage.id == body["id"]).one()
        stored = json.loads(row.intent_json or "{}")
    finally:
        db.close()
    if len(recs) == 1:
        assert stored.get("alternatives"), "the suppression was not persisted with the message"
