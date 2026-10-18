"""Product media: registry -> storefront URLs -> served bytes.

WHAT THESE TESTS PIN DOWN (each one is a defect measured in production on
2026-10-08, so a regression here is a regression the customer would see):

1. the product page serves the REGISTERED derived set, in the gallery order
   (primary 4:5 first, then the ratio ladder, master never in ``images``);
2. a product with no registered rows still renders its legacy images — a page
   must not go blank because the media pass has not reached that product;
3. the list endpoint's card hero comes from the registry too, resolved in ONE
   grouped query rather than a per-product fan-out;
4. ``GET /api/v1/media/...`` serves BYTES for a registered key with immutable
   caching and an ETag taken from the row's checksum, answers 304 on a matching
   If-None-Match, and refuses anything that is not a registered key (unknown
   key, traversal attempt, a key that belongs to another prefix);
5. when object storage is unconfigured the route answers 501 — never a blank
   200 and never a 500.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.models.catalog import Product, ProductImage
from backend.app.services import product_media_service as pms
from backend.tests.conftest import TestingSessionLocal


def _add_rows(db, product_id: int, keys: list[tuple[str, str, bool]]) -> None:
    for key, ratio, primary in keys:
        db.add(
            ProductImage(
                product_id=product_id,
                storage_key=key,
                public_url=pms.media_url_for_key(key),
                ratio=ratio,
                format="jpg",
                width=1200,
                height=1500 if ratio == "4x5" else 1200,
                bytes=1000,
                role="hero" if primary else "gallery",
                is_primary=primary,
                source_type="stock",
                provider="unsplash",
                source_ref="https://images.unsplash.com/example",
                attribution="Unsplash",
                checksum=("a" * 32),
                created_at=datetime.now(timezone.utc),
            )
        )
    db.commit()


@pytest.fixture
def product_with_media():
    """A seeded product carrying a full 5-ratio set, cleaned up afterwards."""
    db = TestingSessionLocal()
    try:
        product = db.query(Product).order_by(Product.id).first()
        assert product is not None, "seed data must provide at least one product"
        pid, slug = product.id, product.slug
        keys = [
            (f"products/{pid}/{pid}-4x5.jpg", "4x5", True),
            (f"products/{pid}/{pid}-1x1.jpg", "1x1", False),
            (f"products/{pid}/{pid}-3x2.jpg", "3x2", False),
            (f"products/{pid}/{pid}-16x9.jpg", "16x9", False),
            (f"products/{pid}/{pid}-master.jpg", "master", False),
        ]
        _add_rows(db, pid, keys)
        yield {"id": pid, "slug": slug, "keys": keys}
    finally:
        db.query(ProductImage).filter(ProductImage.product_id == pid).delete()
        db.commit()
        db.close()


def test_product_page_serves_registered_set_in_gallery_order(client: TestClient, product_with_media):
    pid, slug = product_with_media["id"], product_with_media["slug"]
    res = client.get(f"/api/v1/catalog/products/{slug}")
    assert res.status_code == 200, res.text
    data = res.json()

    expected_images = [
        f"/api/v1/media/products/{pid}/{pid}-4x5.jpg",
        f"/api/v1/media/products/{pid}/{pid}-1x1.jpg",
        f"/api/v1/media/products/{pid}/{pid}-3x2.jpg",
        f"/api/v1/media/products/{pid}/{pid}-16x9.jpg",
    ]
    assert data["images"] == expected_images, "gallery order/claims drifted"
    assert f"/api/v1/media/products/{pid}/{pid}-master.jpg" not in data["images"], "master must not be a gallery frame"
    assert data["thumbnail_url"] == expected_images[0], "card hero must be the registered primary"

    media = data["media"]
    assert len(media) == 5
    assert [m["ratio"] for m in media] == ["4x5", "1x1", "3x2", "16x9", "master"]
    assert media[0]["is_primary"] is True
    first = media[0]
    assert first["bytes"] == 1000 and first["width"] == 1200 and first["height"] == 1500
    # Attribution travels with the asset: a stock photo must stay labelled.
    assert first["source_type"] == "stock" and first["attribution"] == "Unsplash"


def test_legacy_images_remain_when_no_registered_rows(client: TestClient):
    db = TestingSessionLocal()
    try:
        product = (
            db.query(Product)
            .filter(~Product.id.in_(db.query(ProductImage.product_id)))
            .order_by(Product.id)
            .first()
        )
        assert product is not None, "expected at least one product without media rows"
        # Mirror the API's documented precedence (catalog_controller): the
        # product's legacy `images` JSON wins when present; the thumbnail is
        # the fallback only for products that carry no images list. The
        # original assertion assumed thumbnail == images[0], which seed pass
        # #323 (verified product visuals) legitimately decoupled.
        import json as _json
        try:
            parsed = _json.loads(product.images) if product.images else []
        except (TypeError, ValueError):
            parsed = []
        legacy = parsed if isinstance(parsed, list) and parsed else [product.thumbnail_url]
        expected_thumb = product.thumbnail_url
        slug = product.slug
    finally:
        db.close()

    res = client.get(f"/api/v1/catalog/products/{slug}")
    assert res.status_code == 200
    data = res.json()
    assert data["media"] == []
    assert data["images"] == legacy
    assert data["thumbnail_url"] == expected_thumb  # detail thumbnail is the product row's own


def test_list_endpoint_uses_registered_hero(client: TestClient, product_with_media):
    pid = product_with_media["id"]
    res = client.get("/api/v1/catalog/products", params={"limit": 100})
    assert res.status_code == 200
    cards = {p["id"]: p for p in res.json()}
    assert pid in cards, "seeded product should be listed"
    assert cards[pid]["thumbnail_url"] == f"/api/v1/media/products/{pid}/{pid}-4x5.jpg"


def test_media_route_serves_registered_bytes(client: TestClient, product_with_media, monkeypatch):
    pid = product_with_media["id"]
    key = f"products/{pid}/{pid}-4x5.jpg"
    payload = b"\xff\xd8\xff\xe0-jpeg-bytes"
    monkeypatch.setattr("backend.app.controllers.media_controller.read_media_object", lambda k: payload)

    res = client.get(f"/api/v1/media/{key}")
    assert res.status_code == 200
    assert res.content == payload
    assert res.headers["content-type"] == "image/jpeg"
    assert "immutable" in res.headers["cache-control"]
    assert res.headers["etag"] == '"' + "a" * 32 + '"'
    assert res.headers["x-media-ratio"] == "4x5"

    # A repeat view with the same ETag costs no bytes: 304.
    again = client.get(f"/api/v1/media/{key}", headers={"If-None-Match": res.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/media/products/99999/99999-4x5.jpg",   # not registered
        "/api/v1/media/products/1/../1-4x5.jpg",        # traversal
        "/api/v1/media/wardrobe/u1/secret.jpg",         # different prefix
        "/api/v1/media/etc/passwd",                     # not a media key at all
    ],
)
def test_media_route_refuses_anything_unregistered(client: TestClient, product_with_media, path):
    res = client.get(path)
    assert res.status_code == 404, f"{path} must not be servable"
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_media_route_is_honest_when_storage_is_unconfigured(client: TestClient, product_with_media, monkeypatch):
    from backend.app.core.exceptions import FeatureNotConfiguredError

    pid = product_with_media["id"]
    key = f"products/{pid}/{pid}-4x5.jpg"

    def _boom(_k):
        raise FeatureNotConfiguredError("product_media", hint="no bucket")

    monkeypatch.setattr("backend.app.controllers.media_controller.read_media_object", _boom)
    res = client.get(f"/api/v1/media/{key}")
    assert res.status_code == 501, "an unconfigured store must say so, not pretend"
    assert res.json()["error"]["code"] == "FEATURE_NOT_CONFIGURED"


def test_media_route_404_when_object_missing_although_registered(client: TestClient, product_with_media, monkeypatch):
    pid = product_with_media["id"]
    key = f"products/{pid}/{pid}-1x1.jpg"
    monkeypatch.setattr("backend.app.controllers.media_controller.read_media_object", lambda k: None)
    res = client.get(f"/api/v1/media/{key}")
    assert res.status_code == 404


def test_order_media_is_deterministic_and_ratio_aware():
    class R:  # minimal stand-in for ProductImage
        def __init__(self, rid, ratio, fmt, primary=False):
            self.id, self.ratio, self.format, self.is_primary = rid, ratio, fmt, primary

    rows = [R(4, "16x9", "jpg"), R(2, "1x1", "webp"), R(1, "4x5", "jpg", True), R(3, "3x2", "jpg")]
    ordered = [r.ratio for r in pms.order_media(rows)]
    assert ordered == ["4x5", "1x1", "3x2", "16x9"]
    assert [r.ratio for r in pms.order_media(rows)] == ordered, "must be deterministic"
    assert [r.ratio for r in pms.order_media(rows)][0] != "16x9"


# ── 2026-10-18 production defect: upstream-source rows must render their
# verified public URL, never a media-route URL for bytes that were never
# ingested. These fixtures mirror the REAL production row shape measured on
# 2026-10-18 (product_images.storage_key = "provider:photo_id:ratio:role",
# public_url = live Pexels/Unsplash or same-origin static file; 54 rows, zero
# keys in the products/<id>/ ingest shape). They are data-shape replicas for a
# contract test — not a claim about current prod content.


def _add_upstream_rows(db, product_id: int, rows: list[tuple[str, str, str, bool]]) -> None:
    for key, public_url, ratio, primary in rows:
        db.add(
            ProductImage(
                product_id=product_id,
                storage_key=key,
                public_url=public_url,
                ratio=ratio,
                format="jpg",
                width=800,
                height=1000,
                bytes=66840,
                role="hero" if primary else "gallery",
                is_primary=primary,
                source_type="stock",
                provider="pexels",
                source_ref="https://www.pexels.com/photo/883362/",
                attribution="Photo: Pexels",
                checksum="b" * 32,
                created_at=datetime.now(timezone.utc),
            )
        )
    db.commit()


def test_upstream_source_rows_render_public_url_not_dead_media_route(client: TestClient):
    """Colon-shaped keys (the prod reality) resolve to their live public_url."""
    hero = "https://images.pexels.com/photos/883362/pexels-photo-883362.jpeg?auto=compress&cs=tinysrgb&w=800&h=1000&fit=crop"
    square = "https://images.pexels.com/photos/883362/pexels-photo-883362.jpeg?auto=compress&cs=tinysrgb&w=800&h=800&fit=crop"
    db = TestingSessionLocal()
    try:
        product = db.query(Product).order_by(Product.id).first()
        assert product is not None
        pid, slug = product.id, product.slug
        rows = [
            ("pexels:883362:4x5:hero", hero, "4x5", True),
            ("pexels:883362:1x1:gallery", square, "1x1", False),
            ("pexels:883362:master:gallery", "", "master", False),  # empty = registered, undeliverable
        ]
        _add_upstream_rows(db, pid, rows)
    finally:
        db.close()
    try:
        res = client.get(f"/api/v1/catalog/products/{slug}")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["thumbnail_url"] == hero, "card hero must be the row's verified live URL"
        assert data["images"] == [hero, square], "gallery must skip master and unreachable rows"
        urls = [m["url"] for m in data["media"]]
        assert "/api/v1/media/" not in urls, "no media-route URL may be invented for un-ingested keys"
        assert None not in urls and all(u for u in urls)
        # Whitelist invariant: the media route still refuses these keys —
        # correctness lives in not pointing clients at it.
        blocked = client.get("/api/v1/media/pexels:883362:4x5:hero")
        assert blocked.status_code == 404
        lst = client.get("/api/v1/catalog/products", params={"limit": 100}).json()
        card = {p["id"]: p for p in lst}[pid]
        assert card["thumbnail_url"] == hero, "list cards and the detail page must agree"
    finally:
        db = TestingSessionLocal()
        try:
            db.query(ProductImage).filter(ProductImage.product_id == pid).delete()
            db.commit()
        finally:
            db.close()


def test_upstream_row_without_deliverable_url_falls_back_to_legacy(client: TestClient):
    """No ingest key AND no usable public_url -> no URL is invented; the
    serializer falls back to the legacy column (never a blank or a dead img)."""
    db = TestingSessionLocal()
    try:
        product = db.query(Product).order_by(Product.id).first()
        pid, slug = product.id, product.slug
        legacy_thumb = product.thumbnail_url
        _add_upstream_rows(db, pid, [("pexels:883362:4x5:hero", "", "4x5", True)])
    finally:
        db.close()
    try:
        res = client.get(f"/api/v1/catalog/products/{slug}")
        assert res.status_code == 200
        data = res.json()
        assert data["media"] == []
        assert data["thumbnail_url"] == legacy_thumb, "detail thumbnail must fall back to the legacy column"
        assert not data["thumbnail_url"].startswith("/api/v1/media/"), "never a dead media-route URL"
        assert data["images"], "legacy images must still render"
        assert all(not u.startswith("/api/v1/media/") for u in data["images"])
    finally:
        db = TestingSessionLocal()
        try:
            db.query(ProductImage).filter(ProductImage.product_id == pid).delete()
            db.commit()
        finally:
            db.close()


def test_display_url_for_row_rule_is_exhaustive():
    """The capability ladder in one unit: ingest key > https/relative public
    URL > nothing. Insecure, protocol-relative and bogus values never pass."""
    from types import SimpleNamespace

    def row(**kw):
        return SimpleNamespace(**kw)

    svc = pms
    assert svc.display_url_for_row(row(storage_key="products/7/7-4x5.jpg", public_url="https://x/y.jpg")) == "/api/v1/media/products/7/7-4x5.jpg"
    assert svc.display_url_for_row(row(storage_key="pexels:1:4x5:hero", public_url="https://images.pexels.com/a.jpg")) == "https://images.pexels.com/a.jpg"
    assert svc.display_url_for_row(row(storage_key="generated:slug:4x5:hero", public_url="/product-media/slug/hero-4x5.jpg")) == "/product-media/slug/hero-4x5.jpg"
    assert svc.display_url_for_row(row(storage_key="pexels:1:4x5:hero", public_url="http://insecure.example/a.jpg")) is None
    assert svc.display_url_for_row(row(storage_key="pexels:1:4x5:hero", public_url="//evil.example/a.jpg")) is None
    assert svc.display_url_for_row(row(storage_key="pexels:1:4x5:hero", public_url="ftp://nope")) is None
    assert svc.display_url_for_row(row(storage_key="pexels:1:4x5:hero", public_url=None)) is None
    assert svc.display_url_for_row(row(storage_key="products/7/../../etc/passwd", public_url=None)) is None
    assert svc.is_serveable_storage_key("products/7/7-4x5.jpg") is True
    assert svc.is_serveable_storage_key("products/7/../8/8.jpg") is False
    assert svc.is_serveable_storage_key(None) is False
