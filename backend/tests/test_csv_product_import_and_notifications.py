"""Tests for CSV product import, boutique branch inventory, and automated email notifications."""
import io
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.models.catalog import Product, ProductSKU, Category, StoreLocation, StoreInventory
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.models.email_preference import EmailPreference
from backend.app.models.email_outbox import EmailOutbox
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.core.security import create_access_token


@pytest.fixture()
def test_env():
    old_override = app.dependency_overrides.get(get_db)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Create Categories
    c_shirts = Category(name="Shirts", name_ar="قمصان", slug="shirts")
    c_outerwear = Category(name="Outerwear", name_ar="ملابس خارجية", slug="outerwear")
    c_accessories = Category(name="Accessories", name_ar="إكسسوارات", slug="accessories")
    db.add_all([c_shirts, c_outerwear, c_accessories])

    # Create Brand Owner & Profile
    owner = User(
        email="owner@brand.example.com",
        hashed_password="hashed_password_123",
        full_name="Boutique Director",
        role=UserRole.BRAND_OWNER,
        preferred_language="en",
        is_active=True,
        is_verified=True,
    )
    db.add(owner)
    db.flush()

    brand = BrandProfile(
        user_id=owner.id,
        brand_name="Maison Elegance",
        slug="maison-elegance",
        is_verified=True,
    )
    db.add(brand)
    db.flush()

    # Create other brand to test tenant isolation
    other_owner = User(
        email="other@brand.example.com",
        hashed_password="hashed_password_456",
        full_name="Other Director",
        role=UserRole.BRAND_OWNER,
        preferred_language="en",
        is_active=True,
        is_verified=True,
    )
    db.add(other_owner)
    db.flush()

    other_brand = BrandProfile(
        user_id=other_owner.id,
        brand_name="Other Brand",
        slug="other-brand",
        is_verified=True,
    )
    db.add(other_brand)
    db.flush()

    # Create Boutiques
    boutique_cairo = StoreLocation(
        brand_id=brand.id,
        name="Zamalek Flagship Boutique",
        name_ar="بوتيك الزمالك الرئيسي",
        address="15 Brazil Street",
        city="Cairo",
        country="Egypt",
        latitude=30.0561,
        longitude=31.2215,
        phone="+20 2 2735 0000",
        is_bopis_enabled=True,
    )
    boutique_other = StoreLocation(
        brand_id=other_brand.id,
        name="Other Store",
        name_ar="متجر آخر",
        address="Street 10",
        city="Cairo",
        country="Egypt",
        latitude=30.0444,
        longitude=31.2357,
        phone="+20 2 0000 0000",
        is_bopis_enabled=True,
    )
    db.add_all([boutique_cairo, boutique_other])
    db.flush()

    # Create customers for email notification tests
    # Customer 1: Opted-in
    c1 = User(
        email="shopper1@example.com",
        hashed_password="pw1",
        full_name="Amina Mansour",
        role=UserRole.CONSUMER,
        preferred_language="ar",
        is_active=True,
        is_verified=True,
    )
    # Customer 2: Opted-out of marketing
    c2 = User(
        email="shopper2@example.com",
        hashed_password="pw2",
        full_name="John Doe",
        role=UserRole.CONSUMER,
        preferred_language="en",
        is_active=True,
        is_verified=True,
    )
    db.add_all([c1, c2])
    db.flush()

    db.add(EmailPreference(user_id=c1.id, marketing=True, engagement=True))
    db.add(EmailPreference(user_id=c2.id, marketing=False, engagement=True))

    db.commit()

    token = create_access_token({"sub": str(owner.id), "role": UserRole.BRAND_OWNER})
    client = TestClient(app)

    yield {
        "client": client,
        "token": token,
        "brand": brand,
        "other_brand": other_brand,
        "boutique": boutique_cairo,
        "other_boutique": boutique_other,
        "db": db,
    }

    if old_override is not None:
        app.dependency_overrides[get_db] = old_override
    else:
        app.dependency_overrides.pop(get_db, None)
    db.close()


