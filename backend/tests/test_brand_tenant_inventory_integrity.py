"""P1 regression: cross-tenant store-inventory leak + count/breakdown mismatch.

PRODUCTION EVIDENCE THAT MOTIVATED THESE TESTS (2026-09-22, Neon prod DB):

    brand_id | name           | products | stores | placements
    1        | Massimo Dutti  | 3        | 1      | 2
    2        | COS            | 1        | 0      | 0

    SELECT ... FROM store_inventories si
      JOIN store_locations sl ON sl.id = si.store_id
      JOIN product_skus sk    ON sk.id = si.sku_id
      JOIN products p         ON p.id  = sk.product_id
     WHERE sl.brand_id <> p.brand_id;
    -> 11 rows  (store_brand=1, product_brand IN (2,3))

That is the real cause of the audit's "Store Locations (0) ... Store #1: 6
avail" contradiction. It was never a cosmetic counter mismatch: the endpoint
published brand 1's store id and stock levels inside brand 2's response,
because the inventory query constrained only the SKU side of the join.

These tests lock the invariant from three angles so it cannot regress:
  1. the API response for a tenant with zero stores must contain zero store rows
  2. the count and the breakdown must never disagree (contract test)
  3. a deliberately planted cross-tenant row must not surface in either tenant
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token
from backend.app.main import app
from backend.app.models.catalog import (Category, Product, ProductSKU, StoreInventory,
                                        StoreLocation)
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.repositories.brand_repository import BrandRepository


@pytest.fixture
def tenants():
    """Two brands. Brand A owns one store; brand B owns NONE — exactly the
    production shape (Massimo Dutti vs COS)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        ua = User(email=f"a-{uuid.uuid4().hex}@test", full_name="A",
                  hashed_password="x", role=UserRole.BRAND_MANAGER)
        ub = User(email=f"b-{uuid.uuid4().hex}@test", full_name="B",
                  hashed_password="x", role=UserRole.BRAND_MANAGER)
        db.add_all([ua, ub])
        db.flush()

        ba = BrandProfile(user_id=ua.id, brand_name="BrandA", slug="brand-a")
        bb = BrandProfile(user_id=ub.id, brand_name="BrandB", slug="brand-b")
        cat = Category(name="Coats", name_ar="معاطف", slug="coats")
        db.add_all([ba, bb, cat])
        db.flush()

        def make_product(brand, tag):
            p = Product(brand_id=brand.id, category_id=cat.id, title=f"{tag} coat",
                        title_ar="معطف", slug=f"{tag}-coat-{uuid.uuid4().hex[:6]}",
                        description="d", description_ar="د", base_price=100,
                        color_family="Navy", thumbnail_url="http://x/i.jpg")
            db.add(p)
            db.flush()
            s = ProductSKU(product_id=p.id, sku_code=f"{tag}-{uuid.uuid4().hex[:8]}",
                           size="M", color="Navy", stock_level=10, brand_id=brand.id)
            db.add(s)
            db.flush()
            return p, s

        pa, sku_a = make_product(ba, "a")
        pb, sku_b = make_product(bb, "b")

        # Brand A owns exactly one store. Brand B owns none.
        store_a = StoreLocation(brand_id=ba.id, name="A Mall", name_ar="أ", address="addr",
                                city="Dubai", country="UAE", latitude=25.0, longitude=55.0)
        db.add(store_a)
        db.flush()

        # Legitimate row: A's store holding A's SKU.
        db.add(StoreInventory(store_id=store_a.id, sku_id=sku_a.id, brand_id=ba.id,
                              quantity=7, reserved_quantity=1))

        # THE LEAK, reproduced exactly: A's store holding B's SKU, with no
        # brand_id (the legacy shape). Pre-fix this rendered in B's portal.
        db.add(StoreInventory(store_id=store_a.id, sku_id=sku_b.id,
                              brand_id=None, quantity=6, reserved_quantity=0))
        db.commit()

        ids = {"a": ba.id, "b": bb.id, "store_a": store_a.id,
               "sku_a": sku_a.id, "sku_b": sku_b.id}
        tokens = {
            "a": create_access_token({"sub": str(ua.id)}),
            "b": create_access_token({"sub": str(ub.id)}),
        }

    previous = app.dependency_overrides.get(get_db)

    def _session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _session
    client = TestClient(app)
    try:
        yield client, tokens, ids, factory
    finally:
        if previous:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_brand_with_no_stores_sees_no_store_inventory(tenants):
    """The exact production bug: COS had 0 stores but saw 'Store #1: 6 avail'."""
    client, tokens, _ids, _f = tenants

    stores = client.get("/api/v1/partner/stores", headers=_auth(tokens["b"]))
    assert stores.status_code == 200
    assert stores.json() == [], "Brand B owns no stores"

    inv = client.get("/api/v1/partner/inventory", headers=_auth(tokens["b"]))
    assert inv.status_code == 200

    leaked = [si for item in inv.json() for sku in item["skus"]
              for si in sku["store_inventories"]]
    assert leaked == [], (
        "Brand B has zero stores, so it must see zero store-level inventory rows. "
        f"Leaked another tenant's rows: {leaked}"
    )


