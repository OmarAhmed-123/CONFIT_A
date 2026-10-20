"""The storefront's image URLs must resolve — the invariant production broke.

MEASURED DEFECT (2026-10-20, production, read-only)
---------------------------------------------------
``GET /api/v1/catalog/products`` served ``thumbnail_url`` values like
``/api/v1/media/pexels:450212:4x5:hero``. The media route accepts only
``products/{id}/{file}`` (``media_controller._KEY_RE``), so the whitelist
rejected every card image before the database was queried: 10 distinct 404s and
14 "Image unavailable" placeholders on the home page alone.

The registry was not empty (54 rows) and the bucket was not empty (120 objects),
but they used different names and **none of the 54 rows' byte counts matched any
object in the bucket** — the files had never been uploaded. The registry recorded
intent, and the URL streamed to the browser therefore named an object that could
not exist.

These tests pin the invariant that closes it:

  A. the key the API derives is a key the media route accepts (no drift);
  B. a registered row exists only after its bytes were stored, and the
     metadata describes the stored bytes;
  C. a seeded product's ``thumbnail_url`` from the LIST endpoint really serves
     200 + ``image/*`` — the end-to-end path a shopper's browser takes;
  D. an unapproved image host is refused rather than uploaded;
  E. the brand catalogue import now registers media (the gap that let an
     imported product exist with a thumbnail_url and no registry row).
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.controllers.media_controller import _KEY_RE
from backend.app.models.catalog import Product, ProductImage
from backend.app.services import media_materialization_service as mms
from backend.app.services.media_materialization_service import (
    MediaMaterializationError,
    MediaMaterializationService,
    MediaSourceNotApproved,
    canonical_storage_key,
    provider_for_url,
)
from backend.tests.conftest import TestingSessionLocal


# --------------------------------------------------------------------------
# collaborators: a bucket in a dict, a source image in memory
# --------------------------------------------------------------------------
class FakeStorage:
    """Minimal object store: ``store`` writes, ``read`` reads, keys round-trip."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def store(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return key

    def read(self, key: str):
        return self.objects.get(key)


def source_image_bytes(width: int = 900, height: int = 1400, colour=(30, 40, 60)) -> bytes:
    img = Image.new("RGB", (width, height), colour)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture()
def seeded_product():
    db = TestingSessionLocal()
    try:
        product = db.query(Product).order_by(Product.id).first()
        assert product is not None, "seed data must provide at least one product"
        pid = product.id
        original_thumb = product.thumbnail_url
        yield db, product
    finally:
        db.query(ProductImage).filter(ProductImage.product_id == pid).delete()
        db.commit()
        db.close()


# --------------------------------------------------------------------------
# A. no drift between the URL we emit and the key the route accepts
# --------------------------------------------------------------------------
def test_derived_key_is_accepted_by_the_media_route():
    """The bug was two regexes in two files disagreeing. Pin them together."""
    for pid in (1, 7, 12, 999999):
        for ratio in ("4x5", "1x1", "3x2", "16x9", "master"):
            for fmt in ("jpeg", "webp"):
                key = canonical_storage_key(pid, ratio, fmt)
                assert _KEY_RE.match(key), f"media route would reject its own key: {key}"


def test_legacy_label_keys_are_not_servable():
    """'pexels:450212:4x5:hero' was a label, never a key — and must be seen as such."""
    legacy = ProductImage(product_id=1, storage_key="pexels:450212:4x5:hero")
    canonical = ProductImage(product_id=1, storage_key="products/1/1-4x5.jpg")
    assert mms.storage_key_for_row(legacy) is None
    assert mms.storage_key_for_row(canonical) == "products/1/1-4x5.jpg"


