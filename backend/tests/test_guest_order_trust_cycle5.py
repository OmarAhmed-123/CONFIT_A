"""
Cycle5 — 003 Guest Order Trust & Returns — second factor enforcement (CUS-09, CUS-10)

Tests the fixed assert_order_access logic that requires email or session token for guest orders.
Does not require DB, just the service method logic.
"""

import pytest
from backend.app.services.commerce_service import CommerceService
from backend.app.core.exceptions import AuthenticationError, AuthorizationError

# Mock repo not needed, we test assert_order_access directly with dict
# Create a dummy service with None db (method doesn't use db)

class DummyService(CommerceService):
    def __init__(self):
        # Don't call super, just set needed attrs
        self.commerce_repo = None
        self.db = None

def test_guest_order_requires_second_factor():
    svc = DummyService()
    guest_order = {
        "user_id": None,
        "guest_email": "guest@example.com",
        "guest_session_token": "sess_abc123"
    }
    # No second factor -> should raise
    with pytest.raises(AuthenticationError, match="second factor"):
        svc.assert_order_access(guest_order, user=None, session_token=None, guest_email=None)

    # Wrong email -> raise
    with pytest.raises(AuthenticationError):
        svc.assert_order_access(guest_order, user=None, session_token=None, guest_email="wrong@example.com")

    # Correct email -> allow
    svc.assert_order_access(guest_order, user=None, session_token=None, guest_email="guest@example.com")
    svc.assert_order_access(guest_order, user=None, session_token=None, guest_email="GUEST@example.com")  # case-insensitive

    # Correct session token -> allow
    svc.assert_order_access(guest_order, user=None, session_token="sess_abc123", guest_email=None)

    # Wrong session token -> raise
    with pytest.raises(AuthenticationError):
        svc.assert_order_access(guest_order, user=None, session_token="wrong_token", guest_email=None)

def test_registered_order_requires_auth():
    svc = DummyService()
    registered_order = {"user_id": 123, "guest_email": None, "guest_session_token": None}
    # Anonymous -> should require auth
    with pytest.raises(AuthenticationError, match="registered customer"):
        svc.assert_order_access(registered_order, user=None)

    # Wrong user -> AuthorizationError
    class FakeUser:
        id = 999
        role = "customer"
    with pytest.raises(AuthorizationError):
        svc.assert_order_access(registered_order, user=FakeUser())

    # Correct user -> allow
    class CorrectUser:
        id = 123
        role = "customer"
    svc.assert_order_access(registered_order, user=CorrectUser())

def test_admin_bypass():
    svc = DummyService()
    order = {"user_id": 123, "guest_email": None, "guest_session_token": None}
    class AdminUser:
        id = 1
        role = "admin"
        # Simulate UserRole.ADMIN check — need enum? Use string "admin" but code checks UserRole.ADMIN
        # We'll mock by setting role to have value that matches check via getattr
        # Actually code does: if user and getattr(user, "role", None) == UserRole.ADMIN
        # So we need to use actual enum
    from backend.app.models.user import UserRole
    class AdminUserEnum:
        id = 1
        role = UserRole.ADMIN
    svc.assert_order_access(order, user=AdminUserEnum())

def test_guest_order_legacy_without_token_email_only():
    svc = DummyService()
    legacy_order = {
        "user_id": None,
        "guest_email": "legacy@example.com",
        "guest_session_token": None
    }
    # Email match should still work for legacy rows
    svc.assert_order_access(legacy_order, user=None, guest_email="legacy@example.com")
    with pytest.raises(AuthenticationError):
        svc.assert_order_access(legacy_order, user=None, guest_email=None)
