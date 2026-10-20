"""A shopper's product page must not publish internal inventory keys.

MEASURED DEFECT (2026-10-20, production, read-only)
---------------------------------------------------
``GET /api/v1/catalog/products/silk-slip-column-maxi-dress`` — public,
unauthenticated — returned::

    "skus": [{ "id": 13, "sku_code": "REISS-DRS-GLD-6", "size": "6", ... }]

The product is sold by *Riven Studio*; "REISS" is the retired trademark the
brand was renamed away from in this same branch. So the public catalogue was
still naming the old identity, and doing it through an internal inventory key
that no storefront component reads: `ProductDetailView` uses id, size, colour,
price and stock, never the code.

(The previous audit recorded that SKU codes were "not exposed in the public
catalog payload today". That was wrong — this test exists because the check was
never actually made against the live response.)

WHY THE FIX IS AT THE SERIALIZER
--------------------------------
Renaming the rows would rewrite identifiers that historical order lines,
carts, reservations and store inventories all point at (21 / 34 / 29 / 46 rows
respectively in production). The identity of a past transaction is not a
cosmetic field. Withholding the code from the *public* representation removes
what should never have been published, while the brand-owner and admin
surfaces — which legitimately operate the catalogue by SKU — keep receiving it.
"""
from __future__ import annotations

import pytest

PUBLIC_SKU_FIELDS = {"id", "product_id", "size", "color", "color_hex",
                     "price_override", "stock_level", "is_in_stock"}


@pytest.fixture()
def detail_payload(client):
    products = client.get("/api/v1/catalog/products").json()
    assert products, "seeded catalogue expected"
    return client.get(f"/api/v1/catalog/products/{products[0]['slug']}").json()


def test_public_product_page_carries_no_sku_code_value(detail_payload):
    """The KEY may remain (the shared response model declares it, defaulted to
    None); the VALUE must never be published."""
    assert detail_payload["skus"], "seeded product expected to have SKUs"
    for sku in detail_payload["skus"]:
        assert sku.get("sku_code") is None, (
            f"public payload leaked an internal inventory key: {sku.get('sku_code')}"
        )


def test_public_product_page_keeps_everything_a_shopper_selects(detail_payload):
    """Withholding the code must not withhold the variant."""
    for sku in detail_payload["skus"]:
        assert PUBLIC_SKU_FIELDS.issubset(sku), (
            f"the shopper-facing SKU contract lost a field: {sorted(sku)}"
        )
        assert sku["size"] and sku["color"]
        assert isinstance(sku["is_in_stock"], bool)


def test_no_retired_brand_initial_leaks_through_the_detail_endpoint(detail_payload):
    """The whole point: the old trademarks must not appear anywhere in it."""
    import json

    body = json.dumps(detail_payload)
    for retired in ("REISS-", "MD-", "COS-", "ARK-"):
        assert retired not in body, f"{retired!r} still reaches the public product page"

# The tenant-side half of this contract is covered in
# test_catalog_schema_null_tolerance.py::test_tenant_surfaces_still_carry_sku_code,
# which asserts the model still serialises a populated code when one is set.
