from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert False, "DELIBERATE CI GATE PROOF — this test must fail"
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_auth_login_and_me(client: TestClient):
    # Test Login
    login_res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    token = data["access_token"]

    # Test /me
    headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "shopper@confit.io"


def test_user_style_profile(client: TestClient):
    login_res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile_res = client.get("/api/v1/profile/me", headers=headers)
    assert profile_res.status_code == 200
    data = profile_res.json()
    assert "style_archetypes" in data
    assert "body_attributes" in data
    assert data["body_attributes"]["is_encrypted"] is True


def test_catalog_and_bopis(client: TestClient):
    # List products
    res = client.get("/api/v1/catalog/products")
    assert res.status_code == 200
    products = res.json()
    assert len(products) > 0
    first_product = products[0]

    # Get product detail
    detail_res = client.get(f"/api/v1/catalog/products/{first_product['id']}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert len(detail["skus"]) > 0

    # Check BOPIS store availability
    first_sku_id = detail["skus"][0]["id"]
    stores_res = client.get(f"/api/v1/catalog/skus/{first_sku_id}/stores")
    assert stores_res.status_code == 200
    assert len(stores_res.json()) > 0


def test_stylist_chat_and_compatibility(client: TestClient):
    login_res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    chat_res = client.post("/api/v1/stylist/chat", headers=headers, json={
        "prompt": "I need a quiet luxury outfit for a business dinner under $400",
        "occasion": "Work & Business",
        "budget_limit": 400.0
    })
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert len(chat_data["recommendations"]) > 0
    assert "intent_detected" in chat_data

    # Test outfit compatibility check. The login above set the httpOnly
    # session cookie in this client's jar, so under the CSRF double-submit
    # contract a cookie-authenticated POST must echo the readable CSRF cookie
    # as a header — exactly what the frontend does.
    csrf = client.cookies.get("confit_csrf")
    comp_res = client.post("/api/v1/stylist/compatibility", headers={"X-CSRF-Token": csrf}, json={
        "product_ids": [1, 2],
        "target_occasion": "Work & Business"
    })
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert comp_data["compatibility_score"] >= 80
    assert "color_harmony_type" in comp_data


def test_virtual_tryon_and_no_photo_fit(client: TestClient):
    # Test Virtual Try-On — without a configured GPU worker the render
    # endpoint must fail truthfully (503), never fabricating a result.
    tryon_res = client.post("/api/v1/tryon/render", json={
        "product_id": 1,
        "avatar_model_id": "avatar_athletic_m",
        "consent_retain_photo": False
    })
    assert tryon_res.status_code == 503
    assert tryon_res.json()["error"]["code"] == "VTON_ENGINE_UNAVAILABLE"

    # Test No-Photo Fit Finder
    ruler_res = client.post("/api/v1/tryon/no-photo-fit", json={
        "product_id": 1,
        "height_cm": 178.0,
        "weight_kg": 72.0,
        "body_shape": "Athletic",
        "chest_cm": 98.0,
        "waist_cm": 82.0,
        "preferred_fit": "regular"
    })
    assert ruler_res.status_code == 200
    ruler_data = ruler_res.json()
    assert ruler_data["recommended_size"] in ["M", "L"]
    assert "fit_breakdown" in ruler_data


def test_wardrobe_and_duplicate_alert(client: TestClient):
    login_res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get Wardrobe
    w_res = client.get("/api/v1/wardrobe/items", headers=headers)
    assert w_res.status_code == 200
    items = w_res.json()
    assert len(items) > 0

    # Check Duplicate Alert at Cart
    dup_res = client.post("/api/v1/wardrobe/duplicate-check", headers=headers, json={
        "product_id": 1,
        "product_title": "Tailored Italian Wool Double-Breasted Blazer",
        "category": "Outerwear",
        "color_family": "Navy Blue",
        "strict_mode": True
    })
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["has_duplicate_risk"] is True
    assert dup_data["similarity_score"] >= 80


def test_commerce_cart_checkout_and_tracking(client: TestClient):
    login_res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Session-Token": "test_session_123"}

    # Add item to cart
    add_res = client.post("/api/v1/commerce/cart/items", headers=headers, json={
        "product_sku_id": 1,
        "quantity": 1
    })
    assert add_res.status_code in [200, 201]
    cart_data = add_res.json()
    assert cart_data["items_count"] >= 1

    # Checkout
    checkout_res = client.post("/api/v1/commerce/checkout", headers=headers, json={
        "payment_method": "bnpl_tabby",
        "fulfillment_type": "bopis",
        "bopis_store_id": 1,
        "recipient_name": "Layla Al-Mansoor",
        "phone": "+971501234567",
        "city": "Dubai",
        "country": "UAE",
        "promo_code": "CONFIT10",
        "try_on_assisted": True
    })
    assert checkout_res.status_code == 200
    order_data = checkout_res.json()
    assert order_data["order_number"].startswith("CONF-")
    assert order_data["payment_method"] == "bnpl_tabby"

    # Order tracking
    track_res = client.get(f"/api/v1/commerce/orders/{order_data['order_number']}/tracking")
    assert track_res.status_code == 200
    track_data = track_res.json()
    assert len(track_data["timeline"]) > 0


def test_brand_b2b_dashboard(client: TestClient):
    login_res = client.post("/api/v1/auth/login", json={
        "email": "brand@massimodutti.com",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Brand analytics
    analytics_res = client.get("/api/v1/brand/analytics", headers=headers)
    assert analytics_res.status_code == 200
    analytics = analytics_res.json()
    assert analytics["return_reduction_percentage"] > 0
    assert len(analytics["outfit_appearance_rankings"]) > 0

    # Update SKU Stock
    sku_res = client.put("/api/v1/brand/skus/1?stock_level=25", headers=headers)
    assert sku_res.status_code == 200
    assert sku_res.json()["stock_level"] == 25

def test_measurement_session_and_results(client: TestClient):
    # 1. Create measurement session
    sess_res = client.post("/api/v1/measurements/sessions", json={
        "capture_mode": "client_side",
        "consent_granted": True,
        "save_to_profile": False
    })
    assert sess_res.status_code == 201
    sess_data = sess_res.json()
    assert "id" in sess_data
    session_id = sess_data["id"]

    # 2. Submit measurement results
    result_res = client.post(f"/api/v1/measurements/sessions/{session_id}/results", json={
        "height_cm": 178.0,
        "shoulder_width_cm": 46.0,
        "chest_cm": 99.0,
        "waist_cm": 82.0,
        "hip_cm": 96.0,
        "confidence_score": 95,
        "calibration_method": "on_device_height_calibrated",
        "source": "camera_estimate"
    })
    assert result_res.status_code == 201
    res_data = result_res.json()
    assert res_data["status"] == "success"
    assert res_data["derived_measurements"]["height_cm"] == 178.0

    # 3. Query measurement session
    get_res = client.get(f"/api/v1/measurements/sessions/{session_id}")
    assert get_res.status_code == 200
    assert len(get_res.json()["results"]) > 0


def test_catalog_ignores_literal_undefined_params(client: TestClient):
    """Regression for the 2026-08-29 empty-catalog outage: JS clients that
    serialize undefined query params send the literal string 'undefined'.
    The API must treat those as absent, not as real filters."""
    res = client.get("/api/v1/catalog/products?category=undefined&occasion=undefined&color=undefined&search=undefined&sort_by=recommended")
    assert res.status_code == 200
    assert len(res.json()) > 0  # the catalog is NOT empty

    res2 = client.get("/api/v1/catalog/products")
    assert res2.status_code == 200
    assert len(res.json()) == len(res2.json())  # same result as no params
