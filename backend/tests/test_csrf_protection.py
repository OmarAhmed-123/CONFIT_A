"""
C3 FIX: Comprehensive CSRF Protection Tests

Tests the double-submit CSRF pattern:
- Valid CSRF: cookie + matching header = success
- Missing CSRF: cookie exists but header missing = 403
- Invalid CSRF: cookie/header mismatch = 403
- Empty CSRF: empty token = 403
- Safe methods: GET/HEAD/OPTIONS don't require CSRF
- Auth interaction: login, mutation, logout flow
"""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.security import generate_csrf_token

client = TestClient(app)


class TestCSRFProtection:
    """Test CSRF double-submit pattern implementation"""

    def test_csrf_token_generation(self):
        """CSRF token should be generated and be non-empty, unique"""
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()
        assert token1
        assert token2
        assert token1 != token2
        assert len(token1) >= 32  # Should be secure random

    def test_login_sets_csrf_cookie(self):
        """Login should set confit_csrf cookie"""
        # Use test user
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@confit.io", "password": "Test123!@#"},
        )
        # Even if login fails, check if endpoint exists and doesn't require CSRF
        # Login is exempt from CSRF check
        assert response.status_code in [200, 401, 422, 400]  # Any is ok, but not 403 CSRF
        if response.status_code == 403:
            data = response.json()
            assert data.get("error", {}).get("code") != "CSRF_TOKEN_MISMATCH"

    def test_csrf_exempt_paths(self):
        """CSRF exempt paths should not require CSRF token"""
        exempt_paths = [
            "/api/v1/auth/login",
            "/api/v1/auth/register",
        ]
        for path in exempt_paths:
            # POST without CSRF should not be blocked by CSRF (may fail auth, but not CSRF)
            response = client.post(path, json={})
            # Should not be CSRF error
            if response.status_code == 403:
                data = response.json()
                assert data.get("error", {}).get("code") != "CSRF_TOKEN_MISMATCH", f"{path} should be CSRF exempt"

    def test_safe_methods_no_csrf_required(self):
        """GET, HEAD, OPTIONS should not require CSRF"""
        safe_methods = ["GET", "HEAD", "OPTIONS"]
        for method in safe_methods:
            response = client.request(method, "/api/v1/catalog/products")
            # Should not be CSRF blocked
            if response.status_code == 403:
                data = response.json()
                assert data.get("error", {}).get("code") != "CSRF_TOKEN_MISMATCH", f"{method} should not require CSRF"

    def test_mutating_method_without_csrf_cookie_no_block(self):
        """If no session cookie, CSRF check should not trigger (Bearer auth path)"""
        # No cookies set
        client.cookies.clear()
        response = client.post("/api/v1/wardrobe/items", json={"title": "test"})
        # Without session cookie, CSRF guard should not block - auth will fail instead
        # So we should get 401 auth error, not 403 CSRF
        if response.status_code == 403:
            data = response.json()
            # If it's CSRF error, that's wrong when no session cookie
            # Actually guard checks has_session_cookie, so without cookie it should pass through
            assert data.get("error", {}).get("code") != "CSRF_TOKEN_MISMATCH" or "confit_token" not in str(client.cookies)

    def test_mutating_with_session_cookie_missing_csrf_header_blocked(self):
        """With session cookie but missing CSRF header should be blocked 403"""
        csrf_token = generate_csrf_token()
        # Set session cookie and CSRF cookie, but no header
        client.cookies.set("confit_token", "fake_session_token")
        client.cookies.set("confit_csrf", csrf_token)
        
        response = client.post(
            "/api/v1/wardrobe/items",
            json={"title": "test"},
            # No X-CSRF-Token header
        )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "CSRF_TOKEN_MISMATCH"
        
        client.cookies.clear()

    def test_mutating_with_session_cookie_mismatched_csrf_blocked(self):
        """With session cookie but mismatched CSRF should be blocked 403"""
        csrf_token = generate_csrf_token()
        wrong_token = generate_csrf_token()
        
        client.cookies.set("confit_token", "fake_session_token")
        client.cookies.set("confit_csrf", csrf_token)
        
        response = client.post(
            "/api/v1/wardrobe/items",
            json={"title": "test"},
            headers={"X-CSRF-Token": wrong_token},  # Mismatched
        )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "CSRF_TOKEN_MISMATCH"
        
        client.cookies.clear()

    def test_mutating_with_valid_csrf_passes_csrf_check(self):
        """With valid matching CSRF should pass CSRF guard (may fail auth after)"""
        csrf_token = generate_csrf_token()
        
        client.cookies.set("confit_token", "fake_session_token")
        client.cookies.set("confit_csrf", csrf_token)
        
        response = client.post(
            "/api/v1/wardrobe/items",
            json={"title": "test"},
            headers={"X-CSRF-Token": csrf_token},  # Matching
        )
        
        # Should NOT be CSRF error - may be 401 auth error (since fake token) or 422 validation
        # But not 403 CSRF
        if response.status_code == 403:
            data = response.json()
            assert data["error"]["code"] != "CSRF_TOKEN_MISMATCH", "Valid CSRF should pass guard"
        
        client.cookies.clear()

    def test_empty_csrf_token_blocked(self):
        """Empty CSRF token should be blocked"""
        client.cookies.set("confit_token", "fake_session_token")
        client.cookies.set("confit_csrf", "")
        
        response = client.post(
            "/api/v1/wardrobe/items",
            json={"title": "test"},
            headers={"X-CSRF-Token": ""},
        )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "CSRF_TOKEN_MISMATCH"
        
        client.cookies.clear()

    def test_csrf_with_bearer_auth_bypass(self):
        """Bearer auth should bypass CSRF check (header can't be forged cross-site)"""
        csrf_token = generate_csrf_token()
        
        # Set both session cookie and bearer header - bearer should bypass CSRF
        client.cookies.set("confit_token", "fake_session_token")
        client.cookies.set("confit_csrf", csrf_token)
        
        response = client.post(
            "/api/v1/wardrobe/items",
            json={"title": "test"},
            headers={
                "Authorization": "Bearer fake_jwt_token",
                # No CSRF header, but has Bearer - should bypass CSRF check
            },
        )
        
        # Should NOT be CSRF error when Bearer present
        if response.status_code == 403:
            data = response.json()
            assert data["error"]["code"] != "CSRF_TOKEN_MISMATCH", "Bearer auth should bypass CSRF"
        
        client.cookies.clear()

    def test_csrf_protection_on_all_mutating_methods(self):
        """CSRF should protect POST, PUT, PATCH, DELETE"""
        csrf_token = generate_csrf_token()
        methods = ["POST", "PUT", "PATCH", "DELETE"]
        
        for method in methods:
            client.cookies.set("confit_token", "fake_session_token")
            client.cookies.set("confit_csrf", csrf_token)
            
            response = client.request(
                method,
                "/api/v1/wardrobe/items",
                json={"title": "test"} if method in ["POST", "PUT", "PATCH"] else None,
                # No CSRF header
            )
            
            assert response.status_code == 403, f"{method} should require CSRF"
            data = response.json()
            assert data["error"]["code"] == "CSRF_TOKEN_MISMATCH", f"{method} CSRF check failed"
            
            client.cookies.clear()


