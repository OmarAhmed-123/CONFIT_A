"""The CSV import contract: what a brand owner's file must satisfy, end to end.

WHY THIS FILE EXISTS
--------------------
The importer had a validation screen and a commit path that disagreed. Preview
said "28 valid, can_import: true"; the commit then rejected rows for reasons the
preview never mentioned, because the media rules lived only in the commit. A
brand owner who reads a green table and then gets a red summary learns to
distrust the screen, which is worse than having no screen at all.

Every assertion here is about that class of dishonesty, plus the three defects
found while writing it:

  * the downloadable template shipped two rows that its OWN validator rejected
    (`original_price` equal to `price`);
  * a row priced in EGP was stored as-is and then quoted at two different prices
    — the product page rendered the raw number as EGP while the cart converted
    the same number from the USD price book (measured ~53x apart);
  * `description_ar` fell back to the English copy, so every imported product
    claimed an Arabic description it did not have.

The tests are written against observable output (`preview_csv`,
`process_csv_import`, the generated template) rather than private helpers, so
they keep their meaning through refactors.
"""
from __future__ import annotations

import csv
import io
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.core.config import settings
from backend.app.models.catalog import Category, Product, ProductImage, ProductSKU
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services import storage_service
from backend.app.services.brand_catalog_service import BrandCatalogService

APPROVED_IMAGE = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"
FOREIGN_IMAGE = "https://cdn.some-boutique.example.com/shirt.jpg"  # resolvable only in the stub below
HEADER = [
    "product_name", "sku", "description", "category", "price", "currency",
    "original_price", "color", "size", "stock_quantity", "image_url", "gender",
    "title_ar", "description_ar", "material", "care_instructions",
    # Not in the shipped template (the default is refuse), but parsed when a
    # brand explicitly declares provenance — so the contract test covers it.
    "image_source",
]


def _write_csv(rows, header=HEADER) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def _row(**over):
    base = dict(
        product_name="Cotton Poplin Shirt",
        sku="QA-TEST-001",
        description="Crisp cotton shirt",
        category="tops",
        price="27.00",
        currency=settings.PRICING_CURRENCY,
        original_price="",
        color="White",
        size="M",
        stock_quantity="10",
        image_url=APPROVED_IMAGE,
        gender="unisex",
        title_ar="قميص قطني",
        description_ar="قميص قطني متين",
        material="100% cotton",
        care_instructions="Machine wash cold",
        image_source="",
    )
    base.update(over)
    return [base[col] for col in HEADER]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A real SQLite database, a real brand, and real local object storage."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    for slug in BrandCatalogService.SEEDED_CATEGORY_SLUGS:
        db.add(Category(name=slug.title(), name_ar=slug, slug=slug))
    owner = User(email="contract@qa.example.com", hashed_password="x",
                 full_name="Contract QA", role=UserRole.BRAND_OWNER,
                 preferred_language="en", is_active=True, is_verified=True)
    db.add(owner)
    db.flush()
    brand = BrandProfile(user_id=owner.id, brand_name="Contract Atelier",
                         slug="contract-atelier", is_verified=True)
    db.add(brand)
    db.commit()

    monkeypatch.setattr(settings, "STORAGE_LOCAL_DIR", str(tmp_path / "uploads"),
                        raising=False)
    storage_service.reset_storage()

    yield dict(db=db, svc=BrandCatalogService(db), brand=brand,
               owner=owner, storage_dir=tmp_path / "uploads")

    storage_service.reset_storage()
    db.close()


# ---------------------------------------------------------------------------
# The downloadable template must be importable — it is the contract in a file.
# ---------------------------------------------------------------------------
def test_template_currency_is_the_price_book_denomination():
    rows = list(csv.DictReader(io.StringIO(BrandCatalogService.generate_sample_csv())))
    assert rows, "the template has no rows"
    currencies = {r["currency"] for r in rows}
    assert currencies == {settings.PRICING_CURRENCY}, (
        "the template must price in the price book denomination, or every brand "
        f"that follows it imports prices that mean something else; got {currencies}"
    )


def test_every_template_row_passes_the_importer_s_own_validation(env):
    svc, brand = env["svc"], env["brand"]
    sample = BrandCatalogService.generate_sample_csv()
    _valid, errors, stats = svc.parse_csv(sample, brand.id)
    messages = [f"row {e.row} {e.field}: {e.message}" for e in errors]
    assert stats["accepted"] == stats["total"] and stats["total"] >= 5, (
        "the official template contains rows the importer refuses — a brand that "
        f"follows the template exactly would be rejected: {messages}"
    )