# --------------------------------------------------------------------------
# B. a row describes bytes that exist
# --------------------------------------------------------------------------
def test_materialize_registers_rows_whose_metadata_describes_stored_bytes(seeded_product):
    db, product = seeded_product
    storage = FakeStorage()
    source = source_image_bytes()
    service = MediaMaterializationService(db, storage=storage, fetch=lambda url: source)

    rows = service.materialize(
        product,
        "https://images.pexels.com/photos/450212/pexels-photo-450212.jpeg",
        source_type="stock",
        provider="pexels",
        source_ref="https://www.pexels.com/photo/450212/",
        attribution="Photo: Pexels",
    )

    assert len(rows) == 10, "5 ratios x (jpeg, webp)"
    for row in rows:
        assert _KEY_RE.match(row.storage_key), row.storage_key
        assert row.storage_key in storage.objects, "registered a key that holds no bytes"
        stored = storage.objects[row.storage_key]
        assert row.bytes == len(stored), "byte count must describe the stored object"
        assert row.checksum == mms.checksum_of(stored), "checksum must describe the stored object"
        assert (row.width, row.height) == mms.RATIO_DIMENSIONS[row.ratio]
        assert row.source_type == "stock"
        assert row.provider == "pexels"
        assert row.attribution == "Photo: Pexels"

    primaries = [r for r in rows if r.is_primary]
    assert len(primaries) == 1 and primaries[0].ratio == "4x5"
    assert primaries[0].storage_key.endswith(".jpg")
    # the legacy column must agree with the registry hero
    assert product.thumbnail_url == primaries[0].public_url


def test_materialize_refuses_when_the_upload_fails(seeded_product):
    """Half a media set is worse than none: nothing is registered on failure."""
    db, product = seeded_product

    class BrokenStorage(FakeStorage):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def store(self, key, data):
            self.calls += 1
            if self.calls == 3:
                raise OSError("bucket rejected the write")
            return super().store(key, data)

    service = MediaMaterializationService(db, storage=BrokenStorage(), fetch=lambda url: source_image_bytes())
    with pytest.raises(MediaMaterializationError):
        service.materialize(product, "https://images.unsplash.com/photo-1", provider="unsplash")

    assert db.query(ProductImage).filter(ProductImage.product_id == product.id).count() == 0


# --------------------------------------------------------------------------
# C. the end-to-end path the browser takes
# --------------------------------------------------------------------------
def test_seeded_product_thumbnail_url_from_the_list_endpoint_serves_an_image(
    client: TestClient, seeded_product, monkeypatch
):
    """Card image → 200 image/*. This is the exact journey that 404'd in production."""
    db, product = seeded_product
    storage = FakeStorage()
    MediaMaterializationService(db, storage=storage, fetch=lambda url: source_image_bytes()).materialize(
        product,
        "https://images.pexels.com/photos/450212/pexels-photo-450212.jpeg",
        provider="pexels",
        attribution="Photo: Pexels",
    )

    listing = client.get("/api/v1/catalog/products", params={"sort_by": "newest", "limit": 50})
    assert listing.status_code == 200
    card = next((p for p in listing.json() if p["id"] == product.id), None)
    assert card is not None, "the materialised product must appear in the list"
    url = card["thumbnail_url"]
    assert url.startswith("/api/v1/media/"), f"card must use the registry hero, got {url}"

    # Serve from the same fake bucket the materialiser wrote to.
    monkeypatch.setattr(
        "backend.app.controllers.media_controller.read_media_object",
        lambda key: storage.read(key),
    )
    response = client.get(url)
    assert response.status_code == 200, f"{url} answered {response.status_code} — the production defect"
    assert response.headers["content-type"].startswith("image/")
    assert len(response.content) > 0


# --------------------------------------------------------------------------
# D. only approved hosts
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://images.pexels.com/photos/1/x.jpeg", "pexels"),
        ("https://images.unsplash.com/photo-1", "unsplash"),
    ],
)
def test_approved_hosts_map_to_a_provider(url, expected):
    assert provider_for_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/shirt.jpg",
        "https://cdn.retailer.com/img/1.jpg",
        "https://images.pexels.com.evil.io/x.jpg",   # look-alike host
        "http://169.254.169.254/latest/meta-data",   # SSRF probe
        "",
    ],
)
def test_unapproved_hosts_are_refused(url):
    with pytest.raises(MediaSourceNotApproved):
        provider_for_url(url)


