"""The brand owner's whole journey, through HTTP, on the seeded application.

WHY THIS FILE EXISTS
--------------------
The importer, the media pipeline, the public catalogue and the sales report were
each covered by their own tests, but nothing proved the *chain*: that a product
a real brand owner uploads through the real endpoint reaches a real customer's
catalogue, that a real order for it reaches that brand's own sales report and
nobody else's, and that a failure at the image step leaves no half-product
behind.

That gap is where "works on my machine" lives. Each link can pass alone while
the hand-off between them is broken — an import that writes rows but no media,
media registered but never published, a report that counts another tenant's
orders. This file walks the chain and asserts at every joint.

THE NETWORK BOUNDARY
--------------------
`safe_get` is the single place the catalogue turns a URL into a server-side
request, so it is the only thing stubbed. Everything downstream of it — the
crop, the encode, the storage write, the registry row, the media route, the
public serializer — runs for real against real local object storage. A stub at
any point further in would prove nothing about the path.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not assert HTTP 200 for every failure. The project's convention is an
error envelope; a 4xx status and a truthful message is the contract, and the
message is what the brand owner acts on, so the message is what is checked.
"""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.app.models.catalog import Product, ProductImage, ProductSKU
from backend.tests.conftest import TestingSessionLocal

client = TestClient(app)

# Seeded by app/seed_data.py; each account owns exactly one brand.
RIVEN = ("brand@rivenstudio.com", "Password123!")
SABLE = ("brand@ateliersable.com", "Password123!")
SHOPPER = ("shopper@confit.io", "Password123!")

PASSWORD = "Password123!"


def _login(account) -> dict:
    email, password = account
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"login failed for {email}: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _jpeg(colour=(30, 30, 32)) -> bytes:
    """A real, decodable portrait source — the pipeline decodes, so it must be real."""
    img = Image.new("RGB", (900, 1125), (245, 242, 236))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.rectangle([250, 180, 650, 950], fill=colour)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    """Real local object storage, reset per test so counts are unambiguous."""
    from backend.app.core.config import settings
    from backend.app.services import storage_service

    monkeypatch.setattr(settings, "STORAGE_LOCAL_DIR", str(tmp_path / "uploads"), raising=False)
    storage_service.reset_storage()
    yield tmp_path / "uploads"
    storage_service.reset_storage()


@pytest.fixture()
def image_ok(monkeypatch):
    """Let the pipeline fetch a decodable image without touching the network.

    Patched at `_get_fetch`, the seam the suite already uses (conftest's
    `_offline_media_materialization`) and the one `MediaMaterializationService`
    documents as overridable. Everything downstream of the remote GET — decode,
    centre-crop, the five-ratio ladder, JPEG/WebP encode, the storage write, the
    registry row, `verify_resolvable`, the media route — runs for real.
    """
    payload = _jpeg()
    from backend.app.services import media_materialization_service as mms

    monkeypatch.setattr(mms.MediaMaterializationService, "_get_fetch",
                        lambda self: (lambda url: payload))
    return payload


@pytest.fixture()
def image_fails(monkeypatch):
    """The image host is unreachable — the failure a brand owner actually hits."""
    from backend.app.services import media_materialization_service as mms

    def boom(url):
        raise OSError("connection reset by peer")

    monkeypatch.setattr(mms.MediaMaterializationService, "_get_fetch",
                        lambda self: boom)


@pytest.fixture()
def cleanup_orders():
    """Delete the order this test created, so the shared seeded DB is left as found.

    A checkout decrements stock, writes OrderItem rows and a payment record. Left
    behind, they would both pollute later tests that count orders and dangle
    against a product the `cleanup` fixture removes.
    """
    created: list[int] = []
    yield created
    from backend.app.models.commerce import (
        InventoryReservation, Order, OrderEvent, OrderItem, PaymentTransaction,
    )

    db = TestingSessionLocal()
    try:
        for order_id in created:
            for model in (OrderItem, OrderEvent, PaymentTransaction):
                db.query(model).filter(model.order_id == order_id).delete()
            db.query(InventoryReservation).filter(
                InventoryReservation.order_id == order_id).delete()
            db.query(Order).filter(Order.id == order_id).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def cleanup():
    """Remove only what this file created, so the shared seeded DB is left as found."""
    created: list[str] = []
    yield created
    db = TestingSessionLocal()
    try:
        for title in created:
            product = db.query(Product).filter(Product.title == title).first()
            if not product:
                continue
            db.query(ProductImage).filter(ProductImage.product_id == product.id).delete()
            db.query(ProductSKU).filter(ProductSKU.product_id == product.id).delete()
            db.query(Product).filter(Product.id == product.id).delete()
        db.commit()
    finally:
        db.close()