def test_template_categories_are_the_slugs_the_seeder_creates(env):
    """A category the catalogue does not contain is the oldest trap in this file."""
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        seeded = {c.slug for c in db.query(Category).all()}
    rows = list(csv.DictReader(io.StringIO(BrandCatalogService.generate_sample_csv())))
    used = {r["category"] for r in rows}
    assert used <= seeded, (
        f"the template names categories the seeded catalogue does not have: {used - seeded}"
    )
    assert set(BrandCatalogService.SEEDED_CATEGORY_SLUGS) <= seeded, (
        "SEEDED_CATEGORY_SLUGS drifted from what seed_data.py actually creates"
    )


def test_error_report_suggests_only_categories_that_exist(env):
    report = BrandCatalogService.generate_error_report_csv(
        [{"row": 3, "field": "category_slug", "value": "shirts", "message": "not found"}]
    )
    suggestion = list(csv.DictReader(io.StringIO(report)))[0]["Corrective Action"]
    for slug in BrandCatalogService.SEEDED_CATEGORY_SLUGS:
        assert slug in suggestion
    assert "knitwear" not in suggestion and "shirts," not in suggestion, (
        "the corrective action still offers slugs the catalogue does not contain"
    )


# ---------------------------------------------------------------------------
# Preview and commit must reach the SAME verdict.
# ---------------------------------------------------------------------------
def test_preview_reports_an_image_host_the_importer_cannot_materialise(env):
    svc, brand = env["svc"], env["brand"]
    preview = svc.preview_csv(_write_csv([_row(image_url=FOREIGN_IMAGE)]), brand.id)
    fields = {e["field"] for e in preview["errors"]}
    assert "thumbnail_url" in fields, (
        "a row whose image the media stage will refuse must be refused by the "
        f"preview too, on the same field; got {preview['errors']}"
    )
    assert preview["can_import"] is False


def test_preview_error_names_the_approved_hosts(env):
    svc, brand = env["svc"], env["brand"]
    preview = svc.preview_csv(_write_csv([_row(image_url=FOREIGN_IMAGE)]), brand.id)
    suggestion = " ".join(e.get("suggestion", "") for e in preview["errors"])
    # Two actionable routes must be named: a licensed stock host, and claiming/
    # verifying the brand's own domain. (0045 replaced "set image_source=own" as
    # the remedy — the column is now only a hint, and the brand cannot authorize
    # itself by writing a string into a CSV.)
    assert "images.pexels.com" in suggestion, (
        "an error a brand owner cannot act on is a dead end; got "
        f"{suggestion!r}"
    )
    assert "verify your own domain" in suggestion, (
        "a brand importing its own photography needs the ownership route named, "
        f"not just the stock fallback; got {suggestion!r}"
    )


@pytest.fixture()
def public_dns(monkeypatch):
    """Resolve every hostname to a public address.

    The URL guard refuses names it cannot resolve ("we could not resolve it" is
    not evidence of safety), so a hermetic test needs a DNS answer. Patching the
    RESOLVER keeps the guard itself — the allow/deny logic — fully exercised,
    which is the part worth testing.
    """
    import socket as _socket

    from backend.app.core import net_guard

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)


def test_own_photography_is_refused_until_the_deployment_opts_in(env, monkeypatch, public_dns):
    svc, brand = env["svc"], env["brand"]
    monkeypatch.setattr(settings, "CATALOG_IMPORT_ALLOW_OWN_IMAGES", False, raising=False)
    preview = svc.preview_csv(
        _write_csv([_row(image_url=FOREIGN_IMAGE, image_source="own")]), brand.id
    )
    assert any(e["field"] == "image_source" for e in preview["errors"]), (
        "first-party image imports are an owner decision and are OFF by default; "
        "the row must say so instead of being accepted or silently ignored"
    )

    # The deployment flag is a SERVER-level switch, not an authorization. Turning
    # it on used to be enough to import any host a brand named; that was the hole
    # migration 0045 closes. With the flag on but no verified domain, the row is
    # STILL refused — which is the stronger property.
    monkeypatch.setattr(settings, "CATALOG_IMPORT_ALLOW_OWN_IMAGES", True, raising=False)
    preview = svc.preview_csv(
        _write_csv([_row(image_url=FOREIGN_IMAGE, image_source="own")]), brand.id
    )
    assert preview["errors"], (
        "operators switching the deployment flag on must not thereby authorize "
        "every host a brand names; ownership is per-brand and must be proven"
    )
    assert any(
        e["field"] == "thumbnail_url" and "domain" in e["message"].lower()
        for e in preview["errors"]
    ), preview["errors"]
    assert preview["can_import"] is False

    # ...and once THIS brand proves the domain, the same row is accepted. The
    # test therefore proves the control is ownership, not the flag.
    from backend.app.services.image_ownership import ImageOwnershipService

    ownership = ImageOwnershipService(env["db"])
    claim = ownership.request_domain(brand.id, "cdn.some-boutique.example.com")
    ownership.verify_domain(
        brand.id, "cdn.some-boutique.example.com",
        resolver=lambda host, token: token == claim.token,
    )

    preview = svc.preview_csv(
        _write_csv([_row(image_url=FOREIGN_IMAGE, image_source="own")]), brand.id
    )
    assert preview["errors"] == [], preview["errors"]
    assert preview["can_import"] is True


