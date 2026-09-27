"""A strike-through price must be a real prior price, not a decoration.

`compare_at_price` drives the discount badge on every product card and on the
product page. If a brand can set it at or below `base_price`, the storefront
advertises a reduction that never happened — a false price claim, and a
regulated one in several markets CONFIT sells into. The import path is where
that has to be stopped, because by render time the number is already trusted.
"""
from __future__ import annotations

from backend.app.services.brand_catalog_service import BrandCatalogService


def _errors(row):
    """Field names that failed validation for a single import row.

    A real session is used because `_validate_row` resolves the category slug
    against the database; stubbing that out would also stub out the code path
    being measured.
    """
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        svc = BrandCatalogService(db)
        return [(e.field, e.message) for e in svc._validate_row(row, 1)]


BASE = {
    "title": "Wool Blazer",
    "category_slug": "outerwear",
    "base_price": "100.00",
    "color_family": "Navy",
    "thumbnail_url": "https://example.com/a.jpg",
}


def test_compare_at_price_below_base_is_rejected():
    errs = _errors({**BASE, "compare_at_price": "80.00"})
    assert any(f == "compare_at_price" for f, _ in errs), (
        "a 'was' price BELOW the selling price is not a discount and must not "
        f"be accepted; got {errs}"
    )


def test_compare_at_price_equal_to_base_is_rejected():
    errs = _errors({**BASE, "compare_at_price": "100.00"})
    assert any(f == "compare_at_price" for f, _ in errs), (
        "an unchanged price is a 0% discount; advertising it is a false claim"
    )


def test_genuine_prior_price_is_accepted():
    errs = _errors({**BASE, "compare_at_price": "150.00"})
    assert not any(f == "compare_at_price" for f, _ in errs), errs


def test_absent_compare_at_price_is_fine():
    assert not any(f == "compare_at_price" for f, _ in _errors(dict(BASE)))


def test_blank_compare_at_price_is_fine_and_clears_the_sale():
    """An empty cell must be allowed: it is how a brand ENDS a sale."""
    assert not any(f == "compare_at_price" for f, _ in _errors({**BASE, "compare_at_price": ""}))