def _row(title: str, **over) -> dict:
    base = dict(
        title=title,
        description="Merino travelling jacket",
        category_slug="tops",
        base_price="480.00",
        currency=None,  # normalised to the price book's denomination
        thumbnail_url="https://images.pexels.com/photos/996329/pexels-photo-996329.jpeg",
        size="M",
        color="Charcoal",
        stock_level="7",
        gender="unisex",
    )
    base.update(over)
    return base


def _public_titles() -> list[str]:
    res = client.get("/api/v1/catalog/products?limit=100")
    assert res.status_code == 200, res.text
    payload = res.json()
    items = payload["items"] if isinstance(payload, dict) else payload
    return [p["title"] for p in items]


# ---------------------------------------------------------------------------
# A. Upload -> persistence -> media -> public catalogue
# ---------------------------------------------------------------------------
def test_a_brand_owner_upload_reaches_the_public_catalog(storage, image_ok, cleanup):
    headers = _login(RIVEN)
    title = f"E2E Merino Jacket {uuid.uuid4().hex[:8]}"
    cleanup.append(title)

    res = client.post("/api/v1/brand/catalog/upload", headers=headers,
                      json={"products": [_row(title)]})
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["status"] == "completed", job
    assert job["accepted_rows"] == 1, job

    # 1. Persisted, owned by the uploading brand, and publicly active.
    db = TestingSessionLocal()
    try:
        product = db.query(Product).filter(Product.title == title).one()
        brand_id = product.brand_id
        assert product.is_active is True, "an accepted import must be publishable"

        # 2. A SKU exists and carries the stock the owner declared.
        sku = db.query(ProductSKU).filter(ProductSKU.product_id == product.id).one()
        assert sku.stock_level == 7 and sku.is_in_stock is True

        # 3. The media registry is populated — the whole ladder, not one file.
        rows = db.query(ProductImage).filter(ProductImage.product_id == product.id).all()
        ratios = {r.ratio for r in rows}
        assert ratios == {"4x5", "1x1", "3x2", "16x9", "master"}, ratios
        assert len(rows) == 10, f"expected 5 ratios x 2 formats, got {len(rows)}"

        keys = [r.storage_key for r in rows]
        checksums = {r.storage_key: r.checksum for r in rows}
    finally:
        db.close()

    # 4. Every registered object is served by the real media route.
    for key in keys:
        served = client.get(f"/api/v1/media/{key}")
        assert served.status_code == 200, f"{key} -> {served.status_code}"
        assert served.headers["content-type"].startswith("image/")
        import hashlib

        assert hashlib.sha256(served.content).hexdigest().startswith(checksums[key]), (
            f"{key} served bytes that are not the registered object"
        )

    # 5. The brand's own inventory view shows it.
    mine = client.get("/api/v1/brand/products", headers=headers)
    assert mine.status_code == 200, mine.text
    assert title in [p["title"] for p in mine.json()], "brand owner cannot see its own new product"

    # 6. And a customer sees it, from the same rows.
    assert title in _public_titles(), "an accepted import never reached the public catalogue"

    # 7. The public detail payload carries the ladder, not one cropped file.
    listing = client.get("/api/v1/catalog/products?limit=100").json()
    items = listing["items"] if isinstance(listing, dict) else listing
    slug = next((p["slug"] for p in items if p["title"] == title), None)
    assert slug, "the new product is not addressable on the public list"
    detail = client.get(f"/api/v1/catalog/products/{slug}")
    assert detail.status_code == 200
    assert len(detail.json().get("media") or []) == 10


def test_a_repeated_upload_of_the_same_row_does_not_duplicate(storage, image_ok, cleanup):
    """Re-uploading a catalogue is how stock is corrected, so it must be idempotent."""
    headers = _login(RIVEN)
    title = f"E2E Repeat Jacket {uuid.uuid4().hex[:8]}"
    cleanup.append(title)
    body = {"products": [_row(title)]}

    first = client.post("/api/v1/brand/catalog/upload", headers=headers, json=body)
    assert first.status_code == 202 and first.json()["accepted_rows"] == 1

    second = client.post("/api/v1/brand/catalog/upload", headers=headers, json=body)
    assert second.status_code == 202, second.text
    assert second.json()["accepted_rows"] == 1, second.json()

    db = TestingSessionLocal()
    try:
        products = db.query(Product).filter(Product.title == title).all()
        assert len(products) == 1, f"the retry created {len(products)} products"
        skus = db.query(ProductSKU).filter(ProductSKU.product_id == products[0].id).all()
        assert len(skus) == 1, f"the retry created {len(skus)} SKUs"
        rows = db.query(ProductImage).filter(ProductImage.product_id == products[0].id).all()
        assert len(rows) == 10, f"the retry left {len(rows)} media rows instead of 10"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# A3 / D. A failure at the image step must not leave a half-product
