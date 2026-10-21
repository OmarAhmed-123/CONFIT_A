"""EGP→USD catalogue normalisation: the rate, the arithmetic, and the refusal.

WHAT THIS SUITE IS GUARDING
---------------------------
A row priced in EGP used to be refused outright, because storing ``1450.00``
with ``currency='EGP'`` made the product page render "1,450 EGP" while the cart
converted the SAME number out of the USD price book and rendered 78,166.03 EGP —
one product, two prices ~53x apart. It is now converted ONCE at import into the
price-book denomination, at a rate taken from the project's existing FX
authority, with the arithmetic recorded on the product.

The rates here are DETERMINISTIC TEST FIXTURES (1 USD = 52.09 EGP). They are not
live rates and must never be read as one. The suite injects ``RateSnapshot`` so
no test reaches the network and no test can drift when real rates move.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.models.catalog import Category, Product
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services import catalog_fx
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.services.fx_rates import RateSnapshot

APPROVED_IMAGE = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"

#: TEST FIXTURE. 1 USD = 52.09 EGP. Chosen because it divides 1614.79 exactly,
#: which makes the boundary cases below readable — not because it is a real rate.
TEST_RATE = Decimal("52.09")


def snapshot(rates=None, source="configured", base="USD", as_of=None):
    return RateSnapshot(base=base, rates=rates if rates is not None else {"EGP": TEST_RATE},
                        source=source, as_of=as_of)


@pytest.fixture()
def egp_brand():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for slug in BrandCatalogService.SEEDED_CATEGORY_SLUGS:
        db.add(Category(name=slug.title(), name_ar=slug, slug=slug))
    owner = User(email="fx@qa.example.com", hashed_password="x", full_name="FX QA",
                 role=UserRole.BRAND_OWNER, preferred_language="en", is_active=True,
                 is_verified=True)
    db.add(owner)
    db.flush()
    brand = BrandProfile(user_id=owner.id, brand_name="Nile Atelier", slug="nile-atelier",
                         is_verified=True)
    db.add(brand)
    db.commit()
    yield dict(db=db, brand=brand, owner=owner)
    db.close()


@pytest.fixture()
def fx(monkeypatch):
    """Install a deterministic rate and stub media (covered by the gallery suite)."""
    def install(rates=None, source="configured", base="USD", as_of=None):
        snap = snapshot(rates, source, base, as_of)
        monkeypatch.setattr(catalog_fx, "_provider_snapshot", lambda: snap)
        return snap

    install()
    monkeypatch.setattr(
        BrandCatalogService, "_materialize_media",
        # Signature mirrors BrandCatalogService._materialize_media, which now
        # carries brand_id so media materialisation can apply the ownership gate.
        lambda self, product, row, brand_id=None: type(
            "M", (), {"resolvable": True, "rows": 1, "reason": ""}
        )(),
    )
    return install


def csv_text(price, currency="EGP", compare_at=None, title="Cairo Coat", sku="EGP-001"):
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["title", "sku_code", "description", "category_slug", "base_price",
              "color_family", "thumbnail_url", "size", "stock_level", "gender",
              "title_ar", "currency"]
    values = [title, sku, "Wool", "tops", price, "Navy", APPROVED_IMAGE, "M", "5",
              "womens", "معطف", currency]
    if compare_at is not None:
        header.append("compare_at_price")
        values.append(compare_at)
    writer.writerow(header)
    writer.writerow(values)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. The rate itself: direction, precision, provenance
# ---------------------------------------------------------------------------
class TestRateResolution:
    def test_the_rate_direction_is_pricing_to_source_as_documented(self):
        """The provider publishes 1 USD = 52.09 EGP. Converting EGP DIVIDES."""
        rate = catalog_fx.resolve_rate("EGP", "USD", snapshot=snapshot())
        assert rate.provider_rate == TEST_RATE
        # Multiplying by the published number instead of dividing by it would
        # turn a $31 coat into an $84,000 one. Pin the direction arithmetically.
        assert rate.convert(Decimal("52.09")) == Decimal("1.00")
        assert rate.convert(Decimal("1614.79")) == Decimal("31.00")

    def test_the_same_currency_needs_no_conversion(self):
        rate = catalog_fx.resolve_rate("USD", "USD")
        assert rate.provider_rate == Decimal("1")
        assert rate.source == "identity"
        assert rate.convert(Decimal("31.00")) == Decimal("31.00")

    def test_provenance_carries_the_rate_its_source_and_its_timestamp(self):
        from datetime import datetime, timezone
        rate = catalog_fx.resolve_rate(
            "EGP", "USD", snapshot=snapshot(as_of="2026-10-20T00:00:00Z"),
            now=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc))
        prov = rate.provenance()
        assert prov["price_source_currency"] == "EGP"
        assert prov["price_fx_rate"] == "52.09"
        assert prov["price_fx_source"] == "configured"
        assert prov["price_fx_as_of"] == "2026-10-20T00:00:00Z"

    @pytest.mark.parametrize("amount,expected", [
        ("0.52", "0.01"),      # 0.0099… → rounds UP to a cent, not down to zero
        ("0.26", "0.00"),      # below half a cent genuinely converts to nothing
        ("1.00", "0.02"),
        ("1614.79", "31.00"),
        ("52.09", "1.00"),
    ])
    def test_money_is_rounded_half_up_to_the_cent(self, amount, expected):
        rate = catalog_fx.resolve_rate("EGP", "USD", snapshot=snapshot())
        assert rate.convert(Decimal(amount)) == Decimal(expected)

    def test_the_multiplier_keeps_full_precision(self):
        """Quantizing the multiplier first compounds an error across the file.

        The MONEY is quantized per row (that is what a price is), but the RATE
        is not: a multiplier rounded to 0.02 would make every EGP price in the
        file land on a grid, and the error grows with the amount. Measured:
        a 1614.79 EGP row converts to 31.00 at full precision but to 32.30 at a
        2dp multiplier — a 4% overcharge on every product in the catalogue.

        (Note the deliberate NON-property: converting 100 rows of 10.00 and
        summing does not equal converting 1000.00 once. Each price is its own
        money value and is rounded as such; that is correct, not drift.)
        """
        rate = catalog_fx.resolve_rate("EGP", "USD", snapshot=snapshot())
        assert rate.multiplier == Decimal("1") / TEST_RATE
        assert rate.multiplier != rate.multiplier.quantize(Decimal("0.01"))
        assert rate.convert(Decimal("1614.79")) == Decimal("31.00")
        coarse = catalog_fx.CatalogRate(
            source_currency="EGP", pricing_currency="USD",
            provider_rate=TEST_RATE, multiplier=rate.multiplier.quantize(Decimal("0.01")),
            source="configured",
        )
        assert coarse.convert(Decimal("1614.79")) == Decimal("32.30"), (
            "sanity: rounding the rate first is visibly wrong"
        )


# ---------------------------------------------------------------------------
# 2. Every refusal path. A catalogue import must never invent a rate.
# ---------------------------------------------------------------------------
class TestFailClosed:
    @pytest.mark.parametrize("rates,source,base,reason", [
        ({}, "unavailable", "USD", "rate_table_unavailable"),
        ({"EGP": TEST_RATE}, "stale_live", "USD", "rate_source_not_trusted:stale_live"),
        # Non-empty but from a source this importer will not convert with: the
        # TABLE exists, so the refusal names the source rather than the table.
        ({"EGP": TEST_RATE}, "unavailable", "USD", "rate_source_not_trusted:unavailable"),
        ({"EGP": TEST_RATE}, "configured", "EUR", "rate_base_mismatch"),
        ({"AED": Decimal("3.67")}, "live", "USD", "rate_not_published"),
        ({"EGP": Decimal("52.09")}, "weird_source", "USD",
         "rate_source_not_trusted:weird_source"),
    ])
    def test_a_rate_we_do_not_trust_is_refused_with_its_reason(self, rates, source, base, reason):
        with pytest.raises(catalog_fx.RateUnavailable) as excinfo:
            catalog_fx.resolve_rate("EGP", "USD", snapshot=snapshot(rates, source, base))
        assert excinfo.value.reason == reason

    @pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-1"), Decimal("NaN"),
                                     Decimal("Infinity")])
    def test_non_positive_or_non_finite_rates_are_refused(self, bad):
        with pytest.raises(catalog_fx.RateUnavailable) as excinfo:
            catalog_fx.resolve_rate("EGP", "USD", snapshot=snapshot({"EGP": bad}))
        # NaN comparisons are False, so a plain `<= 0` check would let NaN
        # through and every price would become NaN. The finite check is what
        # catches it, and it is the reason this test lists NaN explicitly.
        assert excinfo.value.reason in ("rate_non_positive", "rate_table_unavailable")

    def test_a_malformed_currency_code_is_refused(self):
        with pytest.raises(catalog_fx.RateUnavailable) as excinfo:
            catalog_fx.resolve_rate("EG", "USD", snapshot=snapshot())
        assert excinfo.value.reason == "currency_malformed"


# ---------------------------------------------------------------------------
# 3. The importer: conversion happens once, and is recorded
# ---------------------------------------------------------------------------
class TestImportConversion:
    def test_an_egp_row_is_stored_in_the_price_book_denomination(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        result = BrandCatalogService(db).process_csv_import(
            csv_text("1614.79", compare_at="2597.00"), brand.id, "egp.csv")

        assert result["status"] == "completed", result["errors"]
        assert result["accepted_rows"] == 1
        product = db.query(Product).one()
        assert product.base_price == Decimal("31.00")
        assert str(product.currency).upper() == "USD", "the label must match the number"
        assert product.compare_at_price == Decimal("49.86")

    def test_the_conversion_is_recorded_on_the_product(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        BrandCatalogService(db).process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")
        product = db.query(Product).one()

        assert product.price_source_currency == "EGP"
        assert product.price_source_amount == Decimal("1614.79")
        assert product.price_fx_rate == TEST_RATE
        assert product.price_fx_source == "configured"
        # The arithmetic is reproducible from the row alone.
        assert (product.price_source_amount / product.price_fx_rate).quantize(Decimal("0.01")) \
            == product.base_price

    def test_a_usd_row_is_not_touched_and_carries_no_provenance(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        result = BrandCatalogService(db).process_csv_import(
            csv_text("31.00", currency="USD"), brand.id, "usd.csv")

        assert result["status"] == "completed", result["errors"]
        product = db.query(Product).one()
        assert product.base_price == Decimal("31.00"), "a USD row was converted"
        assert product.price_source_currency is None
        assert product.price_fx_rate is None

    def test_double_conversion_is_impossible_on_reimport(self, egp_brand, fx):
        """The second import of the same EGP row must not divide it twice."""
        db, brand = egp_brand["db"], egp_brand["brand"]
        svc = BrandCatalogService(db)
        svc.process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")
        first = db.query(Product).one().base_price
        assert first == Decimal("31.00")

        svc.process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")
        db.expire_all()
        assert db.query(Product).count() == 1, "re-import created a second product"
        assert db.query(Product).one().base_price == Decimal("31.00"), (
            "the EGP amount was converted again — 31.00/52.09 = 0.60"
        )

    def test_a_rate_change_does_not_reprice_an_existing_product(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        BrandCatalogService(db).process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")
        assert db.query(Product).one().base_price == Decimal("31.00")

        # The provider moves; nothing re-runs the import. The stored price and
        # the stored rate are a snapshot of the import that wrote them.
        fx({"EGP": Decimal("60.00")})
        db.expire_all()
        product = db.query(Product).one()
        assert product.base_price == Decimal("31.00")
        assert product.price_fx_rate == TEST_RATE

    def test_preview_shows_the_converted_price_not_the_raw_one(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        preview = BrandCatalogService(db).preview_csv(csv_text("1614.79"), brand.id)

        record = preview["preview_records"][0]
        assert record["price"] == "31.00"
        assert record["currency"] == "USD"
        # ...and still says where it came from, so the number is explainable.
        assert record["source_price"] == "1614.79"
        assert record["source_currency"] == "EGP"
        assert record["fx_rate"] == "52.09"
        assert record["fx_converted"] is True

    def test_preview_and_commit_agree_on_the_converted_amount(self, egp_brand, fx):
        """A preview that disagrees with the commit is worse than no preview."""
        db, brand = egp_brand["db"], egp_brand["brand"]
        svc = BrandCatalogService(db)
        preview = svc.preview_csv(csv_text("1614.79"), brand.id)
        svc.process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")

        assert preview["preview_records"][0]["price"] == str(db.query(Product).one().base_price)

    def test_no_rate_means_nothing_is_imported(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        fx({}, "unavailable")
        result = BrandCatalogService(db).process_csv_import(
            csv_text("1614.79"), brand.id, "egp.csv")

        assert result["status"] == "failed"
        assert result["accepted_rows"] == 0
        assert db.query(Product).count() == 0, "a row was imported at a guessed rate"
        assert any(e["field"] == "currency" for e in result["errors"])

    def test_a_stale_rate_refuses_the_import_and_says_why(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        fx({"EGP": TEST_RATE}, "stale_live")
        result = BrandCatalogService(db).process_csv_import(
            csv_text("1614.79"), brand.id, "egp.csv")

        assert result["accepted_rows"] == 0
        message = " ".join(e["message"] for e in result["errors"])
        assert "stale_live" in message
        assert "MARKET_FX_RATES" in message, "the brand must be told what to ask for"

    def test_an_amount_that_rounds_to_zero_is_refused_not_published_free(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        result = BrandCatalogService(db).process_csv_import(
            csv_text("0.26"), brand.id, "egp.csv")

        assert result["accepted_rows"] == 0
        assert db.query(Product).count() == 0
        assert any("not a sellable price" in e["message"] for e in result["errors"])

    def test_a_sku_override_follows_the_row_rate(self, egp_brand, fx):
        """An override left in EGP would be a second price for the variant."""
        from backend.app.models.catalog import ProductSKU
        db, brand = egp_brand["db"], egp_brand["brand"]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["title", "sku_code", "description", "category_slug", "base_price",
                         "color_family", "thumbnail_url", "size", "stock_level", "gender",
                         "title_ar", "currency", "price_override"])
        writer.writerow(["Cairo Coat", "EGP-001", "Wool", "tops", "1614.79", "Navy",
                         APPROVED_IMAGE, "M", "5", "womens", "معطف", "EGP", "2083.60"])
        text = buf.getvalue()
        result = BrandCatalogService(db).process_csv_import(text, brand.id, "egp.csv")

        assert result["accepted_rows"] == 1, result["errors"]
        assert db.query(ProductSKU).one().price_override == Decimal("40.00")

    def test_an_unsupported_currency_is_refused_without_conversion(self, egp_brand, fx):
        db, brand = egp_brand["db"], egp_brand["brand"]
        result = BrandCatalogService(db).process_csv_import(
            csv_text("100.00", currency="XYZ"), brand.id, "x.csv")

        assert result["accepted_rows"] == 0
        assert db.query(Product).count() == 0


# ---------------------------------------------------------------------------
# 4. The consistency chain: catalogue → API → order snapshot
# ---------------------------------------------------------------------------
class TestConsistencyAcrossTheChain:
    def test_the_brand_api_reports_the_provenance(self, egp_brand, fx):
        """A merchandiser can see WHY the price is what it is."""
        from backend.app.services.brand_service import BrandService

        db, brand = egp_brand["db"], egp_brand["brand"]
        BrandCatalogService(db).process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")

        rows = BrandService(db).get_brand_products(egp_brand["owner"], brand.id)
        row = next(r for r in rows if r["title"] == "Cairo Coat")
        assert row["price_provenance"]["source_currency"] == "EGP"
        assert row["price_provenance"]["source_amount"] == "1614.79"
        assert row["price_provenance"]["rate"] == "52.09000000"

    def test_the_stored_price_is_in_the_denomination_the_cart_reads(self, egp_brand, fx):
        """The cart converts from the price book; a stored EGP number double-converts."""
        # The registry subclass is what checkout actually calls; the base class
        # has an empty market-currency map and would resolve every country to
        # the price book. Using the real entry point is the point of the test.
        from backend.app.providers.payment.capability_registry import (
            MarketPaymentCapabilityRegistry as MarketSettlement,
        )

        db, brand = egp_brand["db"], egp_brand["brand"]
        BrandCatalogService(db).process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")
        product = db.query(Product).one()

        assert product.currency == MarketSettlement.pricing_currency()

        # The real invariant is that catalogue conversion and checkout settlement
        # read ONE table. Prove it by configuring that table and watching both
        # sides move together — this is the property that makes the catalogue
        # price and the charged price agree by construction.
        from backend.app.core.config import settings
        from backend.app.services import fx_rates as fx_module

        fx_module.fx_rates.invalidate()
        original = settings.MARKET_FX_RATES
        settings.MARKET_FX_RATES = '{"EGP": "52.09"}'
        try:
            settlement = MarketSettlement.resolve_settlement("EG")
            assert settlement.currency == "EGP"
            assert settlement.converted is True
            assert settlement.rate == TEST_RATE, (
                "checkout and the importer must read the same rate"
            )
            # Round trip: 31.00 USD × 52.09 = 1,614.70 EGP ≈ the 1,614.79 the
            # brand wrote. The conversion is a normalisation, not a re-pricing.
            assert (product.base_price * settlement.rate).quantize(Decimal("0.01")) \
                == Decimal("1614.79")
        finally:
            settings.MARKET_FX_RATES = original
            fx_module.fx_rates.invalidate()

    def test_an_order_snapshot_never_moves_when_the_rate_does(self, egp_brand, fx):
        """Existing orders keep the rate they were priced at, forever."""
        db, brand = egp_brand["db"], egp_brand["brand"]
        BrandCatalogService(db).process_csv_import(csv_text("1614.79"), brand.id, "egp.csv")
        snapshot_rate = db.query(Product).one().price_fx_rate

        fx({"EGP": Decimal("60.00")})
        db.expire_all()
        assert db.query(Product).one().price_fx_rate == snapshot_rate
        # The order-side lock is a separate row and is equally untouched; this
        # suite does not create orders (test_order_price_lock.py owns that
        # lifecycle), it only proves the CATALOGUE side has no live re-rating.
