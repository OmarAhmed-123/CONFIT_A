"""Multi-photograph galleries: every supplied image is kept, or its loss is reported.

MEASURED DEFECT
---------------
``BrandCatalogService._materialize_media`` parsed the CSV ``images`` column and
then used only ``parsed[0]``. A brand that supplied front / back / detail
photographs got ONE picture on the storefront, no warning, and a job that said
``completed``. The row's own ``image_url`` was also the only thing materialised,
so the gallery array existed in the CSV contract and nowhere in the product.

THE CONTRACT, AND WHY IT IS ADDITIVE
------------------------------------
``images`` is pinned to "one frame per ratio" for the HERO photograph by
``test_product_gallery_uniqueness.py`` — it is a rendition ladder, not a
gallery, and a second photograph has no place in a list keyed by ratio.
Flattening the gallery into it would either drop photographs (same ratio ⇒ same
key) or restore the double-frame defect. So the gallery is a new ``photos[]``
field: one entry per supplied photograph, in supplied order, and ``images``
keeps meaning exactly what it meant.

These tests pin:
  A. three supplied photographs ⇒ three photographs in the registry, distinct
     storage keys, order preserved, exactly ONE hero;
  B. ``images`` still describes the hero's ladder only (no mixing of frames
     from different photographs);
  C. ``photos[]`` carries each photograph with its own attribution;
  D. a failing photograph does not take the gallery down and IS reported;
  E. re-importing the same gallery neither duplicates rows nor re-uploads;
  F. a gallery may not smuggle in an unapproved host.
"""
from __future__ import annotations

import io
import json

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import settings
from backend.app.core.database import Base
from backend.app.models.catalog import Category, Product, ProductImage
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services import media_materialization_service as mms
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.services.media_materialization_service import (
    MediaMaterializationService,
    canonical_storage_key,
)
from backend.app.services.product_media_service import gallery_images, photos_payload

PEXELS_A = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"
PEXELS_B = "https://images.pexels.com/photos/297933/pexels-photo-297933.jpeg"
PEXELS_C = "https://images.pexels.com/photos/1598507/pexels-photo-1598507.jpeg"
FOREIGN_HOST = "https://cdn.some-boutique.example.com/back.jpg"