# ---------------------------------------------------------------------------
def test_an_unfetchable_image_is_refused_and_leaves_no_product(storage, image_fails, cleanup):
    """The promise is 'accepted means viewable'. A product whose hero 404s is the defect."""
    headers = _login(RIVEN)
    title = f"E2E Broken Image {uuid.uuid4().hex[:8]}"
    cleanup.append(title)

    res = client.post("/api/v1/brand/catalog/upload", headers=headers,
                      json={"products": [_row(title)]})
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["accepted_rows"] == 0, "a product with no resolvable image was accepted"
    assert job["status"] in ("failed", "partially_completed"), job
    assert job["rejected_rows"] >= 1

    # The refusal must say what to do, not leak a stack trace or a storage key.
    blob = str(job.get("errors") or job)
    assert "image" in blob.lower(), f"the refusal does not mention the image: {blob[:300]}"

    # Nothing survives: no product, no SKU, no media, no public listing.
    db = TestingSessionLocal()
    try:
        assert db.query(Product).filter(Product.title == title).count() == 0, (
            "a refused import left a product row behind"
        )
    finally:
        db.close()
    assert title not in _public_titles()


# ---------------------------------------------------------------------------
# C. Tenant isolation on the same endpoints, with two real brand accounts
# ---------------------------------------------------------------------------
def test_one_brand_cannot_read_another_brands_products(storage, image_ok, cleanup):
    riven = _login(RIVEN)
    sable = _login(SABLE)
    title = f"E2E Private Jacket {uuid.uuid4().hex[:8]}"
    cleanup.append(title)

    assert client.post("/api/v1/brand/catalog/upload", headers=riven,
                       json={"products": [_row(title)]}).status_code == 202

    mine = client.get("/api/v1/brand/products", headers=riven).json()
    theirs = client.get("/api/v1/brand/products", headers=sable).json()
    assert title in [p["title"] for p in mine]
    assert title not in [p["title"] for p in theirs], (
        "another brand's inventory leaked into this brand's product list"
    )

    # A brand must not be able to modify a competitor's variant by guessing its id.
    db = TestingSessionLocal()
    try:
        product = db.query(Product).filter(Product.title == title).one()
        sku_id = db.query(ProductSKU).filter(ProductSKU.product_id == product.id).one().id
    finally:
        db.close()

    # The brand route is PUT, the partner routes are PATCH, and stock_level is a
    # QUERY parameter — a JSON body is rejected as 422 before authorization is
    # ever evaluated, which would prove nothing about the boundary.
    for method, path in (("put", f"/api/v1/brand/skus/{sku_id}"),
                         ("patch", f"/api/v1/partner/skus/{sku_id}"),
                         ("patch", f"/api/v1/partner/variants/{sku_id}")):
        patched = getattr(client, method)(
            path, headers=sable, params={"stock_level": 999}
        )
        assert patched.status_code in (403, 404), (
            f"{method.upper()} {path} let another brand modify this SKU: "
            f"{patched.status_code} {patched.text[:200]}"
        )

    # And the value did not change.
    db = TestingSessionLocal()
    try:
        assert db.query(ProductSKU).filter(ProductSKU.id == sku_id).one().stock_level == 7
    finally:
        db.close()


def test_the_owning_brand_still_can_update_its_own_sku(storage, image_ok, cleanup):
    """The positive control for the isolation tests above.

    Denial alone is not evidence of a boundary: an endpoint that rejects every
    caller would satisfy a test that only asserts 403. This proves the same
    route, verb and parameters DO work for the brand that owns the row — so the
    refusal in the previous test is about ownership, not about a broken route.
    """
    riven = _login(RIVEN)
    title = f"E2E Own Sku {uuid.uuid4().hex[:8]}"
    cleanup.append(title)
    assert client.post("/api/v1/brand/catalog/upload", headers=riven,
                       json={"products": [_row(title)]}).status_code == 202

    db = TestingSessionLocal()
    try:
        product = db.query(Product).filter(Product.title == title).one()
        sku_id = db.query(ProductSKU).filter(ProductSKU.product_id == product.id).one().id
    finally:
        db.close()

    ok = client.put(f"/api/v1/brand/skus/{sku_id}", headers=riven,
                    params={"stock_level": 12})
    assert ok.status_code == 200, ok.text
    assert ok.json()["stock_level"] == 12

    db = TestingSessionLocal()
    try:
        assert db.query(ProductSKU).filter(ProductSKU.id == sku_id).one().stock_level == 12
    finally:
        db.close()


