"""C03 — the PDP breadcrumb's category deep link.

THE DEFECT THIS PINS
--------------------
The product page built its category breadcrumb as
``/discover?category=<category_id>`` while the Discover filter is
slug-based — the link loaded Discover with a filter token no category
matches, silently showing an unfiltered (or empty) grid. The detail
payload simply never carried the slug, so the frontend had nothing
honest to link with.

THE CONTRACT
------------
GET /catalog/products/{slug_or_id} exposes ``category_slug`` and it is
exactly the slug of the product's category — the same value the
/catalog/categories vocabulary serves, so a breadcrumb built from it
always matches a real Discover filter state.
"""


def test_detail_payload_carries_the_real_category_slug(client):
    products = client.get("/api/v1/catalog/products").json()
    assert products, "seeded catalogue expected"
    categories = {
        c["id"]: c["slug"]
        for c in client.get("/api/v1/catalog/categories").json()
    }

    detail = client.get(
        f"/api/v1/catalog/products/{products[0]['slug']}"
    ).json()

    assert "category_slug" in detail
    assert detail["category_slug"] == categories[detail["category_id"]]
    # And the deep link it enables is a REAL filter: the slug-filtered
    # list contains this product.
    filtered = client.get(
        f"/api/v1/catalog/products?category={detail['category_slug']}"
    ).json()
    assert detail["id"] in [p["id"] for p in filtered]


def test_detail_by_numeric_id_carries_the_slug_too(client):
    products = client.get("/api/v1/catalog/products").json()
    detail = client.get(
        f"/api/v1/catalog/products/{products[0]['id']}"
    ).json()
    assert detail.get("category_slug"), "numeric-id lookups get the slug too"
