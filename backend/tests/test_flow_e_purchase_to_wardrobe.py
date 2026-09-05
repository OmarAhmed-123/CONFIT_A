"""FLOW E regression suite - G5 completed purchase -> G4 personal wardrobe.

Before this change the contract existed only in documentation: nothing in the
codebase turned a paid order into wardrobe items, so G4 (and everything G4
feeds - G2 wardrobe-first recommendations, gap analysis, smart reuse) could
never see anything the customer actually bought.

These tests drive the REAL HTTP checkout endpoint and then assert against the
database it wrote. They pin the six properties FLOW E requires:

1. a completed purchase materialises wardrobe items owned by the buyer,
2. every field is derived server-side from the persisted OrderItem + catalog
   (never from client-supplied product data, price, category or ownership),
3. the sync is idempotent - retries/re-deliveries cannot duplicate a piece,
4. a guest purchase is a clean no-op (no wardrobe owner exists),
5. a wardrobe failure can never corrupt or falsify the purchase,
6. cross-user isolation holds, and returned / payment-failed lines are not
   (or no longer) in the wardrobe.

Plus the migration that makes (3) a database guarantee rather than an
application habit: 0015 upgrade -> unique lineage index -> downgrade -> upgrade.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from backend.tests.conftest import TestingSessionLocal


# --------------------------------------------------------------------------
# Shared-state isolation
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _restore_catalog_stock():
    """These tests drive the REAL checkout endpoint, which really decrements
    ``product_skus.stock_level``. Other suites pick "the first in-stock SKU of
    products[0]" (test_group5_commerce._first_product_and_sku) and raise
    StopIteration when the seeded catalog has been bought out, so this file
    must not leave its purchases behind in the shared test database.

    Snapshot-and-restore keeps the seeded catalog deterministic without
    touching any other suite's fixtures or assumptions.
    """
    db = TestingSessionLocal()
    try:
        before = db.execute(
            text("select id, stock_level, is_in_stock from product_skus")).all()
    finally:
        db.close()

    yield

    db = TestingSessionLocal()
    try:
        for sku_id, stock_level, is_in_stock in before:
            db.execute(
                text("update product_skus set stock_level = :s, is_in_stock = :i "
                     "where id = :id"),
                {"s": stock_level, "i": is_in_stock, "id": sku_id},
            )
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Helpers (same conventions as test_attribution_item_grain_e2e.py)
# --------------------------------------------------------------------------
def _register(client: TestClient) -> tuple[str, str]:
    email = f"flowe_{uuid.uuid4().hex[:8]}@confit.io"
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "Flow E Buyer"})
    assert r.status_code == 201, r.text
    return email, r.json()["access_token"]


def _headers(token: str, session_token: str) -> dict:
    """carts.session_token is UNIQUE, so every test needs its own."""
    return {"Authorization": f"Bearer {token}", "X-Session-Token": session_token}


def _empty_cart(client: TestClient, headers: dict) -> None:
    r = client.get("/api/v1/commerce/cart", headers=headers)
    if r.status_code != 200:
        return
    for it in r.json().get("items", []):
        cid = it.get("id") or it.get("cart_item_id")
        if cid:
            client.delete(f"/api/v1/commerce/cart/items/{cid}", headers=headers)


def _in_stock_sku(client: TestClient) -> dict:
    products = client.get("/api/v1/catalog/products").json()
    assert products, "seeded catalog is empty"
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    return next(s for s in detail["skus"] if s["is_in_stock"])


def _buy_one(client: TestClient, headers: dict, extra: dict | None = None) -> dict:
    _empty_cart(client, headers)
    sku = _in_stock_sku(client)
    added = client.post("/api/v1/commerce/cart/items",
                        json={"product_sku_id": sku["id"], "quantity": 1}, headers=headers)
    assert added.status_code in (200, 201), added.text
    payload = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Flow E Buyer",
        "phone": "+971500000000",
        "address_line": "1 Corniche",
        "city": "Dubai",
        "country": "AE",
    }
    payload.update(extra or {})
    r = client.post("/api/v1/commerce/checkout", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _wardrobe(client: TestClient, headers: dict) -> list[dict]:
    r = client.get("/api/v1/wardrobe/items", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _synced_rows(order_number: str) -> list[dict]:
    db = TestingSessionLocal()
    try:
        return db.execute(text(
            "select w.id, w.user_id, w.title, w.category, w.subcategory, w.color_name, "
            "w.color_hex, w.brand_name, w.image_url, w.purchase_price, w.source_order_item_id, "
            "oi.id as oi_id, oi.product_id, oi.unit_price, oi.is_returned, o.user_id as owner_id, "
            "o.order_number "
            "from wardrobe_items w "
            "join order_items oi on oi.id = w.source_order_item_id "
            "join orders o on o.id = oi.order_id "
            "where o.order_number = :on"
        ), {"on": order_number}).mappings().all()
    finally:
        db.close()


# --------------------------------------------------------------------------
# 1 + 2: purchase materialises catalog-derived, buyer-owned wardrobe items
# --------------------------------------------------------------------------
def test_completed_purchase_creates_wardrobe_items_owned_by_buyer(client: TestClient) -> None:
    email, token = _register(client)
    headers = _headers(token, f"flowe_own_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers)

    rows = _synced_rows(order["order_number"])
    assert len(rows) == len(order["items"]), (
        f"expected one wardrobe item per persisted OrderItem, got {len(rows)} "
        f"for {len(order['items'])} lines")
    for row in rows:
        assert row["owner_id"] is not None, "wardrobe item must belong to the buyer"
        assert row["user_id"] == row["owner_id"], (
            "wardrobe ownership must equal the ORDER's owner - never a client value")
        assert row["source_order_item_id"] == row["oi_id"]

    # Visible through the buyer's own wardrobe API.
    mine = _wardrobe(client, headers)
    synced_titles = {r["title"] for r in rows}
    assert synced_titles & {m["title"] for m in mine}, (
        "synchronised purchase did not appear in GET /wardrobe/items")


def test_wardrobe_fields_are_catalog_derived_not_client_supplied(client: TestClient) -> None:
    email, token = _register(client)
    headers = _headers(token, f"flowe_cat_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers)
    rows = _synced_rows(order["order_number"])
    assert rows

    db = TestingSessionLocal()
    try:
        for row in rows:
            cat = db.execute(text(
                "select p.title, p.thumbnail_url, p.color_family, p.dominant_hex, "
                "c.name as category_name, b.brand_name as brand_name "
                "from products p join categories c on c.id = p.category_id "
                "join brand_profiles b on b.id = p.brand_id where p.id = :pid"
            ), {"pid": row["product_id"]}).mappings().first()
            assert cat, "OrderItem.product_id must resolve to a catalog product"
            # Title / image / brand come from the CATALOG (live truth).
            assert row["title"] == cat["title"]
            assert row["image_url"] == cat["thumbnail_url"]
            assert row["brand_name"] == cat["brand_name"]
            # Subcategory is the catalog category name; category is the
            # normalised wardrobe taxonomy value (never free text).
            assert row["subcategory"] == cat["category_name"]
            assert row["category"] in {
                "Tops", "Bottoms", "Outerwear", "Footwear", "Accessories", "Dresses"}
            # Money truth = the persisted order line (Decimal, exact).
            assert Decimal(str(row["purchase_price"])) == Decimal(str(row["unit_price"]))
    finally:
        db.close()


def test_client_cannot_inject_ownership_category_price_or_title(client: TestClient) -> None:
    """A tampering client sends its own owner/category/price/title in the
    checkout body. None of it may reach the wardrobe."""
    email, token = _register(client)
    headers = _headers(token, f"flowe_tamper_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers, extra={
        "user_id": 999999,
        "category": "HACKED",
        "purchase_price": 1.0,
        "title": "HACKED TITLE",
        "brand_name": "HACKED BRAND",
        "image_url": "https://evil.example/hack.png",
    })
    rows = _synced_rows(order["order_number"])
    assert rows, "purchase must still synchronise"
    for row in rows:
        assert row["user_id"] == row["owner_id"]
        assert row["category"] != "HACKED"
        assert row["title"] != "HACKED TITLE"
        assert row["brand_name"] != "HACKED BRAND"
        assert row["image_url"] != "https://evil.example/hack.png"
        assert Decimal(str(row["purchase_price"])) == Decimal(str(row["unit_price"]))
        assert Decimal(str(row["purchase_price"])) != Decimal("1.00")


# --------------------------------------------------------------------------
# 3: idempotency
# --------------------------------------------------------------------------
def test_sync_is_idempotent_across_retries(client: TestClient) -> None:
    from backend.app.services.commerce_service import CommerceService

    email, token = _register(client)
    headers = _headers(token, f"flowe_idem_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers)
    first = _synced_rows(order["order_number"])
    assert first

    db = TestingSessionLocal()
    try:
        svc = CommerceService(db)
        for _ in range(3):
            summary = svc.sync_wardrobe_for_order(order["order_number"])
            assert summary["status"] == "synced", summary
            assert summary["created"] == 0, summary
            assert summary["already_synced"] == len(first), summary
    finally:
        db.close()

    after = _synced_rows(order["order_number"])
    assert len(after) == len(first), "retry duplicated wardrobe items"
    assert {r["id"] for r in after} == {r["id"] for r in first}


def test_database_rejects_a_second_item_for_the_same_order_line(client: TestClient) -> None:
    """The uniqueness must be a DATABASE guarantee, not application discipline."""
    from sqlalchemy.exc import IntegrityError

    email, token = _register(client)
    headers = _headers(token, f"flowe_uq_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers)
    rows = _synced_rows(order["order_number"])
    assert rows

    db = TestingSessionLocal()
    try:
        with pytest.raises(IntegrityError):
            db.execute(text(
                "insert into wardrobe_items (user_id, title, category, color_name, color_hex, "
                "pattern, brand_name, image_url, ai_tags, occasions, secondary_colors, "
                "seasonality, wear_frequency, wear_count, is_favorite, processing_status, "
                "source_order_item_id, created_at) "
                "values (:u, 'dup', 'Tops', 'Black', '#000000', 'Solid', 'B', 'x', '[]', '[]', "
                "'[]', 'All-Season', 'regular', 0, 0, 'ready', :oi, CURRENT_TIMESTAMP)"
            ), {"u": rows[0]["user_id"], "oi": rows[0]["source_order_item_id"]})
            db.commit()
    finally:
        db.rollback()
        db.close()


# --------------------------------------------------------------------------
# 4: guest purchase
# --------------------------------------------------------------------------
def test_guest_purchase_is_a_clean_noop(client: TestClient) -> None:
    session_token = f"flowe_guest_{uuid.uuid4().hex[:8]}"
    headers = {"X-Session-Token": session_token}
    _empty_cart(client, headers)
    sku = _in_stock_sku(client)
    added = client.post("/api/v1/commerce/cart/items",
                        json={"product_sku_id": sku["id"], "quantity": 1}, headers=headers)
    assert added.status_code in (200, 201), added.text
    r = client.post("/api/v1/commerce/checkout", headers=headers, json={
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "guest_email": f"flowe_guest_{uuid.uuid4().hex[:6]}@example.com",
        "recipient_name": "Guest Buyer",
        "phone": "+971500000000",
        "address_line": "1 Corniche",
        "city": "Dubai",
        "country": "AE",
    })
    assert r.status_code == 200, r.text
    order = r.json()

    rows = _synced_rows(order["order_number"])
    assert rows == [], "a guest order has no wardrobe owner and must not create items"

    db = TestingSessionLocal()
    try:
        owner = db.execute(text("select user_id from orders where order_number = :on"),
                           {"on": order["order_number"]}).scalar()
    finally:
        db.close()
    assert owner is None
    # The purchase itself is unaffected.
    assert order["payment_status"] != "failed"


# --------------------------------------------------------------------------
# 5: wardrobe failure never corrupts the purchase
# --------------------------------------------------------------------------
def test_wardrobe_sync_failure_does_not_corrupt_the_purchase(
        client: TestClient, monkeypatch) -> None:
    from backend.app.services import wardrobe_service as ws

    def _boom(self, order):  # noqa: ANN001
        raise RuntimeError("simulated wardrobe backend outage")

    monkeypatch.setattr(ws.WardrobeService, "sync_items_from_order", _boom)

    email, token = _register(client)
    headers = _headers(token, f"flowe_fail_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers)

    # The shopper sees a SUCCESSFUL purchase - never a wardrobe error.
    assert order["order_number"]
    assert order["payment_status"] != "failed"
    assert order["items"]

    db = TestingSessionLocal()
    try:
        persisted = db.execute(text(
            "select o.order_number, o.payment_status, o.total_amount, "
            "(select count(*) from order_items oi where oi.order_id = o.id) as lines, "
            "(select count(*) from payment_transactions pt where pt.order_id = o.id) as tx "
            "from orders o where o.order_number = :on"), {"on": order["order_number"]}).mappings().first()
    finally:
        db.close()
    assert persisted is not None, "order must survive a wardrobe failure"
    assert persisted["lines"] == len(order["items"])
    assert persisted["tx"] >= 1, "payment transaction must be persisted"
    assert _synced_rows(order["order_number"]) == []


# --------------------------------------------------------------------------
# 6: cross-user isolation
# --------------------------------------------------------------------------
def test_cross_user_isolation(client: TestClient) -> None:
    _, token_a = _register(client)
    headers_a = _headers(token_a, f"flowe_a_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers_a)
    rows = _synced_rows(order["order_number"])
    assert rows

    _, token_b = _register(client)
    headers_b = _headers(token_b, f"flowe_b_{uuid.uuid4().hex[:8]}")
    assert _wardrobe(client, headers_b) == [], "user B must not see user A's purchases"
    for row in rows:
        r = client.get(f"/api/v1/wardrobe/items/{row['id']}", headers=headers_b)
        assert r.status_code in (403, 404), (
            f"user B read user A's wardrobe item {row['id']}: {r.status_code}")


# --------------------------------------------------------------------------
# returned lines + payment-failed rollback
# --------------------------------------------------------------------------
def test_returned_lines_are_not_synchronised(client: TestClient) -> None:
    from backend.app.services.commerce_service import CommerceService

    email, token = _register(client)
    headers = _headers(token, f"flowe_ret_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers)

    db = TestingSessionLocal()
    try:
        # Mark every purchased line as returned, then drop the synced items so
        # the re-sync has to make the decision again from scratch.
        db.execute(text(
            "update order_items set is_returned = 1 where order_id = "
            "(select id from orders where order_number = :on)"), {"on": order["order_number"]})
        db.execute(text(
            "delete from wardrobe_items where source_order_item_id in "
            "(select id from order_items where order_id = "
            " (select id from orders where order_number = :on))"), {"on": order["order_number"]})
        db.commit()
        summary = CommerceService(db).sync_wardrobe_for_order(order["order_number"])
    finally:
        db.close()

    assert summary["created"] == 0, summary
    assert summary["skipped_returned"] >= 1, summary
    assert _synced_rows(order["order_number"]) == []


def test_failed_payment_webhook_revokes_synced_items(client: TestClient, monkeypatch) -> None:
    """Provider later reports payment.failed -> the pieces were never acquired,
    so the lineage-scoped revoke removes them (uploads untouched)."""
    import hashlib
    import hmac
    import json

    from backend.app.core.config import settings

    email, token = _register(client)
    headers = _headers(token, f"flowe_wh_{uuid.uuid4().hex[:8]}")
    order = _buy_one(client, headers)
    assert _synced_rows(order["order_number"]), "precondition: items were synced"

    # An uploaded item with no lineage must survive the revoke.
    db = TestingSessionLocal()
    try:
        owner_id = db.execute(text("select user_id from orders where order_number = :on"),
                              {"on": order["order_number"]}).scalar()
        db.execute(text(
            "insert into wardrobe_items (user_id, title, category, color_name, color_hex, "
            "pattern, brand_name, image_url, ai_tags, occasions, secondary_colors, seasonality, "
            "wear_frequency, wear_count, is_favorite, processing_status, source_order_item_id, "
            "created_at) values (:u, 'My Own Upload', 'Tops', 'Black', '#000000', 'Solid', "
            "'Own Collection', 'local/x.png', '[]', '[]', '[]', 'All-Season', 'regular', 0, 0, "
            "'ready', NULL, CURRENT_TIMESTAMP)"), {"u": owner_id})
        db.commit()
    finally:
        db.close()

    secret = "flowe-webhook-secret-under-test"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret, raising=False)
    body = json.dumps({
        "id": f"evt_flowe_{uuid.uuid4().hex[:8]}",
        "event": "payment.failed",
        "order_number": order["order_number"],
    }).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    # A real PSP webhook carries no browser cookies. The TestClient still holds
    # the shopper's confit_token cookie from the checkout above, which would
    # trip the double-submit CSRF guard - clear it so the request is what a
    # provider actually sends.
    client.cookies.clear()
    r = client.post("/api/v1/payments/webhooks/stripe", content=body,
                    headers={"Content-Type": "application/json", "X-Signature": sig})
    assert r.status_code == 200, r.text

    assert _synced_rows(order["order_number"]) == [], (
        "lineage-scoped revoke must remove synchronised purchase items")
    db = TestingSessionLocal()
    try:
        still = db.execute(text(
            "select count(*) from wardrobe_items where user_id = :u and source_order_item_id is null"
        ), {"u": owner_id}).scalar()
        status = db.execute(text("select payment_status from orders where order_number = :on"),
                            {"on": order["order_number"]}).scalar()
    finally:
        db.close()
    assert still == 1, "the customer's own uploaded item must never be deleted"
    assert status == "failed"


# --------------------------------------------------------------------------
# migration 0015: upgrade -> unique index -> downgrade -> upgrade
# --------------------------------------------------------------------------
def _alembic(url: str, direction: str, target: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        (command.upgrade if direction == "up" else command.downgrade)(cfg, target)
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


def test_migration_0015_round_trip_and_unique_lineage() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    try:
        _alembic(url, "up", "head")
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("wardrobe_items")}
        assert "source_order_item_id" in cols
        idx = {i["name"]: i for i in insp.get_indexes("wardrobe_items")}
        assert "uq_wardrobe_items_source_order_item" in idx
        # SQLite reports the flag as 1, PostgreSQL as True - assert truthiness.
        assert bool(idx["uq_wardrobe_items_source_order_item"]["unique"]) is True
        assert "ix_wardrobe_items_source_order_item_id" in idx

        with engine.begin() as conn:
            assert conn.execute(text(
                "select version_num from alembic_version")).scalar() == \
                "0016_vton_temporary_delivery"

        _alembic(url, "down", "base")
        insp = inspect(engine)
        assert "wardrobe_items" not in set(insp.get_table_names())

        _alembic(url, "up", "head")
        cols = {c["name"] for c in inspect(engine).get_columns("wardrobe_items")}
        assert "source_order_item_id" in cols
    finally:
        engine.dispose()
        os.unlink(path)


def test_migration_chain_has_a_single_head_at_0016() -> None:
    from backend.app.core.schema_gate import expected_head_revision, migration_chain

    chain = migration_chain()
    downs = {d for d in chain.values() if d}
    heads = [r for r in chain if r not in downs]
    assert heads == [expected_head_revision()]
    # 0016 (VTON temporary-delivery metadata) extends 0015; the chain must
    # remain single-headed and the head must move consciously.
    assert expected_head_revision() == "0016_vton_temporary_delivery"
    assert "0015_wardrobe_purchase_lineage" in chain.values()