def test_store_count_and_breakdown_never_disagree(tenants):
    """Contract test demanded by the audit remediation plan: every store id in
    the SKU breakdown must exist in the tenant's own store list."""
    client, tokens, _ids, _f = tenants

    for tenant in ("a", "b"):
        headers = _auth(tokens[tenant])
        store_ids = {s["id"] for s in client.get("/api/v1/partner/stores", headers=headers).json()}
        inv = client.get("/api/v1/partner/inventory", headers=headers).json()
        referenced = {si["store_id"] for item in inv for sku in item["skus"]
                      for si in sku["store_inventories"]}

        assert referenced <= store_ids, (
            f"Tenant {tenant}: inventory references store ids {referenced - store_ids} "
            f"that are not in its own store list {store_ids}. This is the "
            "count/breakdown mismatch the audit flagged."
        )
        if not store_ids:
            assert not referenced, "No stores must imply no store breakdown"


def test_owning_tenant_still_sees_its_own_inventory(tenants):
    """The fix must not over-correct: brand A's legitimate row survives, and is
    now labelled with the store NAME rather than a bare id."""
    client, tokens, ids, _f = tenants
    inv = client.get("/api/v1/partner/inventory", headers=_auth(tokens["a"])).json()

    rows = [si for item in inv for sku in item["skus"] for si in sku["store_inventories"]]
    assert len(rows) == 1, f"Brand A should see exactly its own row, got {rows}"
    assert rows[0]["store_id"] == ids["store_a"]
    assert rows[0]["quantity"] == 7
    assert rows[0]["reserved"] == 1
    assert rows[0]["available"] == 6
    assert rows[0]["store_name"] == "A Mall"


def test_cross_tenant_detector_finds_planted_row(tenants):
    """The detective control must actually detect. If this test ever fails,
    the audit script guarding production is blind."""
    _client, _tokens, ids, factory = tenants
    with factory() as db:
        violations = BrandRepository(db).find_cross_tenant_inventory()

    assert len(violations) == 1, f"Expected the planted leak to be detected, got {violations}"
    v = violations[0]
    assert v["store_brand_id"] == ids["a"]
    assert v["product_brand_id"] == ids["b"]


def test_inventory_write_refuses_to_adopt_another_tenants_row(tenants):
    """Writing stock must not silently take ownership of a foreign row."""
    _client, _tokens, ids, factory = tenants
    with factory() as db:
        repo = BrandRepository(db)
        # Brand B trying to write against brand A's store must be refused on
        # the store-ownership check, not quietly succeed.
        with pytest.raises(ValueError, match="does not belong to brand"):
            repo.update_store_inventory(store_id=ids["store_a"], sku_id=ids["sku_b"],
                                        quantity=5, brand_id=ids["b"])


def test_repository_map_is_scoped_to_one_tenant(tenants):
    """Unit-level proof that the shared query (single source of truth for both
    the count and the breakdown) is scoped on BOTH sides of the join."""
    _client, _tokens, ids, factory = tenants
    with factory() as db:
        repo = BrandRepository(db)
        assert repo.get_brand_store_inventory_map(ids["b"]) == {}, \
            "Brand B owns no stores; its inventory map must be empty"

        map_a = repo.get_brand_store_inventory_map(ids["a"])
        assert set(map_a) == {ids["sku_a"]}, "Brand A must see only its own SKU"
        assert map_a[ids["sku_a"]][0].store_id == ids["store_a"]