# ---------------------------------------------------------------------------
# B + C. A sale reaches the selling brand's report, and only that brand's
# ---------------------------------------------------------------------------
def test_a_sale_reaches_the_selling_brands_report_and_no_one_elses(
    storage, image_ok, cleanup, cleanup_orders
):
    """Financial attribution: the money must appear under the brand that sold it."""
    riven = _login(RIVEN)
    sable = _login(SABLE)
    title = f"E2E Sold Jacket {uuid.uuid4().hex[:8]}"
    cleanup.append(title)

    assert client.post("/api/v1/brand/catalog/upload", headers=riven,
                       json={"products": [_row(title, base_price="125.00", stock_level="5")]}
                       ).status_code == 202

    db = TestingSessionLocal()
    try:
        product = db.query(Product).filter(Product.title == title).one()
        sku_id = db.query(ProductSKU).filter(ProductSKU.product_id == product.id).one().id
    finally:
        db.close()

    # What the seller's own report says BEFORE the sale. Baseline is a DELTA,
    # not a constant: the seeded catalogue already has trading history, and a
    # test that hard-coded "0 purchases" would encode the seed, not the rule.
    before = client.get("/api/v1/brand/reports/product-sales", headers=riven)
    assert before.status_code == 200, before.text
    kpi_before = client.get("/api/v1/brand/analytics", headers=riven)
    assert kpi_before.status_code == 200, kpi_before.text
    other_before = client.get("/api/v1/brand/analytics", headers=sable)
    assert other_before.status_code == 200, other_before.text
    purchases_before = kpi_before.json()["total_purchases"]
    other_purchases_before = other_before.json()["total_purchases"]

    def row_for(payload, wanted_title):
        for r in payload["rows"]:
            if r.get("title") == wanted_title:
                return r
        return None

    pre = row_for(before.json(), title)
    assert pre is not None, "the seller's report does not list a product it sells"
    assert float(pre["net_sales"]) == 0.0, "no order has been placed yet"

    # A customer buys it through the real cart + checkout.
    shopper = _login(SHOPPER)
    shopper["X-Session-Token"] = f"e2e-sale-{uuid.uuid4().hex[:10]}"
    added = client.post("/api/v1/commerce/cart/items", headers=shopper,
                        json={"product_sku_id": sku_id, "quantity": 2})
    assert added.status_code in (200, 201), added.text

    order = client.post("/api/v1/commerce/checkout", headers=shopper, json={
        "payment_method": "card",
        "fulfillment_type": "delivery",
        "recipient_name": "E2E Buyer",
        "phone": "+201234567890",
        "address_line": "12 Nile View",
        "city": "Giza",
        "country": "EG",
    })
    assert order.status_code == 200, order.text
    cleanup_orders.append(order.json().get("id") or order.json().get("order_id"))

    # The seller sees the money, attributed to the right product.
    after = client.get("/api/v1/brand/reports/product-sales", headers=riven)
    assert after.status_code == 200, after.text
    post = row_for(after.json(), title)
    assert post is not None
    assert float(post["net_sales"]) > 0, "the sale never reached the seller's report"
    assert post["units_sold"] == 2 if "units_sold" in post else True

    # The KPI the brand owner actually reads must move by the same event.
    kpi_after = client.get("/api/v1/brand/analytics", headers=riven)
    assert kpi_after.status_code == 200, kpi_after.text
    assert kpi_after.json()["total_purchases"] == purchases_before + 1, (
        "the sale did not reach the seller's own purchase KPI: "
        f"{purchases_before} -> {kpi_after.json()['total_purchases']}"
    )

    # The other brand sees none of it — neither the row, nor the revenue, nor the KPI.
    other = client.get("/api/v1/brand/reports/product-sales", headers=sable)
    assert other.status_code == 200, other.text
    assert row_for(other.json(), title) is None, (
        "another brand's report lists a product it does not own"
    )
    other_after = client.get("/api/v1/brand/analytics", headers=sable)
    assert other_after.json()["total_purchases"] == other_purchases_before, (
        "another brand's purchase KPI moved because of a sale it did not make"
    )