def test_download_official_catalog_template(test_env):
    client = test_env["client"]
    token = test_env["token"]

    response = client.get(
        "/api/v1/partner/catalog/template.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["Content-Type"]
    assert "confit-catalog-template.csv" in response.headers["Content-Disposition"]
    content = response.text
    assert "product_name,sku,description,category,price,currency" in content
    assert "Classic Cotton Shirt" in content
    assert "Tailored Wool Blazer" in content


def test_preview_csv_validation_with_clean_and_error_rows(test_env):
    client = test_env["client"]
    token = test_env["token"]
    boutique = test_env["boutique"]

    # CSV with 1 valid row, 1 row with negative price, 1 row with duplicate SKU
    csv_data = f"""product_name,sku,description,category,price,currency,color,size,stock_quantity,image_url,branch_id
Linen Summer Shirt,SKU-TEST-001,Pure Italian linen shirt,shirts,950.00,EGP,White,M,15,https://images.pexels.com/photos/297933/shirt.jpg,{boutique.id}
Invalid Price Pants,SKU-TEST-002,Pants with negative price,shirts,-50.00,EGP,Beige,L,10,https://images.pexels.com/photos/1598507/pants.jpg,{boutique.id}
Duplicate SKU Belt,SKU-TEST-001,Duplicate SKU row,accessories,450.00,EGP,Black,One Size,5,https://images.pexels.com/photos/1598508/belt.jpg,{boutique.id}
"""

    files = {"file": ("test_catalog.csv", csv_data.encode("utf-8"), "text/csv")}
    response = client.post(
        "/api/v1/partner/catalog/preview-csv",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_rows"] == 3
    assert data["valid_rows_count"] == 1
    assert data["error_rows_count"] == 2
    assert data["can_import"] is True
    assert len(data["errors"]) >= 2
    # Check that error fields are identified
    fields = [e["field"] for e in data["errors"]]
    assert "base_price" in fields or "price" in fields or "sku_code" in fields


def test_tenant_isolation_rejects_foreign_branch(test_env):
    client = test_env["client"]
    token = test_env["token"]
    other_boutique = test_env["other_boutique"]

    # CSV attempting to assign stock to a branch belonging to another brand
    csv_data = f"""product_name,sku,description,category,price,currency,color,size,stock_quantity,image_url,branch_id
Unauthorized Branch Item,SKU-ILLEGAL-01,Illegally assigning other brand store,shirts,1200.00,EGP,Navy,M,20,https://images.pexels.com/photos/297933/test.jpg,{other_boutique.id}
"""

    files = {"file": ("test_tenant.csv", csv_data.encode("utf-8"), "text/csv")}
    response = client.post(
        "/api/v1/partner/catalog/preview-csv",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid_rows_count"] == 0
    assert any("tenant isolation" in e["message"].lower() for e in data["errors"])


def test_confirm_import_creates_products_and_branch_inventory(test_env):
    client = test_env["client"]
    token = test_env["token"]
    boutique = test_env["boutique"]
    db = test_env["db"]
    brand = test_env["brand"]

    csv_data = f"""product_name,sku,description,category,price,currency,original_price,color,size,stock_quantity,image_url
Cashmere Knit Sweater,SKU-CASH-101,Luxurious 100% Mongolian cashmere,outerwear,3200.00,EGP,3800.00,Navy Blue,L,18,https://images.pexels.com/photos/1342609/sweater.jpg
Silk Evening Scarf,SKU-SILK-202,Handcrafted pure silk scarf,accessories,850.00,EGP,1100.00,Burgundy,One Size,24,https://images.pexels.com/photos/1598508/scarf.jpg
"""

    files = {"file": ("new_collection.csv", csv_data.encode("utf-8"), "text/csv")}
    response = client.post(
        f"/api/v1/partner/catalog/confirm-import?target_store_id={boutique.id}&send_notifications=true",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] in ("completed", "partially_completed")
    assert data["accepted_rows"] == 2
    assert data["rejected_rows"] == 0

    # Verify database state
    p1 = db.query(Product).filter_by(brand_id=brand.id, title="Cashmere Knit Sweater").first()
    assert p1 is not None
    assert str(p1.base_price) == "3200.00"
    assert str(p1.compare_at_price) == "3800.00"

    sku1 = db.query(ProductSKU).filter_by(sku_code="SKU-CASH-101").first()
    assert sku1 is not None
    assert sku1.stock_level == 18

    # Verify branch store inventory was created
    inv = db.query(StoreInventory).filter_by(store_id=boutique.id, sku_id=sku1.id).first()
    assert inv is not None
    assert inv.quantity == 18
    assert inv.brand_id == brand.id

    # Verify email outbox entry was recorded for opted-in customer
    outbox_entries = db.query(EmailOutbox).filter(EmailOutbox.event_key.like(f"import:{data['job_id']}:%")).all()
    assert len(outbox_entries) >= 1
    # Check that shopper1 (marketing=True) received a pending/sent outbox row
    recipients = [e.recipient for e in outbox_entries]
    assert "shopper1@example.com" in recipients
    # Check that shopper2 (marketing=False) was excluded
    assert "shopper2@example.com" not in recipients


def test_export_error_report_csv(test_env):
    client = test_env["client"]
    token = test_env["token"]

    errors_payload = {
        "errors": [
            {
                "row": 3,
                "field": "price",
                "value": "=SUM(A1:B1)",  # Formula injection attempt
                "message": "Price must be a positive number",
                "suggestion": "Enter a valid decimal price like 500.00",
            },
            {
                "row": 5,
                "field": "category",
                "value": "unknown_cat",
                "message": "Category not found",
                "suggestion": "Use an existing category",
            },
        ]
    }

    response = client.post(
        "/api/v1/partner/catalog/export-errors",
        headers={"Authorization": f"Bearer {token}"},
        json=errors_payload,
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["Content-Type"]
    content = response.text
    # Verify formula was sanitized with single quote prefix
    assert "'=SUM(A1:B1)" in content
    assert "Row Number,Field,Submitted Value,Error Reason,Corrective Action" in content
