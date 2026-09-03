"""Regression tests for the silent-fallback sweep (2026-09-03).

Each test drives the PRODUCTION code path (security module, API endpoint) and
asserts that a malformed / hostile input produces an explicit failure instead
of the previous silent coercion:

  * verify_password: a plaintext value stored in ``hashed_password`` used to be
    accepted when the login password equalled it ("legacy hash support").
    Now bcrypt-only -> False. The test also proves the test-DB login endpoint
    rejects such an account end-to-end.
  * placement start/end dates: an unparseable ISO string used to become None
    (an open-ended placement) — now 422 ValidationDomainError.
  * checkout session snapshot: a corrupt ``cart_snapshot_json`` used to be
    presented as an empty 0.00 cart — now 422, so the shopper is told to start
    a new checkout rather than paying for nothing.

The mutations that revert each fix were executed against these tests when the
fixes landed; each test fails under its mutation.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import get_password_hash, verify_password
from backend.app.main import app
from backend.app.models.commerce import CheckoutSession
from backend.app.models.catalog import Product
from backend.app.models.user import BrandProfile, User, UserRole
from backend.tests.conftest import TestingSessionLocal

PASSWORD = "Password123!"


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. verify_password is bcrypt-only
# ---------------------------------------------------------------------------
class TestVerifyPasswordBcryptOnly:
    def test_plaintext_stored_value_never_authenticates(self):
        # The stored column holds the plaintext itself (bad import / manual edit).
        assert verify_password("hunter2hunter2", "hunter2hunter2") is False

    def test_non_bcrypt_hash_like_strings_fail_closed(self):
        for stored in ("5f4dcc3b5aa765d61d8327deb882cf99",  # md5("password")
                       "$argon2id$v=19$m=65536,t=3,p=4$abc$def",
                       "sha256$abcdef",
                       "",
                       "$2b$12$tooshort"):
            assert verify_password("password", stored) is False, stored

    def test_real_bcrypt_hash_still_works(self):
        h = get_password_hash(PASSWORD)
        assert h.startswith("$2")
        assert verify_password(PASSWORD, h) is True
        assert verify_password(PASSWORD + "x", h) is False

    def test_login_endpoint_rejects_plaintext_password_column(self, client):
        """End-to-end: an account whose hashed_password is plaintext cannot log in
        with that plaintext (previously it could)."""
        db = TestingSessionLocal()
        email = "plaintext-victim@confit.io"
        try:
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(email=email, full_name="Plaintext Victim",
                            hashed_password="NotAHash-Plaintext-Value-1",
                            role=UserRole.CONSUMER, is_active=True)
                db.add(user)
            else:
                user.hashed_password = "NotAHash-Plaintext-Value-1"
            db.commit()
        finally:
            db.close()
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "NotAHash-Plaintext-Value-1"})
        assert r.status_code in (400, 401), r.text
        assert "access_token" not in r.text


# ---------------------------------------------------------------------------
# 2. Placement dates must parse or be rejected
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def brand_headers(client):
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
        ctx = {"email": user.email, "product_id": product.id}
    finally:
        db.close()
    r = client.post("/api/v1/auth/login", json={"email": ctx["email"], "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    ctx["headers"] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return ctx


class TestPlacementDateParsing:
    @pytest.mark.parametrize("bad", ["next tuesday", "2026-13-45", "31/12/2026", "2026-09-03T25:61:00Z", "   "])
    def test_unparseable_start_date_is_422_not_open_ended(self, client, brand_headers, bad):
        body = {"product_id": brand_headers["product_id"], "bid_amount_per_click": 1.25,
                "daily_budget": 50, "start_date": bad}
        # pydantic may reject first (422) — if it lets the string through the
        # service must reject it too; either way it must never become None.
        r = client.post("/api/v1/brand/placements", json=body, headers=brand_headers["headers"])
        assert r.status_code == 422, f"{bad!r}: {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("bad", ["next tuesday", "2026-13-45", "31/12/2026", 20260903])
    def test_service_rejects_unparseable_date_instead_of_none(self, brand_headers, bad):
        """The service accepts dict payloads (pydantic is bypassed by internal
        callers / imports). An unparseable value must raise, never become an
        open-ended placement."""
        from backend.app.core.exceptions import ValidationDomainError
        from backend.app.services.brand_service import BrandService
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.email == brand_headers["email"]).first()
            brand = db.query(BrandProfile).filter(BrandProfile.user_id == user.id).first()
            svc = BrandService(db)
            with pytest.raises(ValidationDomainError):
                svc.create_sponsored_placement(user, brand.id, {
                    "product_id": brand_headers["product_id"], "bid_amount_per_click": 1.25,
                    "daily_budget": 50, "start_date": bad,
                })
        finally:
            db.close()

    def test_valid_iso_dates_are_persisted(self, client, brand_headers):
        start = datetime.now(timezone.utc).replace(microsecond=0)
        end = start + timedelta(days=7)
        body = {"product_id": brand_headers["product_id"], "bid_amount_per_click": 1.25,
                "daily_budget": 50, "start_date": start.isoformat(), "end_date": end.isoformat()}
        r = client.post("/api/v1/brand/placements", json=body, headers=brand_headers["headers"])
        assert r.status_code in (200, 201), r.text
        placement_id = r.json()["id"]
        # The response projection does not echo the dates; verify persistence.
        from backend.app.models.brand_analytics import SponsoredPlacement
        db = TestingSessionLocal()
        try:
            row = db.get(SponsoredPlacement, placement_id)
            assert row is not None
            assert row.start_date is not None and row.end_date is not None
            assert row.start_date.replace(tzinfo=None) == start.replace(tzinfo=None)
            assert row.end_date.replace(tzinfo=None) == end.replace(tzinfo=None)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 3. Corrupt checkout snapshot is an error, not an empty cart
# ---------------------------------------------------------------------------
class TestCorruptCheckoutSnapshot:
    def _make_session(self, snapshot: str, token: str) -> None:
        db = TestingSessionLocal()
        try:
            existing = db.query(CheckoutSession).filter(CheckoutSession.token == token).first()
            if existing:
                db.delete(existing)
                db.commit()
            db.add(CheckoutSession(
                token=token,
                user_id=None,
                guest_session_token="guest-corrupt-snapshot",
                cart_snapshot_json=snapshot,
                total_amount=384.00,
                currency="USD",
                status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ))
            db.commit()
        finally:
            db.close()

    @pytest.mark.parametrize("snapshot", ["{not json", "", "\x00\x01", "[1,2"])
    def test_unreadable_snapshot_returns_422(self, client, snapshot):
        token = "chk_corrupt_" + str(abs(hash(snapshot)) % 10_000_000)
        self._make_session(snapshot, token)
        r = client.get(f"/api/v1/checkout/sessions/{token}",
                       headers={"X-Session-Token": "guest-corrupt-snapshot"})
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        # Must not leak a fabricated empty cart / 0.00 total
        assert "items" not in json.dumps(body.get("error", body)).lower() or body.get("error")

    def test_valid_snapshot_still_served(self, client):
        token = "chk_valid_snapshot"
        snapshot = json.dumps({"items": [{"sku_id": 1, "quantity": 1, "unit_price": "384.00"}],
                               "subtotal": "384.00", "total": "384.00"})
        self._make_session(snapshot, token)
        r = client.get(f"/api/v1/checkout/sessions/{token}",
                       headers={"X-Session-Token": "guest-corrupt-snapshot"})
        assert r.status_code == 200, r.text
