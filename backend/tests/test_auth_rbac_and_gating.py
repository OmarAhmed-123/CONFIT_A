import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.database import SessionLocal
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.models.catalog import Product, ProductSKU
from backend.app.seed_data import seed_database

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed_database()


def get_error_message(res) -> str:
    data = res.json()
    if isinstance(data, dict):
        if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
            return data["error"]["message"]
        if "message" in data:
            return data["message"]
        if "detail" in data:
            return str(data["detail"])
    return ""


def test_guest_can_browse_and_add_to_cart():
    # 1. Guest can browse catalog
    cat_res = client.get("/api/v1/catalog/products")
    assert cat_res.status_code == 200
    products = cat_res.json()
    assert len(products) > 0

    # 2. Guest can add item to cart using anonymous session header
    guest_headers = {"X-Session-Token": "guest_session_anon_99"}
    cart_res = client.post("/api/v1/commerce/cart/items", headers=guest_headers, json={
        "product_sku_id": 1,
        "quantity": 1
    })
    assert cart_res.status_code in [200, 201]
    cart_data = cart_res.json()
    assert cart_data["items_count"] >= 1

    # 3. Guest can read cart
    get_cart_res = client.get("/api/v1/commerce/cart", headers=guest_headers)
    assert get_cart_res.status_code == 200
    assert get_cart_res.json()["items_count"] >= 1


def test_checkout_strictly_gates_unauthenticated_guests():
    # Attempting final checkout without Bearer token must be rejected with 401
    guest_headers = {"X-Session-Token": "guest_session_anon_99"}
    checkout_payload = {
        "payment_method": "card",
        "fulfillment_type": "delivery",
        "recipient_name": "Anonymous Guest",
        "phone": "+971500000000",
        "address_line": "Downtown Boulevard",
        "city": "Dubai",
        "country": "UAE"
    }

    unauth_res = client.post("/api/v1/commerce/checkout", headers=guest_headers, json=checkout_payload)
    assert unauth_res.status_code == 401
    msg = get_error_message(unauth_res)
    assert "bearer token required" in msg.lower()


def test_authenticated_customer_can_checkout():
    # 1. Login as customer
    login_res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {
        "Authorization": f"Bearer {token}",
        "X-Session-Token": "shopper_sess_01"
    }

    # 2. Add to cart
    client.post("/api/v1/commerce/cart/items", headers=auth_headers, json={
        "product_sku_id": 1,
        "quantity": 1
    })

    # 3. Checkout succeeds
    checkout_res = client.post("/api/v1/commerce/checkout", headers=auth_headers, json={
        "payment_method": "bnpl_tabby",
        "fulfillment_type": "delivery",
        "recipient_name": "Layla Al-Mansoor",
        "phone": "+971501234567",
        "address_line": "Villa 14, Al Wasl Road",
        "city": "Dubai",
        "country": "UAE",
        "promo_code": "CONFIT10"
    })
    assert checkout_res.status_code == 200
    order = checkout_res.json()
    assert order["order_number"].startswith("CONF-")
    assert order["payment_method"] == "bnpl_tabby"


def test_customer_cannot_access_brand_or_admin_endpoints():
    # Login as customer
    login_res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Customer accessing Brand Analytics -> 403 Forbidden
    brand_res = client.get("/api/v1/brand/analytics", headers=headers)
    assert brand_res.status_code == 403

    # Customer accessing Admin Analytics -> 403 Forbidden
    admin_res = client.get("/api/v1/admin/analytics", headers=headers)
    assert admin_res.status_code == 403


def test_brand_tenant_isolation_cross_brand_mutation_rejected():
    # 1. Login as Massimo Dutti Brand Manager
    login_md = client.post("/api/v1/auth/login", json={
        "email": "brand@massimodutti.com",
        "password": "Password123!"
    })
    assert login_md.status_code == 200
    token_md = login_md.json()["access_token"]
    headers_md = {"Authorization": f"Bearer {token_md}"}

    # 2. Massimo Dutti manager can update their own SKU (Product ID #1 -> SKU #1)
    sku_res = client.put("/api/v1/brand/skus/1?stock_level=30", headers=headers_md)
    assert sku_res.status_code == 200
    assert sku_res.json()["stock_level"] == 30

    # 3. Find an SKU belonging to a DIFFERENT brand (e.g. Reiss, SKU #5)
    db = SessionLocal()
    other_sku = (
        db.query(ProductSKU)
        .join(Product)
        .join(BrandProfile)
        .filter(BrandProfile.brand_name == "Reiss")
        .first()
    )
    db.close()

    assert other_sku is not None
    # 4. Massimo Dutti manager attempting to mutate Reiss's SKU must be rejected with 403
    cross_res = client.put(f"/api/v1/brand/skus/{other_sku.id}?stock_level=99", headers=headers_md)
    assert cross_res.status_code == 403
    msg = get_error_message(cross_res)
    assert "tenant scope violation" in msg.lower()


def test_platform_admin_has_global_oversight():
    # Login as Super Admin
    login_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@confit.io",
        "password": "Password123!"
    })
    assert login_admin.status_code == 200
    token_admin = login_admin.json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    # Admin accessing Platform Admin Analytics -> 200 OK
    admin_res = client.get("/api/v1/admin/analytics", headers=headers_admin)
    assert admin_res.status_code == 200
    data = admin_res.json()
    assert data["total_brands_count"] >= 4
    assert data["tryon_adoption_rate"] > 0

    # Admin accessing Brand Portal routes -> 200 OK
    brand_res = client.get("/api/v1/brand/analytics", headers=headers_admin)
    assert brand_res.status_code == 200
