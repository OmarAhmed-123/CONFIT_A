import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.core.security import get_password_hash
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def client():
    return TestClient(app)


def test_automated_brand_registration_workflow(client):
    """Verify end-to-end brand registration: profile creation, slug generation, workspace."""
    db_session = TestingSessionLocal()
    unique_name = "Maison L'Atelier Haute"
    unique_email = "director@atelier-haute.com"

    # 1. Register brand
    payload = {
        "brand_name": unique_name,
        "email": unique_email,
        "password": "SecurePassword123!",
        "full_name": "Jean-Paul Gautier",
        "phone": "+971501234567",
        "description": "Exquisite Parisian couture and artisanal tailoring in the Middle East.",
        "website": "https://atelier-haute.com",
        "city": "Dubai",
        "country": "UAE",
    }
    res = client.post("/api/v1/brand/register", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()

    assert "access_token" in data
    assert data["status"] == "created"
    assert data["brand"]["brand_name"] == unique_name
    assert data["brand"]["slug"] == "maison-l-atelier-haute"
    # Unverified by default per platform governance
    assert data["brand"]["is_verified"] is False
    assert "Welcome to CONFIT_A!" in data["message"]
    token = data["access_token"]
    brand_id = data["brand"]["id"]

    # 2. Duplicate registration protection (same brand name from another email)
    dup_res = client.post("/api/v1/brand/register", json={
        **payload,
        "email": "impostor@atelier-fake.com",
    })
    assert dup_res.status_code == 409
    assert "already registered" in dup_res.text

    # 3. Idempotent retry by the same brand owner with same credentials
    retry_res = client.post("/api/v1/brand/register", json=payload)
    assert retry_res.status_code == 201
    assert retry_res.json()["status"] == "existing"
    assert retry_res.json()["brand"]["id"] == brand_id

    # 4. Check Onboarding Status endpoint
    headers = {"Authorization": f"Bearer {token}"}
    status_res = client.get("/api/v1/partner/onboarding-status", headers=headers)
    assert status_res.status_code == 200, status_res.text
    status_data = status_res.json()

    assert status_data["brand_id"] == brand_id
    assert status_data["is_verified"] is False
    assert status_data["is_published"] is False
    assert len(status_data["steps"]) == 7
    assert status_data["steps"][0]["key"] == "profile"
    assert status_data["steps"][1]["key"] == "branches"

    # 5. Branch Management (Add First Branch)
    branch_payload = {
        "name": "Maison L'Atelier — Dubai Mall Fashion Avenue",
        "city": "Dubai",
        "country": "UAE",
        "address": "Fashion Avenue, Level 2, The Dubai Mall",
        "latitude": 25.1985,
        "longitude": 55.2799,
        "phone": "+97143219876",
        "pickup_instructions": "VIP Valet parking available at Fashion Avenue entrance.",
        "is_bopis_enabled": True,
    }
    store_res = client.post("/api/v1/partner/stores", json=branch_payload, headers=headers)
    assert store_res.status_code == 201, store_res.text
    store_data = store_res.json()
    store_id = store_data["id"]
    assert "google_maps_url" in store_data
    assert "25.198500,55.279900" in store_data["google_maps_url"]

    # 6. Coordinate validation range check
    bad_coord_res = client.post("/api/v1/partner/stores", json={
        **branch_payload,
        "name": "Invalid Latitude Branch",
        "latitude": 150.0,  # Invalid!
    }, headers=headers)
    assert bad_coord_res.status_code == 422  # Pydantic ge=-90 le=90

    # 7. Get Branch Details
    detail_res = client.get(f"/api/v1/partner/stores/{store_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["name"] == branch_payload["name"]
    assert detail_res.json()["is_location_verified"] is True

    # 8. Check Storefront Visibility Gate: Brand is NOT yet verified, so it must NOT appear in public discovery
    pub_brands_res = client.get("/api/v1/catalog/brands")
    assert pub_brands_res.status_code == 200
    pub_slugs = [b["slug"] for b in pub_brands_res.json()]
    assert "maison-l-atelier-haute" not in pub_slugs

    # Direct query to unverified brand returns 404
    pub_detail_res = client.get("/api/v1/catalog/brands/maison-l-atelier-haute")
    assert pub_detail_res.status_code == 404

    # 9. Admin Verification & Approval Workflow
    # Create or fetch admin user
    admin_user = db_session.query(User).filter(User.role == UserRole.ADMIN).first()
    if not admin_user:
        admin_user = User(
            email="platform-admin@confit.app",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Platform Administrator",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        db_session.add(admin_user)
        db_session.commit()

    admin_login = client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "AdminPass123!" if not admin_user.phone else "admin123",
    })
    # If standard admin password differs, issue token directly via AuthService
    if admin_login.status_code != 200:
        from backend.app.services.auth_service import AuthService
        admin_token = AuthService(db_session)._issue_session_tokens(admin_user)["access_token"]
    else:
        admin_token = admin_login.json()["access_token"]

    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin verifies the brand
    verify_res = client.post(f"/api/v1/admin/catalog/brands/{brand_id}/verify", headers=admin_headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "verified"
    assert verify_res.json()["is_verified"] is True

    # 10. Storefront Visibility Gate: Now brand IS published and discoverable!
    after_verify_res = client.get("/api/v1/catalog/brands")
    assert after_verify_res.status_code == 200
    updated_slugs = [b["slug"] for b in after_verify_res.json()]
    assert "maison-l-atelier-haute" in updated_slugs

    published_detail = client.get("/api/v1/catalog/brands/maison-l-atelier-haute")
    assert published_detail.status_code == 200
    assert published_detail.json()["brand_name"] == unique_name
    assert len(published_detail.json()["stores"]) == 1
    assert published_detail.json()["stores"][0]["name"] == branch_payload["name"]

    # 11. Delete Branch with Tenant Check
    del_res = client.delete(f"/api/v1/partner/stores/{store_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Store no longer exists
    assert client.get(f"/api/v1/partner/stores/{store_id}", headers=headers).status_code == 404
    db_session.close()
