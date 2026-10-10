"""Regression tests: a published look is a complete, constraint-compliant outfit.

Covers missing trousers, missing shoes, an unavailable anchor, catalogue scarcity,
incompatible categories, and a valid alternative replacing an invalid candidate.
Real composer; candidate fixture rolled back per test; provider-free.
"""
from backend.app.models.catalog import Product
from backend.app.services.styling.rules import look_completeness
from backend.tests.test_stylist_candidate_fixture import compose, fixture_catalogue, ids_of

WORK = "Build an office look for work"
ANCHOR_NAVY = "Build an outfit around navy trousers for work"
ANCHOR_BLACK = "Build an outfit around black trousers for work"

BOTTOMS = ["fx-trousers-navy", "fx-trousers-charcoal", "fx-trousers-cream", "fx-trousers-olive", "fx-trousers-navy-2"]
FOOTWEAR = ["fx-shoes-oxford-black", "fx-shoes-suede-olive", "fx-shoes-loafer-navy"]


def _slugs(db, look):
    return {db.get(Product, i).slug for i in ids_of(look)}


def test_missing_trousers_publishes_no_look_without_a_bottom():
    with fixture_catalogue(omit=BOTTOMS) as (db, rows):
        _, outfits, meta = compose(db, rows, WORK)
        for look in outfits:
            assert look_completeness(look["items"])[0]
            assert not (_slugs(db, look) & set(BOTTOMS))
        assert outfits == []
        assert any("bottom" in r for r in meta["reasons"]), meta["reasons"]


def test_missing_shoes_publishes_no_look_without_footwear():
    with fixture_catalogue(omit=FOOTWEAR) as (db, rows):
        _, outfits, meta = compose(db, rows, WORK)
        assert outfits == []
        assert any("footwear" in r for r in meta["reasons"]), meta["reasons"]


def test_unavailable_anchor_colour_is_reported_not_ignored():
    with fixture_catalogue() as (db, rows):
        _, outfits, meta = compose(db, rows, ANCHOR_BLACK)
        assert outfits == []
        assert meta["anchor_satisfied"] is False
        assert any("black trousers" in r for r in meta["reasons"])


def test_removing_every_anchor_match_leaves_no_look_rather_than_an_unanchored_one():
    with fixture_catalogue(omit=["fx-trousers-navy", "fx-trousers-navy-2"]) as (db, rows):
        _, outfits, meta = compose(db, rows, ANCHOR_NAVY)
        assert outfits == []
        assert meta["anchor_satisfied"] is False


def test_a_valid_alternative_replaces_an_invalid_candidate():
    """Two navy trousers exist: each look gets its own, so both looks honour the anchor."""
    with fixture_catalogue() as (db, rows):
        _, outfits, meta = compose(db, rows, ANCHOR_NAVY)
        assert len(outfits) == 2, meta["reasons"]
        pants = [_slugs(db, o) & {"fx-trousers-navy", "fx-trousers-navy-2"} for o in outfits]
        assert all(len(p) == 1 for p in pants)
        assert pants[0] != pants[1]


def test_catalogue_scarcity_returns_the_complete_look_and_explains_the_rest():
    """Only one navy pair exists: a second look would need the same trousers, so it is
    not published. The reply must say why."""
    with fixture_catalogue(omit=["fx-trousers-navy-2"]) as (db, rows):
        _, outfits, meta = compose(db, rows, ANCHOR_NAVY)
        assert len(outfits) == 1
        assert look_completeness(outfits[0]["items"])[0]
        assert meta["reasons"], "the withheld look must be explained"


def test_incompatible_evening_piece_is_excluded_from_work_looks():
    extra = [("fx-tuxedo-jacket", "Tuxedo Peak Lapel Evening Jacket", 1, 3, "Midnight Black",
              ["formal", "evening"], ["wedding", "gala", "black_tie", "party"])]
    with fixture_catalogue(extra=extra) as (db, rows):
        _, outfits, meta = compose(db, rows, WORK)
        assert outfits
        for look in outfits:
            assert "fx-tuxedo-jacket" not in _slugs(db, look)
        tuxedo_id = next(r.id for r in rows if r.slug == "fx-tuxedo-jacket")
        assert str(tuxedo_id) in meta["occasion_excluded"]  # the gate named it


def test_every_published_look_has_top_or_outer_bottom_and_footwear():
    with fixture_catalogue() as (db, rows):
        _, outfits, _ = compose(db, rows, WORK)
        assert len(outfits) >= 2
        for look in outfits:
            positions = {i["position"] for i in look["items"]}
            assert "footwear" in positions and "bottom" in positions
            assert positions & {"top", "outerwear"}
