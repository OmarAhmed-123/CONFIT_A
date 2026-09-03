"""Money boundary regression: user-supplied amounts are rejected in the DOMAIN
(before persistence) and surface as 4xx, never as 500 and never as silently
coerced values.

Every test drives the real production stack (FastAPI app -> pydantic boundary
type -> ``backend.app.core.money.validate_money`` -> repository). No rule is
re-implemented here; the assertions only observe behaviour.

Coverage (owner requirement, financial semantics blocker):
  * NaN / Infinity / 1e400 / garbage -> 422 (was 500 on PATCH placements)
  * sub-cent precision (0.005) -> 422 (was silently rounded to 0.01)
  * negative money on positive-only fields -> 422
  * 9,999,999,999.99 accepted by the domain, 10,000,000,000.00 rejected
  * exchange price_delta is the one signed field (negative allowed)
  * BNPL split is exact Decimal (schedule sums to the amount)
  * repository refuses corrupt money before any ORM assignment
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.app.core.money import (
    MAX_MONEY, MoneyRangeError, MoneyValueError, validate_money,
)
from backend.app.main import app
from backend.app.models.brand_analytics import SponsoredPlacement
from backend.app.models.catalog import Product, ProductSKU
from backend.app.models.user import BrandProfile, User
from backend.app.providers.bnpl_provider import BNPLProvider
from backend.app.repositories.brand_repository import BrandRepository
from backend.tests.conftest import TestingSessionLocal

PASSWORD = "Password123!"


def _raw_json(client: TestClient, method: str, url: str, body: str, headers: dict):
    """Send a raw JSON body so non-JSON-compliant literals (1e400, NaN) reach
    the server exactly as a hostile client would send them."""
    return client.request(method, url, content=body, headers={**headers, "Content-Type": "application/json"})


@pytest.fixture(scope="module")
def raw_client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def brand_ctx(raw_client):
    """A brand manager token plus one product/SKU owned by that brand."""
    db = TestingSessionLocal()
    try:
        row = (
            db.query(BrandProfile, User)
            .join(User, User.id == BrandProfile.user_id)
            .filter(BrandProfile.id.in_(db.query(Product.brand_id)))
            .first()
        )
        if not row:
            pytest.skip("no brand with products seeded")
        brand, user = row
        product = db.query(Product).filter(Product.brand_id == brand.id).first()
        sku = db.query(ProductSKU).filter(ProductSKU.product_id == product.id).first()
        if not sku:
            sku = ProductSKU(product_id=product.id, sku_code=f"MONEY-{product.id}", size="M",
                             color="Navy", stock_level=5, is_in_stock=True)
            db.add(sku)
            db.commit()
            db.refresh(sku)
        ctx = {"brand_id": brand.id, "email": user.email, "product_id": product.id, "sku_id": sku.id}
    finally:
        db.close()
    r = raw_client.post("/api/v1/auth/login", json={"email": ctx["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    ctx["headers"] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # login also set the httpOnly session cookie; drop it so that the
    # unauthenticated BNPL requests below are not subject to the CSRF guard
    raw_client.cookies.clear()
    return ctx


@pytest.fixture()
def placement(brand_ctx):
    db = TestingSessionLocal()
    try:
        plc = BrandRepository(db).create_placement(
            brand_id=brand_ctx["brand_id"], product_id=brand_ctx["product_id"],
            placement_type="stylist_featured", bid_amount="1.00", daily_budget="50.00",
        )
        pid = plc.id
    finally:
        db.close()
    yield pid
    db = TestingSessionLocal()
    try:
        row = db.get(SponsoredPlacement, pid)
        if row:
            db.delete(row)
            db.commit()
    finally:
        db.close()


BAD_BODIES = [
    ('"NaN"', "nan-string"),
    ('"Infinity"', "inf-string"),
    ("1e400", "float-overflow"),
    ('"abc"', "garbage"),
    ("0.005", "sub-cent"),
    ("-1", "negative"),
    ("0", "zero"),
    ("true", "boolean"),
    ('"10000000000.00"', "beyond NUMERIC(12,2)"),
]


class TestPlacementCreateBoundary:
    @pytest.mark.parametrize("literal,label", BAD_BODIES, ids=[b[1] for b in BAD_BODIES])
    def test_bad_bid_rejected_422(self, raw_client, brand_ctx, literal, label):
        body = f'{{"product_id": {brand_ctx["product_id"]}, "bid_amount_per_click": {literal}, "daily_budget": 50}}'
        r = _raw_json(raw_client, "POST", "/api/v1/brand/placements", body, brand_ctx["headers"])
        assert r.status_code == 422, f"{label}: {r.status_code} {r.text[:200]}"
        # the response must itself be valid JSON (1e400 echo used to crash the handler -> 500)
        json.loads(r.text)

    @pytest.mark.parametrize("literal,label", BAD_BODIES, ids=[b[1] for b in BAD_BODIES])
    def test_bad_budget_rejected_422(self, raw_client, brand_ctx, literal, label):
        body = f'{{"product_id": {brand_ctx["product_id"]}, "bid_amount_per_click": 1, "daily_budget": {literal}}}'
        r = _raw_json(raw_client, "POST", "/api/v1/brand/placements", body, brand_ctx["headers"])
        assert r.status_code == 422, f"{label}: {r.status_code} {r.text[:200]}"
        json.loads(r.text)

    def test_nothing_persisted_for_rejected_input(self, raw_client, brand_ctx):
        db = TestingSessionLocal()
        try:
            before = db.query(SponsoredPlacement).filter(SponsoredPlacement.brand_id == brand_ctx["brand_id"]).count()
        finally:
            db.close()
        body = f'{{"product_id": {brand_ctx["product_id"]}, "bid_amount_per_click": 0.005, "daily_budget": 50}}'
        assert _raw_json(raw_client, "POST", "/api/v1/brand/placements", body, brand_ctx["headers"]).status_code == 422
        db = TestingSessionLocal()
        try:
            after = db.query(SponsoredPlacement).filter(SponsoredPlacement.brand_id == brand_ctx["brand_id"]).count()
        finally:
            db.close()
        assert after == before

    def test_valid_two_decimal_bid_persists_exactly(self, raw_client, brand_ctx):
        body = f'{{"product_id": {brand_ctx["product_id"]}, "bid_amount_per_click": 0.15, "daily_budget": 12.30}}'
        r = _raw_json(raw_client, "POST", "/api/v1/brand/placements", body, brand_ctx["headers"])
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        db = TestingSessionLocal()
        try:
            row = db.get(SponsoredPlacement, pid)
            assert Decimal(str(row.bid_amount_per_click)) == Decimal("0.15")
            assert Decimal(str(row.daily_budget)) == Decimal("12.30")
            db.delete(row)
            db.commit()
        finally:
            db.close()


class TestPlacementPatchBoundary:
    """PATCH /partner/placements/{id} took an untyped dict and let money
    errors escape as 500. Now: 422 with the domain message, no mutation."""

    @pytest.mark.parametrize("field", ["bid_amount_per_click", "daily_budget"])
    @pytest.mark.parametrize("literal,label", BAD_BODIES, ids=[b[1] for b in BAD_BODIES])
    def test_bad_patch_value_422_and_unchanged(self, raw_client, brand_ctx, placement, field, literal, label):
        r = _raw_json(raw_client, "PATCH", f"/api/v1/partner/placements/{placement}",
                      f'{{"{field}": {literal}}}', brand_ctx["headers"])
        assert r.status_code == 422, f"{field} {label}: {r.status_code} {r.text[:200]}"
        db = TestingSessionLocal()
        try:
            row = db.get(SponsoredPlacement, placement)
            assert Decimal(str(row.bid_amount_per_click)) == Decimal("1.00")
            assert Decimal(str(row.daily_budget)) == Decimal("50.00")
        finally:
            db.close()

    def test_valid_patch_applies_exact_decimal(self, raw_client, brand_ctx, placement):
        r = _raw_json(raw_client, "PATCH", f"/api/v1/partner/placements/{placement}",
                      '{"bid_amount_per_click": "2.75"}', brand_ctx["headers"])
        assert r.status_code == 200, r.text
        assert Decimal(str(r.json()["bid_amount_per_click"])) == Decimal("2.75")
        assert r.json()["status"] == "active"  # placement status, no longer shadowed by "updated"


class TestClickSpendIsDecimal:
    def test_spend_accumulates_without_float_drift(self, raw_client, brand_ctx):
        db = TestingSessionLocal()
        try:
            plc = BrandRepository(db).create_placement(
                brand_id=brand_ctx["brand_id"], product_id=brand_ctx["product_id"],
                placement_type="stylist_featured", bid_amount="0.10", daily_budget="0.30",
            )
            pid = plc.id
        finally:
            db.close()
        try:
            for expected in ("0.10", "0.20", "0.30"):
                r = raw_client.post(f"/api/v1/partner/placements/{pid}/click", headers=brand_ctx["headers"])
                assert r.status_code == 200, r.text
                assert Decimal(str(r.json()["spent_today"])) == Decimal(expected)
            # 0.1+0.1+0.1 == 0.3 exactly (float would give 0.30000000000000004 and
            # a fourth click would be admitted); budget is now exhausted
            r = raw_client.post(f"/api/v1/partner/placements/{pid}/click", headers=brand_ctx["headers"])
            assert r.status_code == 400
            db = TestingSessionLocal()
            try:
                row = db.get(SponsoredPlacement, pid)
                assert Decimal(str(row.spent_today)) == Decimal("0.30")
                assert row.status == "budget_exhausted"
            finally:
                db.close()
        finally:
            db = TestingSessionLocal()
            try:
                row = db.get(SponsoredPlacement, pid)
                if row:
                    db.delete(row)
                    db.commit()
            finally:
                db.close()


class TestSkuPriceOverrideBoundary:
    @pytest.mark.parametrize("q", ["NaN", "Infinity", "1e400", "12.345", "-1", "0", "abc"])
    def test_bad_price_override_422(self, raw_client, brand_ctx, q):
        r = raw_client.put(f"/api/v1/brand/skus/{brand_ctx['sku_id']}?stock_level=5&price_override={q}",
                           headers=brand_ctx["headers"])
        assert r.status_code == 422, f"{q}: {r.status_code} {r.text[:200]}"

    def test_valid_price_override_exact(self, raw_client, brand_ctx):
        r = raw_client.put(f"/api/v1/brand/skus/{brand_ctx['sku_id']}?stock_level=5&price_override=149.90",
                           headers=brand_ctx["headers"])
        assert r.status_code == 200, r.text
        db = TestingSessionLocal()
        try:
            sku = db.get(ProductSKU, brand_ctx["sku_id"])
            assert Decimal(str(sku.price_override)) == Decimal("149.90")
            sku.price_override = None
            db.commit()
        finally:
            db.close()


class TestBnplBoundary:
    @pytest.mark.parametrize("literal", ['"NaN"', '"Infinity"', "1e400", "-5", "0", '"abc"', "19.999"])
    def test_bad_amount_422(self, raw_client, literal):
        r = _raw_json(raw_client, "POST", "/api/v1/commerce/bnpl-quote", f'{{"amount": {literal}}}', {})
        assert r.status_code == 422, f"{literal}: {r.status_code} {r.text[:200]}"
        json.loads(r.text)

    def test_schedule_sums_exactly_to_amount(self, raw_client):
        r = _raw_json(raw_client, "POST", "/api/v1/commerce/bnpl-quote", '{"amount": "100.01"}', {})
        assert r.status_code == 200, r.text
        data = r.json()
        parts = [Decimal(str(p["amount"])) for p in data["payment_schedule"]]
        assert len(parts) == 4
        assert sum(parts) == Decimal("100.01")
        assert parts[0] == Decimal("25.00") and parts[-1] == Decimal("25.01")

    def test_quote_sync_accepts_decimal_price(self):
        q = BNPLProvider("tabby").quote_sync(Decimal("120.50"))
        assert q["eligible"] is True
        assert Decimal(str(q["installment_amount"])) == Decimal("30.13")  # HALF_UP of 30.125

    def test_quote_sync_refuses_non_finite(self):
        with pytest.raises(MoneyValueError):
            BNPLProvider("tabby").quote_sync(float("nan"))


class TestRepositoryDomainGuard:
    """The repository itself (not just the API schema) refuses corrupt money,
    so an internal caller cannot bypass the boundary."""

    @pytest.mark.parametrize("bid", [float("nan"), float("inf"), "abc", 0, -1, "0.005", "1e400"])
    def test_create_placement_rejects_before_orm(self, brand_ctx, bid):
        db = TestingSessionLocal()
        try:
            before = db.query(SponsoredPlacement).count()
            with pytest.raises(ValueError):
                BrandRepository(db).create_placement(
                    brand_id=brand_ctx["brand_id"], product_id=brand_ctx["product_id"],
                    placement_type="stylist_featured", bid_amount=bid, daily_budget="50.00",
                )
            db.rollback()
            assert db.query(SponsoredPlacement).count() == before
        finally:
            db.close()

    @pytest.mark.parametrize("price", [float("nan"), float("inf"), 0, -1, "12.345", "1e400"])
    def test_update_sku_stock_rejects_bad_price(self, brand_ctx, price):
        db = TestingSessionLocal()
        try:
            with pytest.raises(ValueError):
                BrandRepository(db).update_sku_stock(brand_ctx["sku_id"], 5, price)
            db.rollback()
            assert db.get(ProductSKU, brand_ctx["sku_id"]).price_override is None
        finally:
            db.close()


class TestFieldSpecificSignRules:
    """Domain rules as consumed by production callers (single implementation)."""

    def test_exact_scale_boundaries(self):
        assert validate_money("9999999999.99", "x", exact_scale=True) == MAX_MONEY
        with pytest.raises(MoneyRangeError):
            validate_money("10000000000.00", "x", exact_scale=True)
        with pytest.raises(MoneyValueError):
            validate_money("0.005", "x", exact_scale=True)
        # internal Decimal arithmetic results (not user input) may still be quantized
        assert validate_money("0.005", "x") == Decimal("0.01")

    def test_price_delta_may_be_negative_but_refund_may_not(self):
        assert validate_money("-12.50", "price_delta", allow_negative=True) == Decimal("-12.50")
        with pytest.raises(MoneyValueError):
            validate_money("-12.50", "refund_amount", allow_negative=False)
        assert validate_money("0.00", "refund_amount", allow_zero=True) == Decimal("0.00")
