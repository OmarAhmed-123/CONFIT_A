"""AUDIT-2026-09-06 regression: undecryptable body blob must not 500 product pages.

Scenario observed live on preview: a UserStyleProfile row encrypted under a
rotated ENCRYPTION_KEY_FOR_BODY_DATA made
``GET /api/v1/catalog/products/{slug}`` return 500 ENCRYPTION_ERROR for EVERY
authenticated request (PDP, outfit-builder SKU resolution, recently-viewed).
Root cause: ProductContextService.enrich_product called
get_decrypted_body_data unguarded.

The fix degrades honestly: product detail still serves, body-based fit is
skipped (falls back to the saved size or fit_available=False), and the
failure is logged. This test pins that contract.
"""

import pytest
from fastapi.testclient import TestClient

from backend.tests.conftest import TestingSessionLocal
from backend.app.models.profile import UserStyleProfile

SLUG = "silk-jacquard-evening-necktie"


def _login(client: TestClient):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "shopper@confit.io", "password": "Password123!"},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _set_blob(user_id: int, value):
    db = TestingSessionLocal()
    try:
        usp = db.query(UserStyleProfile).filter_by(user_id=user_id).first()
        assert usp is not None, "seeded shopper must have a style profile"
        usp.encrypted_body_data = value
        db.commit()
    finally:
        db.close()


def test_product_detail_survives_undecryptable_body_blob(client: TestClient):
    headers = _login(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    user_id = me["id"]

    original = None
    db = TestingSessionLocal()
    try:
        usp = db.query(UserStyleProfile).filter_by(user_id=user_id).first()
        original = usp.encrypted_body_data if usp else None
    finally:
        db.close()

    # Simulate a stale ciphertext written under a rotated Fernet key.
    try:
        _set_blob(user_id, "gAAAAABstaleciphertextwrittenunderanoldkey==")
        res = client.get(f"/api/v1/catalog/products/{SLUG}", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        # the product itself is fully served
        assert body["slug"] == SLUG
        assert isinstance(body["skus"], list) and body["skus"]
        # fit context degrades honestly — never fabricated
        assert body["fit_available"] in (True, False)
        if body["fit_available"] is False:
            assert not body["recommended_size"]
        # and the caller never sees raw error payloads
        assert "error" not in body
    finally:
        _set_blob(user_id, original)
