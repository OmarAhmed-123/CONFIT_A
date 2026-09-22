"""A product with NULL cosmetic columns must not 500 the whole catalog.

WHY THIS EXISTS
---------------
Observed in production on 2026-09-22 while verifying the brand portal against
the deployed app: `GET /brand/products` returned HTTP 500 for a tenant whose
single product had NULL `dominant_hex`, `rating` and `is_featured`.

Root cause: those columns are NULLABLE in PostgreSQL, but their defaults are
declared on the ORM model (Python-side), not on the table. Any row written
outside the ORM — a SQL backfill, a bulk import, a data migration — therefore
stores NULL. The response schema declared them as strict `str` / `float` /
`bool`, so serialising such a row raised a pydantic ValidationError, which
FastAPI reports as a 500.

The blast radius is what makes this severe: the endpoint returns a LIST, so ONE
bad row takes down the ENTIRE catalog for that brand rather than degrading a
single card. A missing decorative hex code is not a server error.

These tests pin the contract: cosmetic fields tolerate NULL and fall back to the
model's declared default, while genuinely required identifiers stay strict.
"""
import pytest
from pydantic import ValidationError

from backend.app.schemas.catalog import ProductSKUOut, ProductSummaryOut


def _sku(**overrides):
    base = dict(id=1, product_id=1, sku_code="SKU-1", size="M", color="Navy",
                color_hex="#1B1F3B", price_override=None, stock_level=5,
                is_in_stock=True)
    base.update(overrides)
    return base


def _product(**overrides):
    base = dict(id=1, brand_id=1, brand_name="Brand", category_id=1,
                category_name="Outerwear", title="T", title_ar="ت", slug="t",
                base_price=100.0, currency="AED",
                thumbnail_url="https://example.com/a.jpg", color_family="Navy",
                dominant_hex="#1B1F3B", style_tags=[], occasion_tags=[],
                rating=4.8, is_featured=False)
    base.update(overrides)
    return base


class TestCosmeticNullsDoNotBreakSerialisation:
    """The exact production payload shape that produced the 500."""

    def test_product_with_all_null_cosmetics_validates(self):
        out = ProductSummaryOut.model_validate(_product(
            dominant_hex=None, rating=None, is_featured=None,
            style_tags=None, occasion_tags=None))
        assert out.dominant_hex is None
        assert out.rating is None
        # NULL must become the model's declared default, not stay None: these
        # are typed non-optional downstream.
        assert out.is_featured is False
        assert out.style_tags == []
        assert out.occasion_tags == []

    def test_sku_with_null_cosmetics_validates(self):
        out = ProductSKUOut.model_validate(_sku(
            color_hex=None, stock_level=None, is_in_stock=None))
        assert out.color_hex is None
        assert out.stock_level == 0
        assert out.is_in_stock is False

    @pytest.mark.parametrize("field", ["dominant_hex", "rating", "is_featured"])
    def test_each_nullable_field_independently(self, field):
        """One NULL field must never be enough to reject the row."""
        ProductSummaryOut.model_validate(_product(**{field: None}))

    def test_a_list_containing_one_null_row_still_serialises(self):
        """The blast-radius regression: a list response must not fail whole.

        This is the difference between a degraded card and a 500 for the entire
        brand catalog.
        """
        rows = [_product(id=1), _product(id=2, dominant_hex=None, rating=None,
                                         is_featured=None), _product(id=3)]
        out = [ProductSummaryOut.model_validate(r) for r in rows]
        assert [o.id for o in out] == [1, 2, 3]


class TestRequiredFieldsAreStillStrict:
    """Tolerance must not become permissiveness: real errors must still fail."""

    @pytest.mark.parametrize("field", ["id", "brand_id", "title", "slug", "currency"])
    def test_missing_identifier_is_rejected(self, field):
        payload = _product()
        payload.pop(field)
        with pytest.raises(ValidationError):
            ProductSummaryOut.model_validate(payload)

    @pytest.mark.parametrize("field", ["id", "sku_code", "size"])
    def test_sku_missing_identifier_is_rejected(self, field):
        payload = _sku()
        payload.pop(field)
        with pytest.raises(ValidationError):
            ProductSKUOut.model_validate(payload)

    def test_null_identifier_is_rejected(self):
        with pytest.raises(ValidationError):
            ProductSummaryOut.model_validate(_product(id=None))
