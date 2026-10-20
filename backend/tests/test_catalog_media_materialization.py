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


def test_import_rejects_a_row_whose_image_cannot_resolve(seeded_product):
    """An unapproved host is a REJECTED row, not a product that quietly ships blank.

    Tightened contract (owner decision, turn 18): a catalogue row that cannot
    end up with servable media must not be created at all. The previous
    behaviour — import it, register nothing, report success — is precisely how
    an imageless catalogue got certified as fine.
    """
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

        # The row is rejected, and the reason names the actual problem.
        assert result["accepted_rows"] == 0
        assert result["rejected_rows"] == 1
        messages = " ".join(e.get("message", "") for e in result["errors"])
        assert "no resolvable media" in messages
        assert "source_not_approved" in messages

        # And nothing was created: a rejected row must leave no product behind,
        # not even a half-written one whose hero would 404.
        assert db.query(Product).filter(Product.title == row["title"]).first() is None
        assert result["media_rows_registered"] == 0

        # One bad row out of one: the job fails rather than reporting success.
        assert result["status"] == "failed"
    finally:
        created = db.query(Product).filter(Product.title == row["title"]).first()
        if created:
            db.query(ProductImage).filter(ProductImage.product_id == created.id).delete()
            db.query(Product).filter(Product.id == created.id).delete()
            db.commit()


def test_a_registered_row_without_a_backing_object_is_not_resolvable(seeded_product):
    """The original bug, reproduced deliberately: 54 rows, every one a 404.

    "Resolvable" must mean the object is in the store. If it only meant "a row
    exists", the check would re-certify the exact defect this turn fixed.
    """
    from backend.app.services.media_materialization_service import verify_resolvable

    db, product = seeded_product
    db.add(ProductImage(
        product_id=product.id,
        storage_key=f"products/{product.id}/{product.id}-4x5.jpg",
        ratio="4x5", format="jpeg", public_url=f"/api/v1/media/products/{product.id}/{product.id}-4x5.jpg",
        width=1200, height=1500, bytes=12345, role="hero", checksum="deadbeef",
        source_type="stock", provider="pexels", is_primary=True,
    ))
    db.commit()

    empty_store = FakeStorage()  # holds nothing
    verdict = verify_resolvable(db, product.id, storage=empty_store)
    assert verdict.rows == 1, "the row is there — that is the point"
    assert verdict.resolvable is False, "a row with no object behind it is a 404 waiting to happen"
    assert verdict.reason == "object_missing"

    # Same row, object actually stored: now it resolves.
    empty_store.objects[f"products/{product.id}/{product.id}-4x5.jpg"] = source_image_bytes()
    ok = verify_resolvable(db, product.id, storage=empty_store)
    assert ok.resolvable is True and ok.reason == "ok"


def test_legacy_label_keys_are_not_resolvable(seeded_product):
    """`pexels:2096476:4x5:hero` was never a key; the route rejects it at parse time."""
    from backend.app.services.media_materialization_service import verify_resolvable

    db, product = seeded_product
    db.add(ProductImage(
        product_id=product.id, storage_key="pexels:2096476:4x5:hero", ratio="4x5",
        format="jpeg", public_url="/api/v1/media/pexels:2096476:4x5:hero",
        width=1200, height=1500, bytes=12345, role="hero", checksum="deadbeef",
        source_type="stock", provider="pexels", is_primary=True,
    ))
    db.commit()

    verdict = verify_resolvable(db, product.id, storage=FakeStorage())
    assert verdict.resolvable is False
    assert verdict.reason == "legacy_label_key"


def test_verify_reports_a_partial_ratio_ladder(seeded_product):
    """`--verify` must catch a short ladder, not just a misnamed key.

    MEASURED (2026-10-20, production, read-only): `products_with_media` was
    12/12 and `rows_with_canonical_key` was 108/108 — both green — while
    products 9 and 18 held only `4x5` and `master`. Every one of those four
    rows is canonical, so the name check passed; four of the five design ratios
    were simply absent. On the storefront those two products show a single
    gallery frame, no thumbnail rail and no 1:1 swatch or editorial band.

    The check has to be about COMPLETENESS, which a row count cannot express.
    """
    from backend.scripts.materialize_catalog_media import report_state

    db, product = seeded_product
    for ratio in ("4x5", "master"):
        for fmt in ("jpeg", "webp"):
            db.add(ProductImage(
                product_id=product.id,
                storage_key=f"products/{product.id}/{product.id}-{ratio}.{'jpg' if fmt == 'jpeg' else fmt}",
                ratio=ratio, format=fmt,
                public_url=f"/api/v1/media/products/{product.id}/{product.id}-{ratio}.jpg",
                width=1200, height=1500, bytes=12345, role="hero",
                checksum="deadbeef", source_type="stock", provider="pexels",
                is_primary=(ratio == "4x5"),
            ))
    db.commit()

    state = report_state(db, "verify")

    assert state["rows_with_canonical_key"] == 4, "all four rows are canonical — the name check is green"
    assert state["incomplete_ladder_count"] == 1
    missing = state["products_with_incomplete_ladder"][0]["missing"]
    assert "1x1.jpeg" in missing and "16x9.webp" in missing
    assert not [m for m in missing if m.startswith("4x5")], "4x5 IS present"


def test_verify_is_quiet_for_a_complete_ladder(seeded_product):
    """No false positive: ten rows, five ratios, both formats."""
    from backend.scripts.materialize_catalog_media import report_state
    from backend.app.services.product_media_service import RATIO_ORDER

    db, product = seeded_product
    for ratio in RATIO_ORDER:
        for fmt, ext in (("jpeg", "jpg"), ("webp", "webp")):
            db.add(ProductImage(
                product_id=product.id,
                storage_key=f"products/{product.id}/{product.id}-{ratio}.{ext}",
                ratio=ratio, format=fmt,
                public_url=f"/api/v1/media/products/{product.id}/{product.id}-{ratio}.{ext}",
                width=1200, height=1500, bytes=12345,
                role="hero" if ratio == "4x5" else "gallery",
                checksum="deadbeef", source_type="stock", provider="pexels",
                is_primary=(ratio == "4x5" and fmt == "jpeg"),
            ))
    db.commit()

    state = report_state(db, "verify")

    assert state["incomplete_ladder_count"] == 0
    assert state["products_with_incomplete_ladder"] == []
