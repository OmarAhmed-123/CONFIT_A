"""
Comprehensive Real-World End-to-End, Security, Media, Analytics, CSV, Wishlist
and Fault-Injection Verification Suite covering Mandate Workstreams 2–9.

Design rules strictly enforced in every test:
1. Positive-control-first, negative-control-second on every BOLA/BFLA assertion
   (proves HTTP 200/201 with identical valid payload on owner before asserting
   HTTP 403/404 on cross-tenant / cross-user actor — zero false-green 422s).
2. Scoped monkeypatch / unique per-test entities — zero cross-suite state leak
   and zero secrets or real PII anywhere.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from PIL import Image

from backend.tests.conftest import TestingSessionLocal
from backend.app.models import (
    BrandAnalyticsEvent,
    BrandMembership,
    BrandProfile,
    CatalogImportJob,
    Category,
    Product,
    ProductSKU,
    StoreInventory,
    StoreLocation,
    User,
    UserRole,
    UserWishlistItem,
)
from backend.app.models.catalog import ProductImage
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.services.auth_service import AuthService
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.services.business_intelligence_service import BusinessIntelligenceService
from backend.app.core.security import get_password_hash


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    before_img_ids = {r[0] for r in session.query(ProductImage.id).all()}
    try:
        yield session
    finally:
        try:
            q = session.query(ProductImage)
            if before_img_ids:
                q = q.filter(ProductImage.id.notin_(before_img_ids))
            q.delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()


def _register_and_auth(client, prefix: str, password: str = "StrongPass!2026Aa") -> tuple[dict, int]:
    tag = uuid.uuid4().hex[:8]
    email = f"{prefix}-{tag}@confitqa.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": f"{prefix} {tag}"},
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    token = body["access_token"]
    return {"Authorization": f"Bearer {token}"}, int(body["user"]["id"])


def _seed_two_brands_and_catalog(db_session):
    tag = uuid.uuid4().hex[:8]
    cat = Category(name=f"Outerwear {tag}", name_ar=f"ملابس خارجية {tag}", slug=f"outerwear-rw-{tag}")
    db_session.add(cat)
    db_session.flush()

    owner_a = User(
        email=f"owner-a-{tag}@confitqa.com",
        hashed_password=get_password_hash("StrongPass!2026Aa"),
        full_name="Owner Brand A",
        role=UserRole.BRAND_MANAGER,
        is_active=True,
    )
    owner_b = User(
        email=f"owner-b-{tag}@confitqa.com",
        hashed_password=get_password_hash("StrongPass!2026Aa"),
        full_name="Owner Brand B",
        role=UserRole.BRAND_MANAGER,
        is_active=True,
    )
    admin_u = User(
        email=f"admin-rw-{tag}@confitqa.com",
        hashed_password=get_password_hash("StrongPass!2026Aa"),
        full_name="Platform Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add_all([owner_a, owner_b, admin_u])
    db_session.flush()

    brand_a = BrandProfile(
        user_id=owner_a.id,
        brand_name=f"Maison Alpha {tag}",
        slug=f"maison-alpha-{tag}",
        is_verified=True,
        commission_rate=12.0,
    )
    brand_b = BrandProfile(
        user_id=owner_b.id,
        brand_name=f"Maison Beta {tag}",
        slug=f"maison-beta-{tag}",
        is_verified=True,
        commission_rate=12.0,
    )
    db_session.add_all([brand_a, brand_b])
    db_session.flush()

    db_session.add_all([
        BrandMembership(user_id=owner_a.id, brand_id=brand_a.id, role="owner", status="active"),
        BrandMembership(user_id=owner_b.id, brand_id=brand_b.id, role="owner", status="active"),
    ])

    store_a = StoreLocation(
        brand_id=brand_a.id,
        name="@Maison Alpha Cairo Boutique",
        name_ar="بوتيك ميزون ألفا القاهرة",
        address="Zamalek 12",
        city="Cairo",
        country="Egypt",
        latitude=30.06,
        longitude=31.22,
        is_bopis_enabled=True,
    )
    store_b = StoreLocation(
        brand_id=brand_b.id,
        name="Maison Beta Dubai Boutique",
        name_ar="بوتيك ميزون بيتا دبي",
        address="Fashion Ave 4",
        city="Dubai",
        country="UAE",
        latitude=25.19,
        longitude=55.27,
        is_bopis_enabled=True,
    )
    db_session.add_all([store_a, store_b])
    db_session.flush()

    prod_a = Product(
        brand_id=brand_a.id,
        category_id=cat.id,
        title="=Tailored Merino Coat",  # deliberate leading '=' to verify CSV export neutralization!
        title_ar="معطف ميرينو مُفصّل",
        slug=f"maison-alpha-merino-coat-{tag}",
        description="Structured double-breasted wool coat.",
        description_ar="معطف صوف ميرينو مزدوج الصدر بقصّة مُحكمة.",
        thumbnail_url="https://images.pexels.com/photos/1926769/pexels-photo-1926769.jpeg",
        base_price=Decimal("250.00"),
        currency="USD",
        gender="unisex",
        color_family="+Charcoal",
        is_active=True,
    )
    prod_b = Product(
        brand_id=brand_b.id,
        category_id=cat.id,
        title="Silk Evening Shirt",
        title_ar="قميص حريري للمساء",
        slug=f"maison-beta-silk-shirt-{tag}",
        description="Fluid mulberry silk shirt.",
        description_ar="قميص من حرير التوت الفاخر بانسيابية ناعمة.",
        thumbnail_url="https://images.pexels.com/photos/1926769/pexels-photo-1926769.jpeg",
        base_price=Decimal("180.00"),
        currency="USD",
        gender="unisex",
        color_family="Ivory",
        is_active=True,
    )
    db_session.add_all([prod_a, prod_b])
    db_session.flush()

    sku_a_s = ProductSKU(
        product_id=prod_a.id,
        brand_id=brand_a.id,
        sku_code=f"ALPHA-S-{tag}",
        size="S",
        color="+Charcoal",
        stock_level=10,
        is_in_stock=True,
    )
    sku_a_l = ProductSKU(
        product_id=prod_a.id,
        brand_id=brand_a.id,
        sku_code=f"ALPHA-L-{tag}",
        size="L",
        color="Charcoal",
        stock_level=8,
        is_in_stock=True,
    )
    sku_b_m = ProductSKU(
        product_id=prod_b.id,
        brand_id=brand_b.id,
        sku_code=f"BETA-M-{tag}",
        size="M",
        color="Ivory",
        stock_level=9,
        is_in_stock=True,
    )
    db_session.add_all([sku_a_s, sku_a_l, sku_b_m])
    db_session.flush()

    db_session.add_all([
        StoreInventory(
            store_id=store_a.id,
            brand_id=brand_a.id,
            sku_id=sku_a_l.id,
            quantity=6,
            reserved_quantity=0,
        ),
        StoreInventory(
            store_id=store_b.id,
            brand_id=brand_b.id,
            sku_id=sku_b_m.id,
            quantity=5,
            reserved_quantity=0,
        ),
    ])
    db_session.commit()
    return {
        "tag": tag,
        "cat": cat,
        "owner_a": owner_a,
        "owner_b": owner_b,
        "admin": admin_u,
        "brand_a": brand_a,
        "brand_b": brand_b,
        "store_a": store_a,
        "store_b": store_b,
        "prod_a": prod_a,
        "prod_b": prod_b,
        "sku_a_s": sku_a_s,
        "sku_a_l": sku_a_l,
        "sku_b_m": sku_b_m,
    }


def _login_headers(client, email: str, password: str = "StrongPass!2026Aa") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_wishlist_auth_sync_dedup_isolation_and_gdpr_lifecycle(client, db_session):
    """Workstream 4 & 8: Authenticated wishlist CRUD, guest merge dedup, cross-user isolation & GDPR cleanup."""
    seed = _seed_two_brands_and_catalog(db_session)
    p_a, p_b = seed["prod_a"].id, seed["prod_b"].id

    # Unauthenticated access is rejected with 401
    assert client.get("/api/v1/me/wishlist").status_code == 401

    headers_a, user_a_id = _register_and_auth(client, "shopper-wish-a")
    headers_b, _ = _register_and_auth(client, "shopper-wish-b")

    # Guest-to-account sync merges deduplicated valid IDs and drops nonexistent IDs
    sync_resp = client.post(
        "/api/v1/me/wishlist/sync",
        headers=headers_a,
        json={"product_ids": [p_a, p_b, p_a, 9999999]},
    )
    assert sync_resp.status_code == 200, sync_resp.text
    assert set(sync_resp.json()["product_ids"]) == {p_a, p_b}
    assert len(sync_resp.json()["product_ids"]) == 2

    # Onboarding status must remain completely untouched ('not_completed')
    me_profile = client.get("/api/v1/profile/me", headers=headers_a)
    assert me_profile.status_code == 200
    assert me_profile.json().get("onboarding_completed") is False

    # Shopper B has zero leakage and cannot delete Shopper A's saved items
    assert client.get("/api/v1/me/wishlist", headers=headers_b).json()["product_ids"] == []
    del_attempt = client.delete(f"/api/v1/me/wishlist/{p_a}", headers=headers_b)
    assert del_attempt.status_code == 200
    assert set(client.get("/api/v1/me/wishlist", headers=headers_a).json()["product_ids"]) == {p_a, p_b}

    # GDPR export includes wishlist_product_ids & account deletion leaves zero orphan rows
    export_resp = client.post("/api/v1/me/export", headers=headers_a)
    assert export_resp.status_code == 200, export_resp.text
    assert set(export_resp.json()["data"]["wishlist_product_ids"]) == {p_a, p_b}

    user_a = db_session.get(User, user_a_id)
    AuthService(db_session).delete_account(user_a)
    assert db_session.query(UserWishlistItem).filter_by(user_id=user_a_id).count() == 0
    assert db_session.query(BrandAnalyticsEvent).filter_by(user_id=user_a_id).count() == 0


def test_media_telemetry_photo_index_date_filter_and_cross_brand_isolation(client, db_session):
    """Workstream 2 & 7: Storefront gallery_photo_view + fit_recommendation -> PostgreSQL -> BrandAnalytics honesty."""
    seed = _seed_two_brands_and_catalog(db_session)
    prod_a = seed["prod_a"]
    tag = seed["tag"]

    r0 = client.post(
        "/api/v1/catalog/events",
        json={
            "event_id": f"evt-pdp-photo-0-{tag}",
            "product_id": prod_a.id,
            "sku_id": seed["sku_a_l"].id,
            "event_type": "gallery_photo_view",
            "photo_index": 0,
        },
    )
    assert r0.status_code == 200 and r0.json()["status"] == "recorded"

    r0_dup = client.post(
        "/api/v1/catalog/events",
        json={
            "event_id": f"evt-pdp-photo-0-{tag}",
            "product_id": prod_a.id,
            "event_type": "gallery_photo_view",
            "photo_index": 0,
        },
    )
    assert r0_dup.status_code == 200 and r0_dup.json()["status"] == "duplicate"

    r2 = client.post(
        "/api/v1/catalog/events",
        json={
            "event_id": f"evt-pdp-photo-2-{tag}",
            "product_id": prod_a.id,
            "event_type": "gallery_photo_view",
            "photo_index": 2,
        },
    )
    assert r2.status_code == 200

    r_fit = client.post(
        "/api/v1/catalog/events",
        json={
            "event_id": f"evt-fit-rec-1-{tag}",
            "product_id": prod_a.id,
            "event_type": "fit_recommendation",
            "recommended_size": "L",
            "confidence_band": "high",
        },
    )
    assert r_fit.status_code == 200

    # Cross-product SKU injection is rejected with 422
    bad_sku = client.post(
        "/api/v1/catalog/events",
        json={
            "event_id": f"evt-forged-sku-{tag}",
            "product_id": prod_a.id,
            "sku_id": seed["sku_b_m"].id,
            "event_type": "gallery_photo_view",
            "photo_index": 1,
        },
    )
    assert bad_sku.status_code == 422

    # Brand A analytics reflects exact counts; Brand B has exact 0s (zero cross-brand leakage)
    bi_svc = BusinessIntelligenceService(db_session)
    dash_a = bi_svc.get_brand_bi_dashboard(brand_id=seed["brand_a"].id, days=30)
    dash_b = bi_svc.get_brand_bi_dashboard(brand_id=seed["brand_b"].id, days=30)

    assert dash_a["media_engagement"]["gallery_photo_views"] == 2
    assert dash_a["media_engagement"]["fit_recommendations"] == 1
    assert dash_a["media_engagement"]["photo_index_breakdown"] == {"0": 1, "2": 1}

    assert dash_b["media_engagement"]["gallery_photo_views"] == 0
    assert dash_b["media_engagement"]["fit_recommendations"] == 0
    assert dash_b["media_engagement"]["photo_index_breakdown"] == {}

    # Historical date window filter excludes today's events cleanly
    past_dash = bi_svc.get_brand_bi_dashboard(
        brand_id=seed["brand_a"].id,
        date_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        date_to=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    assert past_dash["media_engagement"]["gallery_photo_views"] == 0

    repo_analytics_a = BrandRepository(db_session).get_brand_analytics(seed["brand_a"].id)
    assert repo_analytics_a["media_engagement"]["gallery_photo_views"] == 2


def test_csv_formula_injection_neutralization_and_utf8_bom_across_all_exports(client, db_session):
    """Workstream 7: Formula injection (=, +, -, @, tab) & UTF-8 BOM verified across all CSV exports."""
    seed = _seed_two_brands_and_catalog(db_session)
    headers_a = _login_headers(client, seed["owner_a"].email)
    headers_admin = _login_headers(client, seed["admin"].email)

    err_csv = BrandCatalogService.generate_error_report_csv([
        {
            "row": 2,
            "field": "title",
            "value": "=CMD|' /C calc'!A0",
            "message": "Invalid title",
        },
        {
            "row": 3,
            "field": "sku_code",
            "value": "@SUM(1+1)",
            "message": "Invalid SKU",
        },
    ])
    assert err_csv.startswith("\ufeff")
    assert "'=CMD|' /C calc'!A0" in err_csv
    assert "'@SUM(1+1)" in err_csv

    cat_export = client.get("/api/v1/partner/catalog/export.csv", headers=headers_a)
    assert cat_export.status_code == 200, cat_export.text
    raw_text = cat_export.content.decode("utf-8")
    assert raw_text.startswith("\ufeff")
    assert "'=Tailored Merino Coat" in raw_text
    assert "'+Charcoal" in raw_text
    assert "معطف ميرينو مُفصّل" in raw_text
    assert "Silk Evening Shirt" not in raw_text

    bi_csv = client.get("/api/v1/partner/analytics/export.csv?days=30", headers=headers_a)
    assert bi_csv.status_code == 200
    bi_text = bi_csv.content.decode("utf-8")
    assert bi_text.startswith("\ufeff")
    assert "'@Maison Alpha Cairo Boutique" in bi_text

    admin_csv = client.get("/api/v1/admin/analytics/export.csv?days=30", headers=headers_admin)
    assert admin_csv.status_code == 200
    assert admin_csv.content.decode("utf-8").startswith("\ufeff")


def test_adversarial_image_validation_and_ssrf_defenses(db_session, monkeypatch):
    """Workstream 6: Rejects polyglot HTML-as-JPEG, SVG script payloads, truncated files & SSRF hosts."""
    from backend.app.services import media_materialization_service as mms

    seed = _seed_two_brands_and_catalog(db_session)
    svc = mms.MediaMaterializationService(db_session)

    # 1. Valid 1600x1600 RGB JPEG materializes all 10 ladder renditions cleanly
    buf = io.BytesIO()
    Image.new("RGB", (1600, 1600), color=(40, 45, 50)).save(buf, format="JPEG")
    valid_bytes = buf.getvalue()
    monkeypatch.setattr(mms.MediaMaterializationService, "_get_fetch", lambda self: (lambda _u: valid_bytes))
    rows = svc.materialize(
        seed["prod_a"],
        "https://images.pexels.com/photos/1926769/pexels-photo-1926769.jpeg",
        photo_index=0,
    )
    assert len(rows) == 10

    # 2. Polyglot HTML renamed to .jpeg is rejected cleanly
    monkeypatch.setattr(
        mms.MediaMaterializationService,
        "_get_fetch",
        lambda self: (lambda _u: b"<html><body><script>alert(1)</script></body></html>"),
    )
    with pytest.raises(Exception):
        svc.materialize(
            seed["prod_a"],
            "https://images.pexels.com/photos/9999991/polyglot.jpeg",
            photo_index=1,
        )

    # 3. Embedded script SVG disguised as image bytes is rejected cleanly
    monkeypatch.setattr(
        mms.MediaMaterializationService,
        "_get_fetch",
        lambda self: (lambda _u: b'<svg xmlns="http://www.w3.org/2000/svg"><script>evil()</script></svg>'),
    )
    with pytest.raises(Exception):
        svc.materialize(
            seed["prod_a"],
            "https://images.pexels.com/photos/9999992/script.jpeg",
            photo_index=1,
        )

    # 4. Corrupt / truncated JPEG header is rejected cleanly
    monkeypatch.setattr(
        mms.MediaMaterializationService,
        "_get_fetch",
        lambda self: (lambda _u: b"\xff\xd8\xff\xe0\x00\x10JFIF\x00corrupt-truncated"),
    )
    with pytest.raises(Exception):
        svc.materialize(
            seed["prod_a"],
            "https://images.pexels.com/photos/9999993/corrupt.jpeg",
            photo_index=1,
        )

    # 5. Cloud metadata & localhost SSRF URLs rejected immediately
    for ssrf_url in (
        "http://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1/internal.jpg",
        "https://evil-unverified-host.example/coat.jpg",
    ):
        with pytest.raises(Exception):
            svc.materialize(seed["prod_a"], ssrf_url, photo_index=1)


def test_positive_first_bola_bfla_isolation_matrix_and_commerce_journey(client, db_session, monkeypatch):
    """Workstreams 2, 5, 8 & 9: Positive-control-first BOLA/BFLA matrix + Fit->Cart->Checkout->Fawaterak HMAC & Lease Recovery."""
    from backend.app.core.config import settings

    seed = _seed_two_brands_and_catalog(db_session)
    tag = seed["tag"]
    headers_brand_a = _login_headers(client, seed["owner_a"].email)
    headers_brand_b = _login_headers(client, seed["owner_b"].email)
    headers_shopper_a = {**_register_and_auth(client, "journey-shopper-a")[0], "X-Session-Token": f"sess-a-{tag}"}
    headers_shopper_b = {**_register_and_auth(client, "journey-shopper-b")[0], "X-Session-Token": f"sess-b-{tag}"}

    # --- A. Brand A vs Brand B BOLA/BFLA (Positive control 200 FIRST, identical payload negative control SECOND) ---
    patch_payload = {"description": "Updated luxury double-faced merino wool description."}
    pos_patch = client.patch(
        f"/api/v1/partner/catalog/products/{seed['prod_a'].id}",
        headers=headers_brand_a,
        json=patch_payload,
    )
    assert pos_patch.status_code == 200, pos_patch.text

    neg_patch = client.patch(
        f"/api/v1/partner/catalog/products/{seed['prod_a'].id}",
        headers=headers_brand_b,
        json=patch_payload,
    )
    assert neg_patch.status_code in (403, 404), f"Expected 403/404, got {neg_patch.status_code}"

    assert client.get("/api/v1/partner/catalog/export.csv", headers=headers_shopper_a).status_code == 403

    # --- B. Double-Submit Cookie CSRF Enforcement + Clean Guest Session Isolation ('X-Session-Token') ---
    # 1. Cookie present from prior auth login without X-CSRF-Token MUST be blocked with 403 CSRF_TOKEN_MISMATCH
    csrf_blocked = client.post(
        "/api/v1/cart/items",
        headers={"X-Session-Token": f"guest-tok-a-{tag}"},
        json={"product_sku_id": seed["sku_a_l"].id, "quantity": 1},
    )
    assert csrf_blocked.status_code == 403 and csrf_blocked.json()["error"]["code"] == "CSRF_TOKEN_MISMATCH"

    # 2. Clear cookies so true unauthenticated guest sessions ('X-Session-Token') are isolated cleanly
    client.cookies.clear()
    guest_a = {"X-Session-Token": f"guest-tok-a-{tag}"}
    guest_b = {"X-Session-Token": f"guest-tok-b-{tag}"}
    add_guest = client.post(
        "/api/v1/cart/items",
        headers=guest_a,
        json={"product_sku_id": seed["sku_a_l"].id, "quantity": 1},
    )
    assert add_guest.status_code in (200, 201), add_guest.text
    assert len(client.get("/api/v1/cart", headers=guest_a).json()["items"]) == 1
    assert len(client.get("/api/v1/cart", headers=guest_b).json()["items"]) == 0

    # --- C. Fit Finder -> Cart -> Idempotent Checkout -> Shopper A vs B Order Isolation & Multi-Brand Accounting ---
    fit_resp = client.post(
        "/api/v1/tryon/no-photo-fit",
        json={
            "product_id": seed["prod_a"].id,
            "height_cm": 182,
            "weight_kg": 79,
            "body_shape": "Athletic",
            "chest_cm": 102,
            "waist_cm": 85,
            "preferred_fit": "regular",
        },
    )
    assert fit_resp.status_code == 200, fit_resp.text

    r_add_a = client.post(
        "/api/v1/commerce/cart/items",
        headers=headers_shopper_a,
        json={"product_sku_id": seed["sku_a_l"].id, "quantity": 1},
    )
    assert r_add_a.status_code in (200, 201), r_add_a.text
    r_add_b = client.post(
        "/api/v1/commerce/cart/items",
        headers=headers_shopper_a,
        json={"product_sku_id": seed["sku_b_m"].id, "quantity": 2},
    )
    assert r_add_b.status_code in (200, 201), r_add_b.text

    checkout_payload = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Nour El-Din",
        "phone": "+201000000001",
        "address_line": "14 Gezira St",
        "city": "Cairo",
        "country": "Egypt",
        "idempotency_key": f"idem-rw-{tag}",
        "try_on_assisted": True,
    }
    idem_headers = {**headers_shopper_a, "X-Idempotency-Key": f"idem-rw-{tag}"}
    order_r1 = client.post("/api/v1/commerce/checkout", headers=idem_headers, json=checkout_payload)
    assert order_r1.status_code in (200, 201), order_r1.text
    order_no = order_r1.json()["order_number"]

    order_r2 = client.post("/api/v1/commerce/checkout", headers=idem_headers, json=checkout_payload)
    assert order_r2.status_code in (200, 201)
    assert order_r2.json()["order_number"] == order_no

    assert client.get(f"/api/v1/commerce/orders/{order_no}", headers=headers_shopper_a).status_code == 200
    assert client.get(f"/api/v1/commerce/orders/{order_no}", headers=headers_shopper_b).status_code in (403, 404)

    bi_svc = BusinessIntelligenceService(db_session)
    assert round(bi_svc.get_brand_bi_dashboard(seed["brand_a"].id, days=30)["kpis"]["gross_sales"], 2) == 250.00
    assert round(bi_svc.get_brand_bi_dashboard(seed["brand_b"].id, days=30)["kpis"]["gross_sales"], 2) == 360.00

    # --- D. Fawaterak Webhook Forged HMAC Rejection (401/400) ---
    monkeypatch.setattr(settings, "FAWATERAK_VENDOR_API_KEY", "unit-test-hmac-key-not-real", raising=False)
    forged_wh = client.post(
        "/api/v1/payments/webhooks/fawaterak/paid_json",
        json={
            "transaction_id": 999111,
            "transaction_key": "TXK-999",
            "payment_method": "Card",
            "status": "paid",
            "transactionHashKey": "0" * 64,
        },
    )
    assert forged_wh.status_code in (400, 401, 403)

    # --- E. Stalled Import Worker Lease Recovery with Full 10-Rendition Media Ladder (Workstream 6 & 9) ---
    csv_payload = (
        "title,title_ar,description,description_ar,category_slug,color_family,base_price,currency,sku_code,size,color,stock_level,thumbnail_url\n"
        f"Recovered Linen Blazer,بليزر كتان صيفي,Tailored summer blazer,بليزر صيفي مُفصّل,{seed['cat'].slug},Beige,195.00,USD,REC-{tag},M,Sand,7,"
        "https://images.pexels.com/photos/1926769/pexels-photo-1926769.jpeg\n"
    )
    stalled_job = CatalogImportJob(
        brand_id=seed["brand_a"].id,
        file_name="stalled.csv",
        total_rows=1,
        processed_rows=0,
        accepted_rows=0,
        rejected_rows=0,
        duplicate_rows=0,
        status="processing",
        payload_text=csv_payload,
        heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        attempts=1,
    )
    db_session.add(stalled_job)
    db_session.commit()
    stalled_id = stalled_job.id

    BrandCatalogService(db_session).execute_import_job(stalled_id)
    db_session.expire_all()
    finished = db_session.get(CatalogImportJob, stalled_id)
    assert finished.status == "completed", finished.errors_json
    assert finished.accepted_rows == 1


def test_wardrobe_auto_mode_never_orphans_into_workerless_redis(client, monkeypatch):
    """DEF-23 (P0): When Upstash/local Redis responds to PING (rate-limiting/state)
    with zero live Celery workers consuming the queue, WARDROBE_ANALYSIS_MODE='auto'
    must analyze inline to a terminal state instead of leaving items stuck in 'processing'."""
    import io
    from PIL import Image
    from backend.app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "WARDROBE_ANALYSIS_MODE", "auto", raising=False)
    monkeypatch.setattr(config_mod.settings, "GEMINI_API_KEY", None, raising=False)

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(36, 37, 38)).save(buf, format="PNG")
    headers, _ = _register_and_auth(client, "shopper-wardrobe-def23")

    res = client.post(
        "/api/v1/wardrobe/upload",
        headers=headers,
        files={"file": ("blazer.png", buf.getvalue(), "image/png")},
    )
    assert res.status_code == 201, res.text
    item = res.json()["results"][0]["item"]
    assert item["processing_status"] == "failed"

