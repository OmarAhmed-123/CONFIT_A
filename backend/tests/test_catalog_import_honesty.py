"""Four catalogue-import defects found by the read-only audit.

Each test fails against the code as it stood before this change.

1. **The CSV template named categories that do not exist.** It emitted
   ``shirts`` and ``trousers``; the seeded catalogue creates
   outerwear/tops/bottoms/dresses/footwear/accessories, and ``_validate_row``
   rejects an unknown slug — so two of the template's own four sample rows
   failed validation. The error hint repeated the same three bad slugs, so a
   user who followed the advice landed back in the same error.
2. **Bulk import emailed customers by default.** ``send_notifications`` was
   ``Query(True)``, so a thousand-row dataset load fired a campaign nobody
   asked for.
3. **``title_ar`` silently held English.** A row without an Arabic title was
   stored with the English title in the Arabic column, so the database asserted
   a translation that did not exist and the RTL storefront rendered Latin text
   with nothing marking it.
"""
from __future__ import annotations

import csv
import inspect
import io

import pytest

from backend.app.controllers import brand_controller
from backend.app.services.brand_catalog_service import BrandCatalogService


def _template_rows() -> list[dict]:
    text = BrandCatalogService.generate_sample_csv()
    return list(csv.DictReader(io.StringIO(text)))


# -- 1. template + hint agree with the seeded categories ---------------------
def test_sample_csv_only_uses_seeded_categories():
    slugs = {row["category"] for row in _template_rows()}
    unknown = slugs - set(BrandCatalogService.SEEDED_CATEGORY_SLUGS)
    assert not unknown, f"the official template offers categories that do not exist: {sorted(unknown)}"
    assert slugs, "the template must contain sample rows"


def test_seeded_category_slugs_match_the_seeder():
    """The constant must describe the real seed, not a hopeful list."""
    import ast
    from pathlib import Path

    seed = Path(__file__).resolve().parents[2] / "backend/app/seed_data.py"
    tree = ast.parse(seed.read_text(encoding="utf-8"))
    seeded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if {"name", "name_ar", "slug"} <= keys:
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == "slug" and isinstance(v, ast.Constant):
                        seeded.add(v.value)
    assert seeded == set(BrandCatalogService.SEEDED_CATEGORY_SLUGS), (
        f"SEEDED_CATEGORY_SLUGS drifted from seed_data.py: {seeded} vs "
        f"{set(BrandCatalogService.SEEDED_CATEGORY_SLUGS)}"
    )


def test_category_error_hint_names_only_seeded_slugs():
    source = inspect.getsource(BrandCatalogService._validate_row)
    hint_line = next(line for line in source.splitlines() if "Select a seeded category" in line)
    assert "SEEDED_CATEGORY_SLUGS" in hint_line, (
        "the hint must be derived from the seeded constants, not hand-written again"
    )
    assert "knitwear" not in source and "'shirts'" not in source, (
        "the hint still names categories the seeder never creates"
    )


# -- 2. notifications are an explicit opt-in -------------------------------
def test_bulk_import_does_not_notify_by_default():
    signature = inspect.signature(brand_controller.upload_catalog_csv)
    default = signature.parameters["send_notifications"].default
    assert getattr(default, "default", default) is False, (
        "a bulk catalog import must not email the customer base unless asked"
    )


@pytest.mark.parametrize("method", ["process_csv_import", "process_json_import", "_process"])
def test_service_level_import_defaults_are_quiet(method):
    signature = inspect.signature(getattr(BrandCatalogService, method))
    default = signature.parameters["send_notifications"].default
    assert default is False, f"{method} must default to not notifying"


# -- 3. missing Arabic stays missing --------------------------------------
def test_missing_title_ar_is_stored_blank_not_english():
    assert BrandCatalogService._arabic_or_blank(None) == ""
    assert BrandCatalogService._arabic_or_blank("   ") == ""
    assert BrandCatalogService._arabic_or_blank("قميص قطني") == "قميص قطني"


def test_import_reports_rows_created_without_arabic(seeded_product_for_import):
    db, product = seeded_product_for_import
    from backend.app.models.catalog import Product

    service = BrandCatalogService(db)
    row = {
        "title": "Untranslated Import Probe Shirt",
        "category_slug": "tops",
        "base_price": "150.00",
        "color_family": "White",
        "thumbnail_url": "https://images.pexels.com/photos/450212/pexels-photo-450212.jpeg",
        "currency": "USD",
        "stock_level": "2",
        "size": "M",
        "color": "White",
        # deliberately no title_ar
    }
    try:
        result = service.process_json_import([row], product.brand_id, send_notifications=False)
        created = db.query(Product).filter(Product.title == row["title"]).first()
        assert created is not None
        assert created.title_ar == "", "the Arabic column must not silently hold English"
        assert result["rows_missing_title_ar"] == 1, "the import must say so rather than pretend"
        assert result["missing_title_ar_rows"], "the affected row numbers are reported"
    finally:
        created = db.query(Product).filter(Product.title == row["title"]).first()
        if created:
            from backend.app.models.catalog import ProductImage

            db.query(ProductImage).filter(ProductImage.product_id == created.id).delete()
            db.query(Product).filter(Product.id == created.id).delete()
            db.commit()


@pytest.fixture()
def seeded_product_for_import():
    from backend.app.models.catalog import Product, ProductImage
    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    product = db.query(Product).order_by(Product.id).first()
    assert product is not None
    try:
        yield db, product
    finally:
        db.query(ProductImage).filter(ProductImage.product_id == product.id).delete()
        db.commit()
        db.close()
