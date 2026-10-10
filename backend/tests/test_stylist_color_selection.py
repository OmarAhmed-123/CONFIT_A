"""Prove that image-derived colour changes the ACTUAL selected products.

Real `StylingEngine` composer over the deterministic candidate fixture
(test_stylist_candidate_fixture.py). Assertions are on product slugs/IDs, not on
scores or wording. Provider-free; the fixture is rolled back after each test.
"""
from backend.app.services.styling.constraints import palette_bonus
from backend.app.services.styling.occasion_gate import is_suitable
from backend.app.services.styling.rules import look_completeness
from backend.app.models.catalog import Product
from backend.tests.test_stylist_candidate_fixture import (
    compose, fixture_catalogue, ids_of,
)

WORK = "Build an office look for work"
ANCHOR = "Build an outfit around navy trousers for work"


def _slugs(db, outfits):
    return [sorted(db.get(Product, i).slug for i in ids_of(o)) for o in outfits]


# --- baseline with NO photo palette -------------------------------------------

def test_baseline_without_palette_selects_these_products():
    with fixture_catalogue() as (db, rows):
        _, outfits, meta = compose(db, rows, WORK, palette=[])
        assert meta["reasons"] == []
        assert _slugs(db, outfits) == [
            ["fx-blazer-navy", "fx-shirt-white", "fx-shoes-suede-olive", "fx-trousers-navy"],
            ["fx-blazer-olive", "fx-shirt-cream", "fx-shoes-oxford-black", "fx-tie-navy", "fx-trousers-charcoal"],
        ]


# --- palettes change the selection --------------------------------------------

def test_navy_palette_changes_shoes_and_second_look_trousers():
    with fixture_catalogue() as (db, rows):
        _, base, _ = compose(db, rows, WORK, palette=[])
        _, navy, _ = compose(db, rows, WORK, palette=["navy"])
        base_s, navy_s = _slugs(db, base), _slugs(db, navy)
        assert navy_s[0] == ["fx-blazer-navy", "fx-shirt-white", "fx-shoes-loafer-navy", "fx-trousers-navy"]
        assert navy_s[1] == ["fx-blazer-olive", "fx-shirt-cream", "fx-shoes-oxford-black", "fx-tie-navy", "fx-trousers-navy-2"]
        assert navy_s != base_s


def test_olive_palette_builds_an_all_olive_look_and_differs_from_baseline():
    with fixture_catalogue() as (db, rows):
        _, base, _ = compose(db, rows, WORK, palette=[])
        _, olive, _ = compose(db, rows, WORK, palette=["olive"])
        first = _slugs(db, olive)[0]
        assert first == ["fx-blazer-olive", "fx-shirt-olive", "fx-shoes-suede-olive", "fx-trousers-olive"]
        assert _slugs(db, olive) != _slugs(db, base)


def test_burgundy_palette_selects_burgundy_pieces():
    with fixture_catalogue() as (db, rows):
        _, outfits, _ = compose(db, rows, WORK, palette=["burgundy"])
        assert _slugs(db, outfits) == [
            ["fx-blazer-burgundy", "fx-shirt-burgundy", "fx-shoes-loafer-navy", "fx-trousers-navy"],
            ["fx-blazer-navy", "fx-shirt-white", "fx-shoes-oxford-black", "fx-tie-burgundy", "fx-trousers-charcoal"],
        ]


def test_three_palettes_give_three_different_primary_looks():
    with fixture_catalogue() as (db, rows):
        primaries = []
        for pal in (["navy"], ["olive"], ["burgundy"]):
            _, outfits, _ = compose(db, rows, WORK, palette=pal)
            primaries.append(tuple(_slugs(db, outfits)[0]))
        assert len(set(primaries)) == 3


# --- neutrals are not penalised for being neutral -------------------------------

def test_neutral_colours_score_no_penalty_under_any_palette():
    for pal in (["navy"], ["olive"], ["burgundy"], ["black"]):
        for neutral in ("Optic White", "Ivory Cream", "Charcoal Grey", "Obsidian Black"):
            assert palette_bonus(neutral, pal) >= 0, (neutral, pal)


def test_neutral_pieces_remain_selected_under_a_clashing_palette():
    with fixture_catalogue() as (db, rows):
        _, outfits, _ = compose(db, rows, WORK, palette=["burgundy"])
        all_ids = set().union(*(ids_of(o) for o in outfits))
        white = next(r.id for r in rows if r.slug == "fx-shirt-white")
        assert white in all_ids


# --- hard constraints hold under every palette -----------------------------------

def test_every_palette_keeps_anchor_occasion_completeness_and_grounding():
    for pal in ([], ["navy"], ["olive"], ["burgundy"]):
        with fixture_catalogue() as (db, rows):
            fixture_ids = {r.id for r in rows}
            intent, outfits, meta = compose(db, rows, ANCHOR, palette=pal)
            assert outfits, pal
            navy_trousers = {r.id for r in rows if r.slug.startswith("fx-trousers-navy")}
            for look in outfits:
                ids = ids_of(look)
                assert ids and ids <= fixture_ids, "every item must be a real fixture product"
                assert ids & navy_trousers, ("anchor violated", pal, look["title"])
                assert look_completeness(look["items"])[0], ("incomplete", pal, look["title"])
                for pid in ids:  # every piece must pass the work occasion gate
                    assert is_suitable(db.get(Product, pid), "Work & Business"), pid


def test_palette_cannot_override_the_anchor_even_when_it_favours_other_trousers():
    with fixture_catalogue() as (db, rows):
        _, outfits, _ = compose(db, rows, ANCHOR, palette=["olive"])  # olive pulls to olive trousers
        for look in outfits:
            slugs = {db.get(Product, i).slug for i in ids_of(look)}
            assert slugs & {"fx-trousers-navy", "fx-trousers-navy-2"}
            assert "fx-trousers-olive" not in slugs