def source_image_bytes(colour=(60, 60, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (640, 800), colour).save(buf, format="JPEG")
    return buf.getvalue()


class FakeStorage:
    """In-memory object store; records how many objects were written."""

    def __init__(self):
        self.objects: dict = {}
        self.writes = 0

    def store(self, key, data):
        self.objects[key] = data
        self.writes += 1
        return key

    def exists(self, key):
        return key in self.objects

    def read(self, key):
        return self.objects.get(key)


@pytest.fixture()
def gallery_env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    for slug in BrandCatalogService.SEEDED_CATEGORY_SLUGS:
        db.add(Category(name=slug.title(), name_ar=slug, slug=slug))
    owner = User(email="gallery@qa.example.com", hashed_password="x",
                 full_name="Gallery QA", role=UserRole.BRAND_OWNER,
                 preferred_language="en", is_active=True, is_verified=True)
    db.add(owner)
    db.flush()
    brand = BrandProfile(user_id=owner.id, brand_name="Gallery Atelier",
                         slug="gallery-atelier", is_verified=True)
    db.add(brand)
    db.commit()

    storage = FakeStorage()
    monkeypatch.setattr(MediaMaterializationService, "_get_storage", lambda self: storage)
    monkeypatch.setattr(MediaMaterializationService, "_get_fetch",
                        lambda self: (lambda url: source_image_bytes()))

    db.commit()

    yield dict(db=db, brand=brand, storage=storage)
    db.close()


def _row(db, brand_id, *, title, images):
    """A normalized import row: what parse/normalize hands to import_products."""
    code = f"GAL-{title.replace(' ', '-').upper()}"
    return {
        "row_number": 2,
        "title": title,
        "category_slug": "tops",
        "base_price": "199.00",
        "color_family": "Navy",
        "currency": settings.PRICING_CURRENCY,
        "stock_level": "3",
        "size": "M",
        "color": "Navy",
        "sku_code": code,
        "title_ar": "معطف اختبار",
        "thumbnail_url": PEXELS_A,
        "images": json.dumps(images, ensure_ascii=False),
        "image_source": "",
    }


# ---------------------------------------------------------------------------
# A/B/C — the gallery is kept, ordered, and does not disturb `images`
# ---------------------------------------------------------------------------
def test_three_supplied_photographs_all_reach_the_registry(gallery_env):
    db, brand, storage = gallery_env["db"], gallery_env["brand"], gallery_env["storage"]
    svc = BrandCatalogService(db)
    svc.import_products([_row(db, brand.id, title="Triptych Shirt",
                              images=[PEXELS_B, PEXELS_C])], brand.id)
    db.expire_all()

    product = db.query(Product).filter_by(title="Triptych Shirt").one()
    rows = db.query(ProductImage).filter_by(product_id=product.id).all()

    positions = sorted({r.photo_index for r in rows})
    assert positions == [0, 1, 2], (
        "every supplied photograph must be registered as its own photograph; "
        f"got positions {positions}"
    )
    # The hero is the row's image_url; the gallery keeps the CSV order.
    by_pos = {r.photo_index: r for r in rows if r.ratio == "4x5" and r.format == "jpeg"}
    assert by_pos[0].source_ref == PEXELS_A
    assert by_pos[1].source_ref == PEXELS_B
    assert by_pos[2].source_ref == PEXELS_C

    heroes = [r for r in rows if r.is_primary]
    assert len(heroes) == 1 and heroes[0].photo_index == 0, (
        "exactly one hero, belonging to the first photograph — two primaries "
        "would make the card image depend on row order"
    )


def test_each_photograph_has_its_own_storage_keys(gallery_env):
    """Photograph 2 must not be written over photograph 1's bytes."""
    keys = [canonical_storage_key(7, "4x5", "jpeg", idx) for idx in (0, 1, 2)]
    assert len(set(keys)) == 3, f"photographs share storage keys: {keys}"
    assert keys[0].endswith("/7-4x5.jpg"), keys[0]
    assert keys[1].endswith("/7-p1-4x5.jpg"), keys[1]
    # Still inside the shape the media route's whitelist accepts.
    for key in keys:
        assert mms.CANONICAL_KEY_RE.match(key), key


def test_images_stays_the_hero_ladder_and_photos_carries_the_gallery(gallery_env):
    db, brand = gallery_env["db"], gallery_env["brand"]
    svc = BrandCatalogService(db)
    svc.import_products([_row(db, brand.id, title="Contract Shirt",
                              images=[PEXELS_B, PEXELS_C])], brand.id)
    db.expire_all()
    product = db.query(Product).filter_by(title="Contract Shirt").one()
    rows = db.query(ProductImage).filter_by(product_id=product.id).all()

    images = gallery_images(rows)
    # One frame per ratio, hero photograph only — the pinned invariant.
    assert len(images) == 4, f"`images` must stay one frame per ratio, got {images}"
    assert all("p1-" not in url and "p2-" not in url for url in images), (
        f"`images` leaked frames from other photographs: {images}"
    )

    photos = photos_payload(rows)
    assert [p["position"] for p in photos] == [0, 1, 2]
    assert photos[0]["is_primary"] is True
    assert [p["source_ref"] for p in photos] == [PEXELS_A, PEXELS_B, PEXELS_C]
    assert all(len(p["images"]) == 4 for p in photos), (
        "each photograph needs its own ratio ladder so the page can pick a frame"
    )
    # Distinct photographs must not share a single URL.
    assert len({p["url"] for p in photos}) == 3
    # Attribution travels per photograph, not per product.
    assert all(p["attribution"] and "Pexels" in p["attribution"] for p in photos)


# ---------------------------------------------------------------------------
# D — a failing photograph is reported, not swallowed
# ---------------------------------------------------------------------------
def test_a_failing_secondary_photo_is_reported_and_does_not_kill_the_row(gallery_env, monkeypatch):
    db, brand = gallery_env["db"], gallery_env["brand"]
    good = source_image_bytes()

    def flaky(url):
        if url == PEXELS_C:
            raise RuntimeError("connection reset")
        return good

    monkeypatch.setattr(MediaMaterializationService, "_get_fetch", lambda self: flaky)

    svc = BrandCatalogService(db)
    row = _row(db, brand.id, title="Flaky Shirt", images=[PEXELS_B, PEXELS_C])
    accepted, rejected, errors, *_rest = svc.import_products([row], brand.id)
    db.expire_all()

    assert rejected == 0 and accepted == 1, (
        "one unreachable photograph must not reject an otherwise valid product row"
    )
    product = db.query(Product).filter_by(title="Flaky Shirt").one()
    positions = sorted({r.photo_index for r in db.query(ProductImage).filter_by(product_id=product.id)})
    assert positions == [0, 1], f"the reachable photographs must still land, got {positions}"
    assert svc._photo_warnings, "the dropped photograph was not reported anywhere"
    assert svc._photo_warnings[0]["field"] == "images"
    assert "Image 3 of 3 was not imported" in svc._photo_warnings[0]["message"], (
        f"the warning must name WHICH image was dropped: {svc._photo_warnings[0]}"
    )


def test_a_gallery_cannot_smuggle_in_an_unapproved_host(gallery_env):
    db, brand = gallery_env["db"], gallery_env["brand"]
    svc = BrandCatalogService(db)
    row = _row(db, brand.id, title="Smuggle Shirt", images=[FOREIGN_HOST, PEXELS_B])
    svc.import_products([row], brand.id)
    db.expire_all()

    product = db.query(Product).filter_by(title="Smuggle Shirt").one()
    rows = db.query(ProductImage).filter_by(product_id=product.id).all()
    refs = {r.source_ref for r in rows}
    assert FOREIGN_HOST not in refs, (
        "an unapproved host reached object storage through the gallery column"
    )
    # ...and the approved photograph in the same row still landed, because one
    # bad URL must not cost the brand the whole product.
    assert PEXELS_B in refs
    assert sorted({r.photo_index for r in rows}) == [0, 1]
    assert any("not an approved image source" in w["message"] for w in svc._photo_warnings), (
        f"the refused image was not reported: {svc._photo_warnings}"
    )


# ---------------------------------------------------------------------------
# E — idempotency across the whole gallery
# ---------------------------------------------------------------------------
def test_reimport_does_not_duplicate_or_reupload_the_gallery(gallery_env):
    db, brand, storage = gallery_env["db"], gallery_env["brand"], gallery_env["storage"]
    svc = BrandCatalogService(db)
    row = _row(db, brand.id, title="Idempotent Shirt", images=[PEXELS_B, PEXELS_C])

    svc.import_products([row], brand.id)
    db.expire_all()
    product = db.query(Product).filter_by(title="Idempotent Shirt").one()
    first_rows = db.query(ProductImage).filter_by(product_id=product.id).count()
    first_writes = storage.writes
    assert first_rows == 3 * 5 * 2, f"expected 3 photographs x 5 ratios x 2 formats, got {first_rows}"

    svc.import_products([row], brand.id)
    db.expire_all()
    second_rows = db.query(ProductImage).filter_by(product_id=product.id).count()

    assert second_rows == first_rows, (
        f"a second identical upload changed the registry: {first_rows} -> {second_rows}"
    )
    assert storage.writes == first_writes, (
        f"a second identical upload re-rendered {storage.writes - first_writes} objects"
    )

    photos = photos_payload(db.query(ProductImage).filter_by(product_id=product.id).all())
    assert len(photos) == 3, f"photographs multiplied on re-import: {len(photos)}"