def test_own_photography_cannot_point_at_the_private_network(env, monkeypatch):
    """A URL typed by a brand owner is a server-side request primitive."""
    svc, brand = env["svc"], env["brand"]
    monkeypatch.setattr(settings, "CATALOG_IMPORT_ALLOW_OWN_IMAGES", True, raising=False)
    for hostile in (
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://127.0.0.1:6379/",
        "http://10.0.0.5/internal.png",
    ):
        preview = svc.preview_csv(
            _write_csv([_row(image_url=hostile, image_source="own")]), brand.id
        )
        assert any(e["field"] == "thumbnail_url" for e in preview["errors"]), (
            f"{hostile} was accepted as an image source"
        )


def test_a_currency_the_price_book_does_not_use_is_refused(env):
    """One product, two prices, differing by the FX rate — measured, not feared."""
    svc, brand = env["svc"], env["brand"]
    foreign = "EGP" if settings.PRICING_CURRENCY != "EGP" else "USD"
    preview = svc.preview_csv(_write_csv([_row(currency=foreign)]), brand.id)
    assert any(e["field"] == "currency" for e in preview["errors"]), (
        f"a row priced in {foreign} was accepted while the price book is "
        f"{settings.PRICING_CURRENCY}"
    )
    assert preview["can_import"] is False


# ---------------------------------------------------------------------------
# Gender: the catalogue filters on it, so the import must supply a real value.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("written,stored", [
    ("Women", "womens"), ("female", "womens"), ("ladies", "womens"), ("نسائي", "womens"),
    ("men", "mens"), ("Male", "mens"), ("رجالي", "mens"),
    ("unisex", "unisex"), ("Both", "unisex"), ("للجنسين", "unisex"),
])
def test_gender_synonyms_are_normalised(env, written, stored):
    svc, brand = env["svc"], env["brand"]
    valid, errors, _stats = svc.parse_csv(_write_csv([_row(gender=written)]), brand.id)
    assert not errors, [e.to_dict() for e in errors]
    assert valid[0]["gender"] == stored


def test_an_unrecognised_gender_is_refused(env):
    svc, brand = env["svc"], env["brand"]
    preview = svc.preview_csv(_write_csv([_row(gender="childrenswear")]), brand.id)
    assert any(e["field"] == "gender" for e in preview["errors"])
    assert "mens" in " ".join(e.get("suggestion", "") for e in preview["errors"])


def test_gender_is_inferred_when_absent_and_reported(env):
    svc, brand = env["svc"], env["brand"]
    result = svc.process_csv_import(
        _write_csv([_row(product_name="Silk Maxi Dress", sku="QA-DRESS-1", gender="")]),
        brand.id, "dress.csv",
    )
    assert result["accepted_rows"] == 1, result
    product = env["db"].query(Product).filter_by(title="Silk Maxi Dress").one()
    assert product.gender == "womens", (
        "the garment name says dress; leaving it unisex hides it from the "
        "stylist's women's outfits and offers it to men's"
    )
    assert result["rows_gender_inferred"] == 1, (
        "a derived value must be reported, not passed off as supplied"
    )


def test_an_explicit_gender_survives_a_reimport(env):
    svc, brand = env["svc"], env["brand"]
    svc.process_csv_import(_write_csv([_row(product_name="Wool Coat", sku="QA-C-1",
                                            gender="")]), brand.id, "a.csv")
    env["db"].expire_all()
    product = env["db"].query(Product).filter_by(title="Wool Coat").one()
    product.gender = "mens"          # merchandiser corrects it in the dashboard
    env["db"].commit()

    svc.process_csv_import(_write_csv([_row(product_name="Wool Coat", sku="QA-C-1",
                                            stock_quantity="4", gender="")]),
                           brand.id, "b.csv")
    env["db"].expire_all()
    assert env["db"].query(Product).filter_by(title="Wool Coat").one().gender == "mens", (
        "re-uploading an unchanged stock sheet overwrote a human decision with a guess"
    )


