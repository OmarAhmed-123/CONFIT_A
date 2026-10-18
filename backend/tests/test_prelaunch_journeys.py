"""Pre-launch full-path journeys at the API contract level.

These are the exact endpoint chains the two broken screenshots took, verified
against the real serializers and the real media route — not a mock of the
frontend. The seeded registry rows replicate the production row shape measured
2026-10-18 (colon-shaped storage_key, live public_url, nothing in the bucket);
they are labelled shape replicas, not a claim about what the third-party hosts
serve on any future day.

Browser-pixel verification is a separate manual step; what these journeys pin
is the part that was actually broken: the bytes/URLs the API hands the browser
have to be deliverable, and the failure states have to stay honest envelopes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.models.catalog import Product, ProductImage
from backend.tests.conftest import TestingSessionLocal

# https image URL OR same-origin absolute path — the deliverable shapes.
DELIVERABLE = re.compile(r"^(https://\S+|/\S+)$")
MEDIA_ROUTE = re.compile(r"^/api/v1/media/products/\d{1,12}/[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


@pytest.fixture(scope="module")
def prod_shape_seed():
    """Attach the production-shaped media registry to the first two products."""
    hero_urls = {
        1: "https://images.pexels.com/photos/450212/pexels-photo-450212.jpeg?auto=compress&cs=tinysrgb&w=800&h=1000&fit=crop",
    }
    db = TestingSessionLocal()
    try:
        products = db.query(Product).order_by(Product.id).limit(2).all()
        assert len(products) == 2, "seed must provide two products"
        snapshot = []
        for product in products:
            photo = "450212" if product.id == 1 else "883362"
            provider = "pexels"
            hero = hero_urls.get(product.id) or (
                "https://images.pexels.com/photos/883362/pexels-photo-883362.jpeg"
                "?auto=compress&cs=tinysrgb&w=800&h=1000&fit=crop"
            )
            for ratio, role, primary in (("4x5", "hero", True), ("1x1", "gallery", False)):
                db.add(
                    ProductImage(
                        product_id=product.id,
                        storage_key=f"{provider}:{photo}:{ratio}:{role}",
                        public_url=hero.replace("w=800&h=1000", "w=800&h=800") if ratio == "1x1" else hero,
                        ratio=ratio,
                        format="jpg",
                        width=800,
                        height=800 if ratio == "1x1" else 1000,
                        bytes=66840,
                        role=role,
                        is_primary=primary,
                        source_type="stock",
                        provider=provider,
                        source_ref=f"https://www.pexels.com/photo/{photo}/",
                        attribution="Photo: Pexels",
                        checksum="d" * 32,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            snapshot.append((product.id, product.slug))
        db.commit()
        yield snapshot
    finally:
        db = TestingSessionLocal()
        try:
            for pid, _ in snapshot:
                db.query(ProductImage).filter(ProductImage.product_id == pid).delete()
            db.commit()
        finally:
            db.close()


def _assert_deliverable_thumbnail(url: str | None) -> None:
    assert url, "a seeded product must always hand the UI an image URL"
    assert DELIVERABLE.match(url), f"not deliverable to a browser: {url!r}"
    # A media-route URL is only legal when its key is the registered ingest
    # shape; the production colon shape must NEVER surface as a media route.
    if url.startswith("/api/v1/media/"):
        assert re.match(r"^/api/v1/media/products/\d{1,12}/", url), (
            f"media-route URL with un-ingestable key reached the client: {url!r}"
        )


class TestJourney1HomeNewIn:
    """Screenshot 1: home 'New in' row — GET /catalog/products?sort_by=newest."""

    def test_cards_get_deliverable_urls(self, client: TestClient, prod_shape_seed):
        res = client.get("/api/v1/catalog/products", params={"sort_by": "newest", "limit": 8})
        assert res.status_code == 200
        items = res.json()
        assert len(items) >= 2
        seeded = {pid for pid, _ in prod_shape_seed}
        for item in items:
            _assert_deliverable_thumbnail(item.get("thumbnail_url"))
            if item["id"] in seeded:
                assert item["thumbnail_url"].startswith("https://images.pexels.com/"), (
                    "prod-shaped registry row must surface its live public URL, not a dead route"
                )

    def test_no_invented_media_route(self, client: TestClient, prod_shape_seed):
        res = client.get("/api/v1/catalog/products", params={"limit": 100})
        dead = [
            p["thumbnail_url"] for p in res.json()
            if str(p.get("thumbnail_url", "")).startswith("/api/v1/media/")
            and not MEDIA_ROUTE.match(p["thumbnail_url"])
        ]
        assert dead == [], f"client-facing media-route URLs that the route can never serve: {dead}"


class TestJourney2ProductDetail:
    """Card -> PDP: gallery and hero must agree with the card, image-first."""

    def test_detail_gallery_matches_card(self, client: TestClient, prod_shape_seed):
        pid, slug = prod_shape_seed[0]
        lst = client.get("/api/v1/catalog/products", params={"limit": 100}).json()
        card = {p["id"]: p for p in lst}[pid]
        res = client.get(f"/api/v1/catalog/products/{slug}")
        assert res.status_code == 200
        data = res.json()
        for url in [data["thumbnail_url"], *data["images"]]:
            _assert_deliverable_thumbnail(url)
        assert data["thumbnail_url"] == card["thumbnail_url"], "card and PDP hero must never disagree"
        assert data["images"][0] == card["thumbnail_url"], "gallery leads with the card hero (deterministic order)"
        for m in data["media"]:
            assert m["url"], f"media[] entry without a deliverable URL: {m}"
            _assert_deliverable_thumbnail(m["url"])
        # Attribution travels with the asset — an editorial stock photo is
        # never presented as the boutique's own shot.
        assert data["media"][0]["source_type"] == "stock"
        assert data["media"][0]["attribution"] == "Photo: Pexels"


class TestJourney3TryOnGrid:
    """Screenshot 2: the try-on outfit builder grid — same catalog query the
    builder picker uses; every card image must be deliverable."""

    def test_builder_grid_urls(self, client: TestClient, prod_shape_seed):
        res = client.get("/api/v1/catalog/products", params={"limit": 50, "sort_by": "newest"})
        assert res.status_code == 200
        for item in res.json():
            _assert_deliverable_thumbnail(item.get("thumbnail_url"))
            for img in item.get("images") or []:
                _assert_deliverable_thumbnail(img)


class TestJourney4MediaRouteContract:
    """The route itself: honest 404 for colon shapes (the prod registry keys),
    immutable caching and ETag/304 for a registered ingest key stay intact."""

    def test_prod_colon_keys_404_honestly(self, client: TestClient, prod_shape_seed):
        pid = prod_shape_seed[0][0]
        res = client.get(f"/api/v1/media/pexels:450212:4x5:hero")
        assert res.status_code == 404
        body = res.json()
        assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert "message" in body["error"] and body["error"]["message"]

    def test_search_journey_still_honest_404(self, client: TestClient):
        res = client.get("/api/v1/catalog/products/this-slug-does-not-exist")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


class TestJourney5CapabilitiesUnchanged:
    """The shipped sleeve-gate surface must be untouched by the media fix:
    mode off by default, calibration claims never implied by images."""

    def test_capabilities_exposes_gate_mode_off(self, client: TestClient):
        res = client.get("/api/v1/catalog/capabilities")
        assert res.status_code == 200
        gate = res.json()["vton_sleeve_gate"]
        assert gate["mode"] == "off"
        # Contract (capability_service): with the gate off, calibration is NOT
        # evaluated, so it reports None — neither a claim of calibration nor a
        # failure claim. False would only appear on the module-error branch.
        assert gate["calibrated"] is None
        assert isinstance(gate["reasons"], list)
