"""Explicit admin catalog surface and shared-database propagation.

The regression this closes was architectural: an ADMIN opened /b2b/catalog,
but every request was partner-scoped and required a linked BrandProfile. These
tests prove the replacement is an explicit admin route, keeps partner RBAC,
performs real audited CRUD, and changes the same Product rows consumed by the
public catalog.
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.models.user import AuditLog
from backend.tests.conftest import TestingSessionLocal


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(client: TestClient, email: str) -> dict:
    return {"Authorization": f"Bearer {_login(client, email)}"}


def test_catalog_brand_selector_is_admin_only_and_uses_real_counts(client: TestClient):
    denied = client.get(
        "/api/v1/admin/catalog/brands",
        headers=_headers(client, "shopper@confit.io"),
    )
    assert denied.status_code == 403

    response = client.get(
        "/api/v1/admin/catalog/brands",
        headers=_headers(client, "admin@confit.io"),
    )
    assert response.status_code == 200, response.text
    brands = response.json()
    assert brands
    assert all({
        "id", "brand_name", "product_count", "active_product_count",
        "sku_count", "store_count", "placement_count",
    } <= set(row) for row in brands)
    assert any(row["product_count"] > 0 for row in brands)


def test_admin_product_crud_propagates_to_public_catalog_and_is_audited(client: TestClient):
    headers = _headers(client, "admin@confit.io")
    brands_response = client.get("/api/v1/admin/catalog/brands", headers=headers)
    assert brands_response.status_code == 200
    brand = max(brands_response.json(), key=lambda row: row["product_count"])

    snapshot_response = client.get(
        f"/api/v1/admin/catalog/brands/{brand['id']}", headers=headers
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot = snapshot_response.json()
    assert snapshot["brand"]["id"] == brand["id"]
    assert snapshot["categories"]
    category_id = snapshot["categories"][0]["id"]

    marker = uuid4().hex[:10].upper()
    title = f"Admin Contract Product {marker}"
    edited_title = f"Admin Contract Edited {marker}"
    sku_code = f"ADM-{marker}"
    payload = {
        "category_id": category_id,
        "title": title,
        "title_ar": f"منتج إداري {marker}",
        "description": "Persisted integration-test product for the explicit admin workflow.",
        "description_ar": "منتج اختبار محفوظ لمسار إدارة الكتالوج الصريح.",
        "base_price": "1499.00",
        "currency": "EGP",
        "material": "Organic cotton",
        "care_instructions": "Cold wash; reshape while damp.",
        "color_family": "Midnight Navy",
        "dominant_hex": "#1B1F3B",
        "thumbnail_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab",
        "images": [],
        "style_tags": ["minimal", "smart-casual"],
        "occasion_tags": ["work", "weekend"],
        "is_featured": False,
        "skus": [{
            "sku_code": sku_code,
            "size": "M",
            "color": "Midnight Navy",
            "color_hex": "#1B1F3B",
            "stock_level": 17,
        }],
    }

    created = client.post(
        f"/api/v1/admin/catalog/brands/{brand['id']}/products",
        json=payload,
        headers=headers,
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["product_id"]

    public = client.get("/api/v1/catalog/products")
    assert public.status_code == 200
    assert any(row["id"] == product_id and row["title"] == title for row in public.json())

    refreshed = client.get(
        f"/api/v1/admin/catalog/brands/{brand['id']}", headers=headers
    ).json()
    product = next(row for row in refreshed["products"] if row["id"] == product_id)
    sku_id = product["skus"][0]["id"]
    assert product["skus"][0]["stock_level"] == 17

    sku_update = client.patch(
        f"/api/v1/admin/catalog/brands/{brand['id']}/skus/{sku_id}",
        json={"stock_level": 23, "price_override": "1399.00"},
        headers=headers,
    )
    assert sku_update.status_code == 200, sku_update.text
    assert sku_update.json()["stock_level"] == 23

    updated = client.patch(
        f"/api/v1/admin/catalog/brands/{brand['id']}/products/{product_id}",
        json={"title": edited_title, "base_price": "1599.00"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    public_after_edit = client.get("/api/v1/catalog/products").json()
    assert any(row["id"] == product_id and row["title"] == edited_title for row in public_after_edit)

    deactivated = client.delete(
        f"/api/v1/admin/catalog/brands/{brand['id']}/products/{product_id}",
        headers=headers,
    )
    assert deactivated.status_code == 200, deactivated.text
    assert all(row["id"] != product_id for row in client.get("/api/v1/catalog/products").json())

    reactivated = client.post(
        f"/api/v1/admin/catalog/brands/{brand['id']}/products/{product_id}/activate",
        headers=headers,
    )
    assert reactivated.status_code == 200, reactivated.text
    assert any(row["id"] == product_id for row in client.get("/api/v1/catalog/products").json())

    db = TestingSessionLocal()
    try:
        actions = {
            action for (action,) in db.query(AuditLog.action).filter(
                AuditLog.resource_type.in_(("Product", "ProductSKU")),
                AuditLog.resource_id.in_((str(product_id), str(sku_id))),
            ).all()
        }
    finally:
        db.close()
    assert {
        "ADMIN_CATALOG_PRODUCT_CREATED",
        "ADMIN_CATALOG_PRODUCT_UPDATED",
        "ADMIN_CATALOG_SKU_UPDATED",
        "ADMIN_CATALOG_PRODUCT_DEACTIVATED",
        "ADMIN_CATALOG_PRODUCT_REACTIVATED",
    } <= actions


def test_admin_cannot_mutate_a_product_through_the_wrong_brand_scope(client: TestClient):
    headers = _headers(client, "admin@confit.io")
    brands = client.get("/api/v1/admin/catalog/brands", headers=headers).json()
    populated = next(row for row in brands if row["product_count"] > 0)
    other = next(row for row in brands if row["id"] != populated["id"])
    product_id = client.get(
        f"/api/v1/admin/catalog/brands/{populated['id']}", headers=headers
    ).json()["products"][0]["id"]

    response = client.patch(
        f"/api/v1/admin/catalog/brands/{other['id']}/products/{product_id}",
        json={"title": "Cross-scope mutation must fail"},
        headers=headers,
    )
    assert response.status_code == 404