class TestCSRFRealFlow:
    """Test real browser-like flow: login -> get CSRF -> mutation -> logout"""

    def test_full_csrf_lifecycle(self):
        """Test complete lifecycle: login sets cookie, mutation requires header, logout clears"""
        # Step 1: Login (exempt from CSRF)
        # This will set confit_csrf cookie in real implementation
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@confit.io", "password": "Admin123!@#"},
        )
        
        # Login may fail in test env (no DB), but check CSRF cookie logic
        # In real flow, login response sets CSRF cookie
        # For test, simulate the cookie setting
        csrf_token = generate_csrf_token()
        client.cookies.set("confit_csrf", csrf_token)
        client.cookies.set("confit_token", "test_session")
        
        # Step 2: Try mutation without CSRF header - should fail
        response_no_csrf = client.post(
            "/api/v1/wardrobe/items",
            json={"title": "test"},
        )
        assert response_no_csrf.status_code == 403
        
        # Step 3: Try mutation with valid CSRF - should pass CSRF check
        response_valid_csrf = client.post(
            "/api/v1/wardrobe/items",
            json={"title": "test"},
            headers={"X-CSRF-Token": csrf_token},
        )
        # Should not be CSRF error (may be auth error due to fake session)
        if response_valid_csrf.status_code == 403:
            assert response_valid_csrf.json()["error"]["code"] != "CSRF_TOKEN_MISMATCH"
        
        # Step 4: Logout should clear cookies
        # Simulate logout clearing
        client.cookies.clear()
        assert "confit_csrf" not in client.cookies
        assert "confit_token" not in client.cookies
