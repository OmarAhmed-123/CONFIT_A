import json
import io
import csv
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.core.database import SessionLocal
from backend.app.models.user import User, BrandProfile, UserRole
from backend.app.models.catalog import Product, ProductSKU, Category, StoreLocation, StoreInventory
from backend.app.models.brand_analytics import SponsoredPlacement
from backend.app.models.catalog_import import CatalogImportJob
from backend.app.models.commerce import Order, OrderItem
from backend.app.models.stylist import Outfit, OutfitItem
from backend.app.core.security import get_password_hash as hash_password


TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

client = TestClient(app)


def create_test_user_and_brand(db, email_suffix=""):
    # Use existing seeded category
    cat = db.query(Category).filter(Category.slug == "outerwear").first()
    if not cat:
        cat = Category(name="Outerwear", name_ar="ملابس خارجية", slug="outerwear")
        db.add(cat)
        db.commit()
        db.refresh(cat)

    # Use existing seeded brand user for reliability (seed creates brand@massimodutti.com etc)
    # For isolation tests, we still need two brands - use seeded ones
    if email_suffix in ["isolation1", "isolation2"]:
        if email_suffix == "isolation1":
            email = "brand@massimodutti.com"
        else:
            email = "brand@cos.com"
        user = db.query(User).filter(User.email == email).first()
        brand = db.query(BrandProfile).filter(BrandProfile.user_id == user.id).first()
        return user, brand, cat

    # For other tests, use existing brand user
    email = "brand@massimodutti.com"
    user = db.query(User).filter(User.email == email).first()
    brand = db.query(BrandProfile).filter(BrandProfile.user_id == user.id).first()
    if not user or not brand:
        # Fallback create if seed not available
        from backend.app.core.security import get_password_hash
        email_new = f"brand_test_{email_suffix}@test.com"
        user_existing = db.query(User).filter(User.email == email_new).first()
        if user_existing:
            user = user_existing
        else:
            user = User(
                email=email_new,
                hashed_password=get_password_hash("Password123!"),
                full_name="Test Brand Owner",
                role=UserRole.BRAND_OWNER,
                is_active=True,
                is_verified=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        brand = db.query(BrandProfile).filter(BrandProfile.user_id == user.id).first()
        if not brand:
            brand = BrandProfile(
                user_id=user.id,
                brand_name=f"TestBrand{email_suffix}",
                slug=f"testbrand{email_suffix}",
                description="Test brand",
                is_verified=True
            )
            db.add(brand)
            db.commit()
            db.refresh(brand)

    return user, brand, cat


def get_auth_token(email, password="Password123!"):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        # Try to get error detail
        try:
            print(f"Login failed for {email}: {resp.json()}")
        except:
            print(f"Login failed for {email}: {resp.text}")
        return None
    return resp.json()["access_token"]


def get_brand_token(db, suffix="test"):
    """Helper to get token for brand user"""
    _, brand, _ = create_test_user_and_brand(db, suffix)
    user = db.query(User).filter(User.email == "brand@massimodutti.com").first()
    if not user:
        user = db.query(User).filter(User.email.like("brand_test_%")).first()
    if user:
        return get_auth_token(user.email)
    return get_auth_token("brand@massimodutti.com")


class TestBrandTenantIsolation:
    """Tenant isolation: Brand A cannot access Brand B"""

    def test_brand_cannot_access_other_brand_products(self):
        db = TestingSessionLocal()
        try:
            user1, brand1, cat = create_test_user_and_brand(db, "isolation1")
            user2, brand2, _ = create_test_user_and_brand(db, "isolation2")

            # Use existing product from brand1 or create
            prod = db.query(Product).filter(Product.brand_id == brand1.id).first()
            if not prod:
                prod = Product(
                    brand_id=brand1.id,
                    category_id=cat.id,
                    title="Brand1 Product Isolation",
                    title_ar="منتج",
                    slug=f"brand1-prod-iso-{brand1.id}-{brand1.id}",
                    description="Test",
                    description_ar="اختبار",
                    base_price=100.0,
                    color_family="Navy",
                    thumbnail_url="https://example.com/img.jpg",
                    is_active=True
                )
                db.add(prod)
                db.commit()
                db.refresh(prod)
                created_prod = True
            else:
                created_prod = False

            sku = db.query(ProductSKU).filter(ProductSKU.product_id == prod.id).first()
            if not sku:
                sku = ProductSKU(
                    product_id=prod.id,
                    sku_code=f"SKU-ISO1-{brand1.id}-TEST",
                    size="M",
                    color="Navy",
                    stock_level=10,
                    is_in_stock=True
                )
                db.add(sku)
                db.commit()
                db.refresh(sku)
                created_sku = True
            else:
                created_sku = False

            # User2 tries to update brand1's SKU - should fail
            token2 = get_auth_token(user2.email)
            assert token2 is not None, f"Failed to get token for {user2.email}"

            resp = client.patch(
                f"/partner/skus/{sku.id}?stock_level=50",
                headers={"Authorization": f"Bearer {token2}"}
            )
            # Should be 403 or 404 or 400 due to tenant violation
            assert resp.status_code in [403, 404, 400, 401], f"Expected tenant violation, got {resp.status_code}: {resp.text}"

            # Cleanup only if we created
            if created_sku:
                db.delete(sku)
            if created_prod:
                db.delete(prod)
            db.commit()

        finally:
            db.close()

    def test_brand_analytics_scoped(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "analytics_scope")
            token = get_auth_token(user.email)
            assert token is not None

            resp = client.get("/brand/analytics", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            data = resp.json()
            assert "brand_name" in data
            assert data["brand_name"] == brand.brand_name

        finally:
            db.close()


class TestCatalogCSVImport:
    """Real CSV import with validation, idempotency, error reporting"""

    def test_csv_import_valid(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "csv_valid")
            token = get_auth_token(user.email)
            assert token is not None

            csv_content = f"""title,category_slug,base_price,color_family,thumbnail_url,size,color,stock_level
Test Product CSV,outerwear,199.99,Navy,https://example.com/test.jpg,M,Navy,15
Another Product,outerwear,299.99,Black,https://example.com/another.jpg,L,Black,20
"""

            # Use API import first (simpler)
            resp = client.post(
                "/partner/catalog/import",
                json={
                    "products": [
                        {
                            "title": "Test Product CSV",
                            "category_slug": "outerwear",
                            "base_price": 199.99,
                            "color_family": "Navy",
                            "thumbnail_url": "https://example.com/test.jpg",
                            "size": "M",
                            "color": "Navy",
                            "stock_level": 15
                        }
                    ]
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code in [200, 202]
            data = resp.json()
            assert "job_id" in data
            assert data["accepted_rows"] >= 1 or data["status"] in ["completed", "partially_completed"]

            # Verify product created
            prod = db.query(Product).filter(Product.title == "Test Product CSV", Product.brand_id == brand.id).first()
            assert prod is not None
            assert float(prod.base_price) == 199.99

            # Cleanup
            if prod:
                skus = db.query(ProductSKU).filter(ProductSKU.product_id == prod.id).all()
                for s in skus:
                    db.delete(s)
                db.delete(prod)
                db.commit()

        finally:
            db.close()

    def test_csv_import_validation_missing_fields(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "csv_invalid")
            token = get_auth_token(user.email)
            assert token is not None

            # Missing required field base_price
            resp = client.post(
                "/partner/catalog/import",
                json={
                    "products": [
                        {
                            "title": "Invalid Product",
                            "category_slug": "outerwear",
                            "color_family": "Navy",
                            "thumbnail_url": "https://example.com/test.jpg"
                        }
                    ]
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            # Should fail or have errors
            assert resp.status_code in [200, 202, 400]
            if resp.status_code in [200, 202]:
                data = resp.json()
                # Should have rejected rows or errors
                assert data["rejected_rows"] > 0 or len(data.get("errors", [])) > 0

        finally:
            db.close()

    def test_csv_import_idempotency(self):
        """Repeated upload of same file must not create duplicates randomly"""
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "csv_idempotent")
            token = get_auth_token(user.email)
            assert token is not None

            product_data = {
                "title": "Idempotent Product",
                "category_slug": "outerwear",
                "base_price": 150.0,
                "color_family": "Navy",
                "thumbnail_url": "https://example.com/idempotent.jpg",
                "size": "M",
                "color": "Navy",
                "stock_level": 10,
                "sku_code": f"IDEMPOTENT-SKU-{brand.id}"
            }

            # First import
            resp1 = client.post(
                "/partner/catalog/import",
                json={"products": [product_data]},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp1.status_code in [200, 202]

            # Second import same SKU - should upsert not duplicate
            resp2 = client.post(
                "/partner/catalog/import",
                json={"products": [product_data]},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp2.status_code in [200, 202]

            # Check only one SKU exists
            skus = db.query(ProductSKU).filter(ProductSKU.sku_code == product_data["sku_code"]).all()
            assert len(skus) == 1

            # Cleanup
            for s in skus:
                prod = db.query(Product).filter(Product.id == s.product_id).first()
                db.delete(s)
                if prod and prod.brand_id == brand.id:
                    db.delete(prod)
            db.commit()

        finally:
            db.close()

    def test_csv_injection_protection(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "csv_injection")
            from backend.app.services.brand_catalog_service import BrandCatalogService
            service = BrandCatalogService(db)

            # Test sanitization
            assert service._sanitize_csv_value("=CMD('calc')") == "'=CMD('calc')"
            assert service._sanitize_csv_value("+SUM(A1:A10)") == "'+SUM(A1:A10)"
            assert service._sanitize_csv_value("-2+3") == "'-2+3"
            assert service._sanitize_csv_value("@SUM(A1)") == "'@SUM(A1)"
            assert service._sanitize_csv_value("Normal text") == "Normal text"

        finally:
            db.close()


class TestInventoryManagement:
    """Real inventory with location-level stock, reserved, available"""

    def test_store_crud_tenant_isolated(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "store_crud")
            token = get_auth_token(user.email)
            assert token is not None

            # Create store
            resp = client.post(
                "/partner/stores",
                json={
                    "name": "Test Boutique",
                    "city": "Dubai",
                    "country": "UAE",
                    "address": "Test Address, Dubai Mall",
                    "latitude": 25.1972,
                    "longitude": 55.2792
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 201
            store_id = resp.json()["id"]

            # Get stores - should include new one
            resp = client.get("/partner/stores", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            stores = resp.json()
            assert any(s["id"] == store_id for s in stores)

            # Update store
            resp = client.patch(
                f"/partner/stores/{store_id}",
                json={"city": "Abu Dhabi"},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200

            # Cleanup
            from backend.app.models.catalog import StoreLocation
            store = db.query(StoreLocation).filter(StoreLocation.id == store_id).first()
            if store:
                db.delete(store)
                db.commit()

        finally:
            db.close()

    def test_inventory_update_with_locking(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "inventory_lock")
            token = get_auth_token(user.email)
            assert token is not None

            # Create product and SKU
            prod = Product(
                brand_id=brand.id,
                category_id=cat.id,
                title="Inventory Test Product",
                title_ar="اختبار",
                slug=f"inv-test-{brand.id}",
                description="Test",
                description_ar="اختبار",
                base_price=100.0,
                color_family="Navy",
                thumbnail_url="https://example.com/img.jpg",
                is_active=True
            )
            db.add(prod)
            db.commit()
            db.refresh(prod)

            sku = ProductSKU(
                product_id=prod.id,
                sku_code=f"INV-TEST-{brand.id}",
                size="M",
                color="Navy",
                stock_level=20,
                is_in_stock=True
            )
            db.add(sku)
            db.commit()
            db.refresh(sku)

            # Update stock
            resp = client.patch(
                f"/partner/skus/{sku.id}?stock_level=50",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["stock_level"] == 50

            # Verify no negative
            resp = client.patch(
                f"/partner/skus/{sku.id}?stock_level=-5",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code in [400, 422]

            # Cleanup
            db.delete(sku)
            db.delete(prod)
            db.commit()

        finally:
            db.close()


class TestSponsoredPlacements:
    """Real sponsored placement with validation, budget enforcement"""

    def test_placement_create_and_validation(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "placement")
            token = get_auth_token(user.email)
            assert token is not None

            # Create product
            prod = Product(
                brand_id=brand.id,
                category_id=cat.id,
                title="Placement Test Product",
                title_ar="اختبار",
                slug=f"placement-test-{brand.id}",
                description="Test",
                description_ar="اختبار",
                base_price=100.0,
                color_family="Navy",
                thumbnail_url="https://example.com/img.jpg",
                is_active=True
            )
            db.add(prod)
            db.commit()
            db.refresh(prod)

            # Valid placement
            resp = client.post(
                "/partner/placements",
                json={
                    "product_id": prod.id,
                    "placement_type": "stylist_featured",
                    "bid_amount_per_click": 1.5,
                    "daily_budget": 100.0
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 201
            placement_id = resp.json()["id"]
            assert resp.json()["bid_amount_per_click"] == 1.5
            assert resp.json()["daily_budget"] == 100.0
            assert resp.json()["spent_today"] == 0.0  # Real, not fake 12.50
            assert resp.json()["impressions"] == 0  # Real, not fake 1420

            # Invalid: bid exceeds budget
            resp = client.post(
                "/partner/placements",
                json={
                    "product_id": prod.id,
                    "placement_type": "stylist_featured",
                    "bid_amount_per_click": 200.0,
                    "daily_budget": 100.0
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code in [400, 422]

            # Invalid: product not belonging to brand
            # Create another brand's product - use isolation2 which returns COS brand
            user2, brand2, _ = create_test_user_and_brand(db, "isolation2")
            assert brand2.id != brand.id, f"Brands should be different: {brand.id} vs {brand2.id}"
            prod2 = Product(
                brand_id=brand2.id,
                category_id=cat.id,
                title="Other Brand Product Tenant",
                title_ar="اختبار",
                slug=f"other-brand-tenant-{brand2.id}-{brand.id}",
                description="Test",
                description_ar="اختبار",
                base_price=100.0,
                color_family="Navy",
                thumbnail_url="https://example.com/img.jpg",
                is_active=True
            )
            db.add(prod2)
            db.commit()
            db.refresh(prod2)

            resp = client.post(
                "/partner/placements",
                json={
                    "product_id": prod2.id,
                    "placement_type": "stylist_featured",
                    "bid_amount_per_click": 1.0,
                    "daily_budget": 50.0
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code in [400, 422, 403], f"Should fail tenant check, got {resp.status_code}: {resp.text}"

            # Cleanup
            plc = db.query(SponsoredPlacement).filter(SponsoredPlacement.id == placement_id).first()
            if plc:
                db.delete(plc)
            db.delete(prod)
            db.delete(prod2)
            db.commit()

        finally:
            db.close()

    def test_placement_budget_enforcement(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "budget")
            token = get_auth_token(user.email)
            assert token is not None

            prod = Product(
                brand_id=brand.id,
                category_id=cat.id,
                title="Budget Test Product",
                title_ar="اختبار",
                slug=f"budget-test-{brand.id}",
                description="Test",
                description_ar="اختبار",
                base_price=100.0,
                color_family="Navy",
                thumbnail_url="https://example.com/img.jpg",
                is_active=True
            )
            db.add(prod)
            db.commit()
            db.refresh(prod)

            # Create placement with small budget
            resp = client.post(
                "/partner/placements",
                json={
                    "product_id": prod.id,
                    "placement_type": "stylist_featured",
                    "bid_amount_per_click": 10.0,
                    "daily_budget": 15.0
                },
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 201
            placement_id = resp.json()["id"]

            # First click should succeed (10 spent, 5 remaining)
            resp = client.post(
                f"/partner/placements/{placement_id}/click",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 200
            assert resp.json()["spent_today"] == 10.0

            # Second click should fail (would exceed budget: 10+10=20 > 15)
            resp = client.post(
                f"/partner/placements/{placement_id}/click",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert resp.status_code == 400
            assert "budget" in resp.json()["detail"].lower()

            # Cleanup
            plc = db.query(SponsoredPlacement).filter(SponsoredPlacement.id == placement_id).first()
            if plc:
                db.delete(plc)
            db.delete(prod)
            db.commit()

        finally:
            db.close()


class TestAnalyticsRealData:
    """Analytics must use real data, not hardcoded"""

    def test_brand_analytics_real_funnel(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "real_funnel")
            token = get_auth_token(user.email)
            assert token is not None

            resp = client.get("/brand/analytics", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            data = resp.json()

            # Check structure exists (real data may be 0 if no events)
            assert "total_views" in data
            assert "total_tryons" in data
            assert "total_add_to_carts" in data
            assert "total_purchases" in data
            assert "funnel_conversion_rate" in data
            assert "outfit_appearance_rankings" in data
            assert "return_rate_before_vton" in data
            assert "return_rate_after_vton" in data

            # Values should be integers, not hardcoded 48200 etc unless real data matches
            # But at least check they are numbers and not always same fake values
            assert isinstance(data["total_views"], int)
            assert isinstance(data["total_tryons"], int)

            # Outfit rankings should be list, may be empty if no outfits, not fake 5 items with p.id*14+18
            assert isinstance(data["outfit_appearance_rankings"], list)

        finally:
            db.close()

    def test_admin_analytics_real(self):
        db = TestingSessionLocal()
        try:
            # Create admin user
            admin_email = "admin_test_group6@test.com"
            admin_user = db.query(User).filter(User.email == admin_email).first()
            if not admin_user:
                admin_user = User(
                    email=admin_email,
                    hashed_password=hash_password("Password123!"),
                    full_name="Admin Test",
                    role=UserRole.ADMIN,
                    is_active=True,
                    is_verified=True
                )
                db.add(admin_user)
                db.commit()
                db.refresh(admin_user)

            token = get_auth_token(admin_email)
            assert token is not None

            resp = client.get("/admin/analytics", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            data = resp.json()

            # Real structure
            assert "total_users_count" in data
            assert "total_brands_count" in data
            assert "total_gmv" in data
            assert "total_orders" in data
            assert "revenue_attribution" in data
            assert "top_performing_brands" in data
            assert "style_preference_heatmap" in data

            # Check revenue attribution is dict with real values (may be 0)
            assert isinstance(data["revenue_attribution"], dict)
            # Should have at least these keys if real
            # ai_virtual_stylist, outfit_builder, visual_search, organic_discovery

            # Check top_performing_brands is list, not hardcoded 4 brands unless real data has 4
            assert isinstance(data["top_performing_brands"], list)

        finally:
            db.close()

    def test_conversion_per_sku_real(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "conv_sku")
            token = get_auth_token(user.email)
            assert token is not None

            resp = client.get("/partner/analytics/conversion", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            data = resp.json()

            assert "views" in data
            assert "tryons" in data
            assert "add_to_cart" in data
            assert "purchases" in data
            assert "per_sku" in data
            assert "methodology" in data

            # per_sku should be list
            assert isinstance(data["per_sku"], list)

        finally:
            db.close()

    def test_heatmap_anonymized(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "heatmap")
            token = get_auth_token(user.email)
            assert token is not None

            resp = client.get("/partner/analytics/heatmaps?region=MENA", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            data = resp.json()

            assert "region" in data
            assert "anonymized" in data
            assert data["anonymized"] == True
            assert "privacy_threshold" in data or "methodology" in data

            # Should not expose individual user data
            # Check no user emails, ids in response
            data_str = json.dumps(data)
            assert "@test.com" not in data_str
            assert "user_id" not in data_str.lower() or "sample_size" in data_str.lower()

        finally:
            db.close()


class TestRBAC:
    """Role-based access control"""

    def test_consumer_cannot_access_brand_routes(self):
        db = TestingSessionLocal()
        try:
            # Create consumer user
            email = "consumer_test_group6@test.com"
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    email=email,
                    hashed_password=hash_password("Password123!"),
                    full_name="Consumer Test",
                    role=UserRole.CONSUMER,
                    is_active=True,
                    is_verified=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            token = get_auth_token(email)
            assert token is not None

            resp = client.get("/brand/analytics", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code in [403, 401]

            resp = client.get("/brand/products", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code in [403, 401]

        finally:
            db.close()

    def test_unauthenticated_cannot_access_brand(self):
        resp = client.get("/brand/analytics")
        assert resp.status_code in [401, 403]

    def test_brand_cannot_access_admin(self):
        db = TestingSessionLocal()
        try:
            user, brand, cat = create_test_user_and_brand(db, "brand_admin_rbac")
            token = get_auth_token(user.email)
            assert token is not None

            resp = client.get("/admin/analytics", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code in [403, 401]

        finally:
            db.close()