def test_stock_source_cannot_bypass_the_allowlist_by_asserting_a_provider(seeded_product):
    """A caller-supplied provider string is not evidence of a licence."""
    db, product = seeded_product
    service = MediaMaterializationService(db, storage=FakeStorage(), fetch=lambda url: source_image_bytes())
    with pytest.raises(MediaSourceNotApproved):
        service.materialize(
            product,
            "https://cdn.retailer.example/shirt.jpg",
            source_type="stock",
            provider="pexels",
        )


# --------------------------------------------------------------------------
# E. the import registers media (the gap)
# --------------------------------------------------------------------------
def test_catalog_import_registers_product_images(seeded_product, monkeypatch):
    """An imported product must not exist with a thumbnail_url and no registry rows."""
    db, product = seeded_product
    from backend.app.services.brand_catalog_service import BrandCatalogService

    storage = FakeStorage()
    monkeypatch.setattr(
        "backend.app.services.media_materialization_service.MediaMaterializationService._get_storage",
        lambda self: storage,
    )
    monkeypatch.setattr(
        "backend.app.services.media_materialization_service.MediaMaterializationService._get_fetch",
        lambda self: (lambda url: source_image_bytes()),
    )

    service = BrandCatalogService(db)
    row = {
        "title": "Materialised Import Probe Shirt",
        "category_slug": "tops",
        "base_price": "199.00",
        "color_family": "Navy",
        "thumbnail_url": "https://images.pexels.com/photos/450212/pexels-photo-450212.jpeg",
        "currency": "USD",
        "stock_level": "3",
        "size": "M",
        "color": "Navy",
        "title_ar": "قميص اختبار",
    }
    try:
        result = service.process_json_import([row], product.brand_id, send_notifications=False)
        created = db.query(Product).filter(Product.title == row["title"]).first()
        assert created is not None
        media = db.query(ProductImage).filter(ProductImage.product_id == created.id).all()
        assert media, "import left the product with no registered media"
        assert all(_KEY_RE.match(m.storage_key) for m in media)
        assert {m.source_type for m in media} == {"stock"}
        assert result["media_rows_registered"] == len(media)
    finally:
        created = db.query(Product).filter(Product.title == row["title"]).first()
        if created:
            db.query(ProductImage).filter(ProductImage.product_id == created.id).delete()
            db.query(Product).filter(Product.id == created.id).delete()
            db.commit()


def test_import_skips_media_honestly_when_the_host_is_not_approved(seeded_product):
    """A catalogue row from an unapproved host still imports; it just gets no media."""
    db, product = seeded_product
    from backend.app.services.brand_catalog_service import BrandCatalogService

    service = BrandCatalogService(db)
    row = {
        "title": "Unapproved Host Probe Jacket",
        "category_slug": "outerwear",
        "base_price": "299.00",
        "color_family": "Black",
        "thumbnail_url": "https://example.com/jacket.jpg",
        "currency": "USD",
        "stock_level": "1",
        "size": "M",
        "color": "Black",
        "title_ar": "سترة",
    }
    try:
        result = service.process_json_import([row], product.brand_id, send_notifications=False)
        created = db.query(Product).filter(Product.title == row["title"]).first()
        assert created is not None, "the row is still valid catalogue data"
        assert result["media_rows_registered"] == 0, "no bytes were stored, so no row may claim any"
        assert db.query(ProductImage).filter(ProductImage.product_id == created.id).count() == 0
    finally:
        created = db.query(Product).filter(Product.title == row["title"]).first()
        if created:
            db.query(ProductImage).filter(ProductImage.product_id == created.id).delete()
            db.query(Product).filter(Product.id == created.id).delete()
            db.commit()