# ---------------------------------------------------------------------------
# Arabic copy: missing means missing, never English wearing an Arabic label.
# ---------------------------------------------------------------------------
def test_missing_arabic_description_is_stored_empty_not_english(env):
    svc, brand = env["svc"], env["brand"]
    result = svc.process_csv_import(
        _write_csv([_row(description_ar="")]), brand.id, "ar.csv")
    assert result["accepted_rows"] == 1, result
    product = env["db"].query(Product).filter_by(title="Cotton Poplin Shirt").one()
    assert product.description_ar == "", (
        "the Arabic description was filled with the English copy, so the AR page "
        "renders English prose as though it were a translation"
    )
    assert result["rows_missing_description_ar"] == 1


def test_arabic_copy_is_stored_verbatim(env):
    svc, brand = env["svc"], env["brand"]
    svc.process_csv_import(_write_csv([_row()]), brand.id, "ar.csv")
    product = env["db"].query(Product).filter_by(title="Cotton Poplin Shirt").one()
    assert product.title_ar == "قميص قطني"
    assert product.description_ar == "قميص قطني متين"


# ---------------------------------------------------------------------------
# Warnings: real, actionable, and never silently dropped.
# ---------------------------------------------------------------------------
def test_unrecognised_column_is_a_warning_not_a_silent_drop(env):
    svc, brand = env["svc"], env["brand"]
    header = HEADER + ["materiel"]          # the typo a human actually types
    preview = svc.preview_csv(_write_csv([_row()], header=header), brand.id)
    assert preview["errors"] == [], "an unknown column must not block the import"
    warned = {w["field"] for w in preview["warnings"]}
    assert "materiel" in warned, (
        "the value was ignored with no feedback at all; the brand owner will "
        "publish products with no material and never know why"
    )


def test_zero_stock_is_warned_because_the_storefront_hides_it(env):
    svc, brand = env["svc"], env["brand"]
    preview = svc.preview_csv(_write_csv([_row(stock_quantity="0")]), brand.id)
    assert preview["errors"] == []
    assert any(w["field"] == "stock_level" and w["row"] == 2 for w in preview["warnings"])


def test_missing_arabic_title_is_warned(env):
    svc, brand = env["svc"], env["brand"]
    preview = svc.preview_csv(_write_csv([_row(title_ar="", description_ar="")]), brand.id)
    assert any(w["field"] == "title_ar" for w in preview["warnings"])


# ---------------------------------------------------------------------------
# Dry run, create-vs-update, idempotency.
# ---------------------------------------------------------------------------
def test_preview_writes_nothing(env):
    svc, brand, db = env["svc"], env["brand"], env["db"]
    svc.preview_csv(_write_csv([_row()]), brand.id)
    assert db.query(Product).count() == 0
    assert db.query(ProductSKU).count() == 0
    assert db.query(ProductImage).count() == 0


def test_preview_labels_a_reupload_as_an_update(env):
    svc, brand = env["svc"], env["brand"]
    csv_text = _write_csv([_row()])
    first = svc.preview_csv(csv_text, brand.id)
    assert first["preview_records"][0]["action"] == "create"
    svc.process_csv_import(csv_text, brand.id, "first.csv")

    second = svc.preview_csv(csv_text, brand.id)
    assert second["preview_records"][0]["action"] == "update", (
        "the preview said 'create' for a row the import would update, because it "
        "only looked for a matching sku_code and SKUs are usually generated"
    )


def test_reimport_updates_in_place_and_never_duplicates(env):
    svc, brand, db = env["svc"], env["brand"], env["db"]
    csv_text = _write_csv([_row()])
    svc.process_csv_import(csv_text, brand.id, "1.csv")
    first_ids = sorted(p.id for p in db.query(Product).all())

    csv_v2 = _write_csv([_row(stock_quantity="3", price="31.00")])
    result = svc.process_csv_import(csv_v2, brand.id, "2.csv")

    db.expire_all()
    assert result["accepted_rows"] == 1, result
    assert sorted(p.id for p in db.query(Product).all()) == first_ids
    product = db.query(Product).filter_by(title="Cotton Poplin Shirt").one()
    assert str(product.base_price) == "31.00"
    assert db.query(ProductSKU).filter_by(sku_code="QA-TEST-001").one().stock_level == 3


