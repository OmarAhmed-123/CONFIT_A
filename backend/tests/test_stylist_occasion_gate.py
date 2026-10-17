"""Hard occasion gate: a product catalogued only for other occasions is excluded.

Unit tests use the real catalogue tag vocabulary. Provider-free."""
from types import SimpleNamespace as P

from backend.app.services.styling.occasion_gate import gate_products, is_suitable


def prod(pid, tags):
    return P(id=pid, occasion_tags=tags)


TUXEDO = prod(2, '["wedding", "gala", "black_tie", "party"]')
SANDALS = prod(7, '["wedding", "party", "gala", "dinner"]')
OXFORD_SHIRT = prod(3, '["work", "casual", "dinner", "wedding"]')
OXFORD_SHOES = prod(6, '["wedding", "work", "business", "dinner"]')
UNTAGGED = prod(99, "[]")


def test_work_excludes_evening_only_pieces():
    kept, excluded = gate_products([TUXEDO, SANDALS, OXFORD_SHIRT, OXFORD_SHOES], "Work & Business")
    assert [p.id for p in kept] == [3, 6]
    assert excluded == ["2", "7"]


def test_formal_keeps_tuxedo_and_sandals():
    kept, excluded = gate_products([TUXEDO, SANDALS, OXFORD_SHIRT], "Formal & Wedding")
    assert [p.id for p in kept] == [2, 7, 3]
    assert excluded == []


def test_casual_excludes_formal_only_tuxedo():
    assert not is_suitable(TUXEDO, "Casual Weekend")
    assert is_suitable(OXFORD_SHIRT, "Casual Weekend")


def test_untagged_products_are_never_excluded():
    assert is_suitable(UNTAGGED, "Work & Business")
    assert is_suitable(UNTAGGED, "Formal & Wedding")


def test_unstated_or_unknown_occasion_applies_no_gate():
    products = [TUXEDO, SANDALS, OXFORD_SHIRT]
    for occ in (None, "", "Smart Casual", "Something Else"):
        kept, excluded = gate_products(products, occ)
        assert kept == products and excluded == [], occ


def test_string_and_list_tags_both_supported():
    assert is_suitable(prod(1, ["work"]), "Work & Business")
    assert not is_suitable(prod(1, ["gala"]), "Work & Business")
    assert is_suitable(prod(1, "not json"), "Work & Business")  # invalid JSON -> untagged -> kept
