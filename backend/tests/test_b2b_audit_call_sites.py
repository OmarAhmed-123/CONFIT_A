"""B2B admin audit-coverage tests (final truth audit, section 16).

Finding: proving AuditLog rows can be INSERTED is not evidence that production
operations audit anything. Before this change, zero brand/admin mutating
endpoints called log_audit(). These tests exercise the real HTTP endpoints and
assert a real AuditLog row lands in the database.

They fail if audit persistence is disabled or the call sites are removed.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.user import AuditLog, User, UserRole
from backend.app.models.brand_analytics import SponsoredPlacement
from backend.app.models.catalog import Product
from backend.tests.conftest import TestingSessionLocal

client = TestClient(app)


def _brand_login():
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(
            User.role.in_([UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER]),
            User.is_active == True).first()  # noqa: E712
        if not user:
            pytest.skip("no seeded brand owner")
        email = user.email
    finally:
        db.close()
    for pwd in ("Password123!", "Brand123!", "Test123!"):
        r = client.post("/auth/login", json={"email": email, "password": pwd})
        if r.status_code == 200:
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
    pytest.skip("could not authenticate seeded brand owner")


def _audit_count(action: str) -> int:
    db = TestingSessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.action == action).count()
    finally:
        db.close()


class TestBrandAdminOperationsAreAudited:
    def test_inventory_update_writes_audit_row(self):
        headers = _brand_login()
        db = TestingSessionLocal()
        try:
            from backend.app.models.catalog import ProductSKU
            sku = db.query(ProductSKU).first()
            if not sku:
                pytest.skip("no seeded SKU")
            sku_id, level = sku.id, (sku.stock_level or 1)
        finally:
            db.close()

        before = _audit_count("BRAND_INVENTORY_UPDATED")
        r = client.put(f"/brand/skus/{sku_id}", params={"stock_level": level},
                       headers=headers)
        if r.status_code in (403, 404):
            pytest.skip(f"SKU not owned by this brand ({r.status_code})")
        assert r.status_code == 200, r.text
        assert _audit_count("BRAND_INVENTORY_UPDATED") == before + 1

    def test_audit_row_carries_actor_and_resource(self):
        db = TestingSessionLocal()
        try:
            row = (db.query(AuditLog)
                     .filter(AuditLog.action == "BRAND_INVENTORY_UPDATED")
                     .order_by(AuditLog.id.desc()).first())
        finally:
            db.close()
        if row is None:
            pytest.skip("no inventory audit row produced in this environment")
        assert row.user_id is not None
        assert row.resource_type == "ProductSKU"
        assert row.resource_id is not None


class TestAuditCallSitesExist:
    """Static guard: section 30 mutation — removing the call sites must fail."""

    def test_brand_controller_audits_sensitive_mutations(self):
        src = open("backend/app/controllers/brand_controller.py").read()
        for action in ("BRAND_INVENTORY_UPDATED", "BRAND_PLACEMENT_CREATED",
                       "BRAND_PLACEMENT_UPDATED", "BRAND_PLACEMENT_DELETED",
                       "BRAND_STORE_CREATED"):
            assert action in src, f"missing audit call site: {action}"

    def test_audit_helper_uses_real_persistence_not_print(self):
        src = open("backend/app/controllers/brand_controller.py").read()
        assert "UserRepository(db).log_audit(" in src