def test_reimport_does_not_re_render_existing_media(env):
    """A stock-level correction must not re-upload the whole image ladder."""
    svc, brand, storage_dir = env["svc"], env["brand"], env["storage_dir"]
    csv_text = _write_csv([_row()])
    svc.process_csv_import(csv_text, brand.id, "1.csv")
    first = sorted(p for p in storage_dir.rglob("*") if p.is_file())
    assert first, "no media was written at all"

    svc.process_csv_import(_write_csv([_row(stock_quantity="7")]), brand.id, "2.csv")
    second = sorted(p for p in storage_dir.rglob("*") if p.is_file())
    assert [p.name for p in first] == [p.name for p in second], (
        "every re-import re-rendered the whole ratio ladder; the object set "
        "should be identical when the source image has not changed"
    )


def test_a_sku_belonging_to_another_product_is_caught_before_the_commit(env):
    svc, brand, db = env["svc"], env["brand"], env["db"]
    csv_text = _write_csv([_row()])
    svc.process_csv_import(csv_text, brand.id, "1.csv")

    other = _write_csv([_row(product_name="Another Shirt", sku="QA-TEST-001")])
    preview = svc.preview_csv(other, brand.id)
    sku_errors = [e for e in preview["errors"] if e["field"] == "sku_code"]
    assert sku_errors, "the preview approved a row the commit refuses"
    assert "cannot be moved" in sku_errors[0]["message"] or "already belongs" in sku_errors[0]["message"]

    result = svc.process_csv_import(other, brand.id, "2.csv")
    assert result["accepted_rows"] == 0
    db.expire_all()
    assert db.query(Product).count() == 1, "the refused row still created a product"


def test_import_result_reports_media_and_completeness_honestly(env):
    svc, brand = env["svc"], env["brand"]
    result = svc.process_csv_import(_write_csv([_row()]), brand.id, "1.csv")
    assert result["status"] == "completed", result
    assert result["media_rows_registered"] > 0, (
        "the product was accepted, so its media must exist; a product whose hero "
        "404s is the defect this importer is supposed to refuse"
    )
    assert result["rows_missing_title_ar"] == 0
    assert result["rows_missing_description_ar"] == 0
    # The job row stores the same numbers the response claimed.
    from backend.app.models.catalog_import import CatalogImportJob
    job = env["db"].query(CatalogImportJob).filter_by(id=result["job_id"]).one()
    assert (job.accepted_rows, job.rejected_rows, job.status) == (1, 0, "completed")
    assert json.loads(job.errors_json or "[]") == []


def test_utf8_arabic_survives_the_round_trip_through_the_file(env):
    """Excel writes a BOM and UTF-8 Arabic; both must survive."""
    svc, brand = env["svc"], env["brand"]
    with_title = "فستان سهرة مطرز"
    payload = "\ufeff" + _write_csv([_row(product_name="Embroidered Gown",
                                          title_ar=with_title,
                                          description_ar="فستان سهرة بتطريز يدوي",
                                          sku="QA-AR-1")])
    result = svc.process_csv_import(payload, brand.id, "ar.csv")
    assert result["accepted_rows"] == 1, result
    product = env["db"].query(Product).filter_by(title="Embroidered Gown").one()
    assert product.title_ar == with_title


def test_imported_gender_reaches_the_stylist_filter(env):
    """The value the import writes is the value the outfit composer filters on.

    `services/styling/garment_gender.is_compatible` is what `stylist_service`
    calls for a gendered request. Importing the wrong gender is invisible in the
    catalogue and only shows up as a man being offered an evening dress, which is
    the production defect migration 0027 exists for.
    """
    from backend.app.services.styling.garment_gender import is_compatible

    svc, brand = env["svc"], env["brand"]
    svc.process_csv_import(
        _write_csv([
            _row(product_name="Silk Slip Maxi Dress", sku="QA-G-1", gender=""),
            _row(product_name="Tailored Wool Blazer", sku="QA-G-2",
                 gender="mens", image_url=APPROVED_IMAGE),
        ]),
        brand.id, "gender.csv",
    )
    env["db"].expire_all()
    dress = env["db"].query(Product).filter_by(title="Silk Slip Maxi Dress").one()
    blazer = env["db"].query(Product).filter_by(title="Tailored Wool Blazer").one()

    assert dress.gender == "womens"
    assert is_compatible(dress.gender, "mens") is False, (
        "a men's outfit request can still be composed around an imported dress"
    )
    assert is_compatible(blazer.gender, "mens") is True
    assert is_compatible(dress.gender, None) is True, (
        "an unqualified request must not hide the catalogue"
    )