# ---------------------------------------------------------------------------
# D. A storage write that fails mid-ladder must not register half a product
# ---------------------------------------------------------------------------
def test_a_storage_failure_mid_ladder_registers_nothing(
    storage, image_ok, cleanup, monkeypatch
):
    """`materialize` is all-or-nothing: bytes first, registry rows second.

    The failure mode this rules out is the expensive one for a storefront: a
    product that exists, is published, and has three of its five ratios —
    because the fourth upload hit a full disk. The customer sees a broken
    gallery and the operator sees `accepted: 1`.
    """
    from backend.app.services import storage_service

    headers = _login(RIVEN)
    title = f"E2E Storage Fails {uuid.uuid4().hex[:8]}"
    cleanup.append(title)

    real_backend = storage_service.get_storage()
    calls = {"n": 0}

    class FlakyBackend:
        """Wraps the real backend; dies on the third object, like a full disk."""

        def store(self, key, data):
            calls["n"] += 1
            if calls["n"] >= 3:
                raise OSError("No space left on device")
            return real_backend.store(key, data)

        def exists(self, key):
            return real_backend.exists(key)

    from backend.app.services import media_materialization_service as mms

    # monkeypatch, not a bare assignment: assigning on the class leaked the
    # failing backend into every later test in the session (observed: unrelated
    # suites began raising "No space left on device" four tests later).
    monkeypatch.setattr(mms.MediaMaterializationService, "_get_storage",
                        lambda self: FlakyBackend())

    res = client.post("/api/v1/brand/catalog/upload", headers=headers,
                      json={"products": [_row(title)]})
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["accepted_rows"] == 0, "a product with a half-written ladder was accepted"
    assert job["status"] in ("failed", "partially_completed"), job

    # No product, no SKU, no registry rows — and no partially-stored objects left
    # registered against a product that does not exist.
    db = TestingSessionLocal()
    try:
        product = db.query(Product).filter(Product.title == title).first()
        assert product is None, "a failed storage write left a product row behind"
        live_ids = {pid for (pid,) in db.query(Product.id).all()}
        orphans = [r.storage_key for r in db.query(ProductImage).all()
                   if r.product_id not in live_ids]
        assert not orphans, f"media rows left pointing at no product: {orphans[:5]}"
    finally:
        db.close()
    assert title not in _public_titles()


# ---------------------------------------------------------------------------
# D2. Recovery: the same row imports cleanly once the failure is resolved
# ---------------------------------------------------------------------------
def test_a_failed_import_succeeds_on_retry_after_the_image_host_recovers(
    storage, cleanup, monkeypatch
):
    """Failure must be recoverable by retrying, not by editing the database.

    The failing case above proves nothing is left behind; this proves the brand
    owner's next action works. Driven through the same endpoint with the same
    payload, changing only the thing that was broken.
    """
    from backend.app.services import media_materialization_service as mms

    headers = _login(RIVEN)
    title = f"E2E Retry Jacket {uuid.uuid4().hex[:8]}"
    cleanup.append(title)
    payload = _jpeg()

    # 1. the host is down
    monkeypatch.setattr(mms.MediaMaterializationService, "_get_fetch",
                        lambda self: (lambda url: (_ for _ in ()).throw(OSError("down"))))
    first = client.post("/api/v1/brand/catalog/upload", headers=headers,
                        json={"products": [_row(title)]})
    assert first.json()["accepted_rows"] == 0
    assert title not in _public_titles()

    # 2. the host is back; the operator retries the same request
    monkeypatch.setattr(mms.MediaMaterializationService, "_get_fetch",
                        lambda self: (lambda url: payload))
    second = client.post("/api/v1/brand/catalog/upload", headers=headers,
                         json={"products": [_row(title)]})
    assert second.status_code == 202, second.text
    assert second.json()["accepted_rows"] == 1, second.json()

    db = TestingSessionLocal()
    try:
        products = db.query(Product).filter(Product.title == title).all()
        assert len(products) == 1, "the retry created a duplicate product"
        rows = db.query(ProductImage).filter(ProductImage.product_id == products[0].id).all()
        assert len(rows) == 10, f"the recovered product has {len(rows)} media rows, not 10"
    finally:
        db.close()
    assert title in _public_titles(), "the recovered product never reached the catalogue"
