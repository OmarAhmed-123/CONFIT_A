"""Group 1 security-hardening regression tests — continuation pass.

Covers the fixes applied in the continuation phase:
  §2  wardrobe: no anonymous user-#1 fallback, IDOR between two users
  §3  outfits:  auth + ownership on read / patch / delete / share / add-to-cart
  §4  /api/v1/diagnostic: anonymous 401, non-admin 403, admin 200 (non-prod),
      production 404, and no user emails / DB URLs / tracebacks in the payload
  §5  seed: refuses to run under ENVIRONMENT=production
  §10 mood-board real upload: multipart validation + persistence + ownership
  §30 real persistence: write → commit → NEW session → read same value
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.tests.conftest import TestingSessionLocal


def _unique_email() -> str:
    return f"g1sec_{uuid.uuid4().hex[:8]}@confit-testing.example.com"


def _register_and_token(email: str) -> str:
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={
        "email": email,
        "password": "StrongPassw0rd!",
        "full_name": "G1 Security User",
    })
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# §2 — Wardrobe: anonymous fallback removed
# =============================================================================
def test_wardrobe_list_requires_auth_anonymous_401():
    fresh = TestClient(app)
    assert fresh.get("/api/v1/wardrobe/items").status_code == 401


def test_wardrobe_single_item_requires_auth_anonymous_401():
    fresh = TestClient(app)
    assert fresh.get("/api/v1/wardrobe/items/1").status_code == 401


def test_wardrobe_gap_analysis_requires_auth_anonymous_401():
    fresh = TestClient(app)
    assert fresh.get("/api/v1/wardrobe/gap-analysis").status_code == 401
    assert fresh.post("/api/v1/wardrobe/gap-analysis").status_code == 401


def test_wardrobe_cross_user_item_is_404_not_leaked():
    token_a = _register_and_token(_unique_email())
    token_b = _register_and_token(_unique_email())
    client = TestClient(app)

    create = client.post("/api/v1/wardrobe/items", headers=_auth(token_a), json={
        "title": "A's Silk Scarf", "category": "Accessories",
        "color_name": "Ivory", "image_url": "https://cdn.example.com/scarf.jpg",
    })
    assert create.status_code == 201, create.text
    item_id = create.json()["id"]

    # B must NOT read A's item — 404 (no existence oracle)
    res = client.get(f"/api/v1/wardrobe/items/{item_id}", headers=_auth(token_b))
    assert res.status_code == 404

    # B must NOT update or delete A's item
    assert client.patch(f"/api/v1/wardrobe/items/{item_id}", headers=_auth(token_b),
                        json={"title": "hijacked"}).status_code == 404
    assert client.delete(f"/api/v1/wardrobe/items/{item_id}", headers=_auth(token_b)).status_code == 404

    # B's list must not contain A's item
    lst = client.get("/api/v1/wardrobe/items", headers=_auth(token_b))
    assert res_list_ids(lst) == [] or item_id not in res_list_ids(lst)


def res_list_ids(resp):
    return [it["id"] for it in resp.json()]


# =============================================================================
# §3 — Outfits: ownership on every user-owned operation
# =============================================================================
def _create_outfit(token: str) -> int:
    client = TestClient(app)
    # sku ids 1..n exist in the seeded test catalogue
    r = client.post("/api/v1/outfits", headers=_auth(token), json={
        "title": "Evening Look", "occasion": "Formal", "product_sku_ids": [1, 2],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_outfits_list_requires_auth_anonymous_401():
    fresh = TestClient(app)
    assert fresh.get("/api/v1/outfits").status_code == 401
    assert fresh.get("/api/v1/outfits/my-looks").status_code == 401


def test_outfits_save_requires_auth_anonymous_401():
    fresh = TestClient(app)
    assert fresh.post("/api/v1/outfits", json={
        "title": "x", "occasion": "Casual", "product_sku_ids": [1],
    }).status_code == 401


def test_outfits_anonymous_cannot_mutate_by_id():
    fresh = TestClient(app)
    assert fresh.patch("/api/v1/outfits/1", json={"title": "h"}).status_code == 401
    assert fresh.delete("/api/v1/outfits/1").status_code == 401
    assert fresh.post("/api/v1/outfits/1/share").status_code == 401
    assert fresh.post("/api/v1/outfits/1/add-to-cart").status_code == 401


def test_outfit_cross_user_read_patch_delete_share_cart_all_rejected():
    token_a = _register_and_token(_unique_email())
    token_b = _register_and_token(_unique_email())
    outfit_id = _create_outfit(token_a)
    client = TestClient(app)

    assert client.get(f"/api/v1/outfits/{outfit_id}", headers=_auth(token_b)).status_code == 404
    assert client.patch(f"/api/v1/outfits/{outfit_id}", headers=_auth(token_b),
                        json={"title": "stolen"}).status_code == 404
    assert client.delete(f"/api/v1/outfits/{outfit_id}", headers=_auth(token_b)).status_code == 404
    assert client.post(f"/api/v1/outfits/{outfit_id}/share", headers=_auth(token_b)).status_code == 404
    assert client.post(f"/api/v1/outfits/{outfit_id}/add-to-cart", headers=_auth(token_b)).status_code == 404

    # And the owner still sees it intact (nothing was mutated by B)
    mine = client.get(f"/api/v1/outfits/{outfit_id}", headers=_auth(token_a))
    assert mine.status_code == 200
    assert mine.json()["title"] == "Evening Look"


def test_outfit_owner_full_lifecycle_works():
    token = _register_and_token(_unique_email())
    client = TestClient(app)
    outfit_id = _create_outfit(token)

    patched = client.patch(f"/api/v1/outfits/{outfit_id}", headers=_auth(token),
                           json={"title": "Renamed Look"})
    assert patched.status_code == 200

    share = client.post(f"/api/v1/outfits/{outfit_id}/share", headers=_auth(token))
    assert share.status_code == 200
    assert share.json()["share_token"].startswith("look_")

    deleted = client.delete(f"/api/v1/outfits/{outfit_id}", headers=_auth(token))
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/outfits/{outfit_id}", headers=_auth(token)).status_code == 404


# =============================================================================
# §4 — Diagnostic endpoint lockdown
# =============================================================================
def test_diagnostic_anonymous_401():
    fresh = TestClient(app)
    assert fresh.get("/api/v1/diagnostic").status_code == 401


def test_diagnostic_non_admin_403():
    token = _register_and_token(_unique_email())
    res = TestClient(app).get("/api/v1/diagnostic", headers=_auth(token))
    assert res.status_code == 403


def test_diagnostic_admin_allowed_and_leaks_nothing_sensitive(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)
    db = TestingSessionLocal()
    try:
        from backend.app.models.user import User, UserRole
        admin = db.query(User).filter(User.email == "admin@confit.io").first()
        assert admin is not None, "seeded admin should exist in the dev test DB"
    finally:
        db.close()
    login = TestClient(app).post("/api/v1/auth/login", json={
        "email": "admin@confit.io", "password": "Password123!",
    })
    assert login.status_code == 200, login.text
    res = TestClient(app).get("/api/v1/diagnostic", headers=_auth(login.json()["access_token"]))
    assert res.status_code == 200, res.text
    body = res.json()
    assert "users" not in body              # no per-user identity list
    assert "db_engine" not in body          # no DB URL/credentials
    assert "traceback" not in body          # no raw tracebacks
    assert body["database_reachable"] is True
    assert isinstance(body["users_count"], int)


def test_diagnostic_disabled_in_production_even_for_admin(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    login = TestClient(app).post("/api/v1/auth/login", json={
        "email": "admin@confit.io", "password": "Password123!",
    })
    token = login.json()["access_token"]
    res = TestClient(app).get("/api/v1/diagnostic", headers=_auth(token))
    assert res.status_code == 404


# =============================================================================
# §5 — Seed refuses production
# =============================================================================
def test_seed_database_refuses_production(monkeypatch):
    from backend.app.seed_data import seed_database
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    with pytest.raises(RuntimeError, match="production"):
        seed_database()


# =============================================================================
# §10 — Mood-board real upload flow
# =============================================================================
def _make_board(token: str) -> int:
    r = TestClient(app).post("/api/v1/me/mood-boards", headers=_auth(token),
                             json={"title": "Inspo", "description": None})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_mood_board_upload_real_file_then_attach_and_serve():
    token = _register_and_token(_unique_email())
    client = TestClient(app)
    board_id = _make_board(token)

    # Minimal valid PNG (89-byte header + IHDR stub) — content-type whitelist
    # is what the endpoint validates; bytes are persisted verbatim.
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    up = client.post(
        f"/api/v1/me/mood-boards/{board_id}/upload",
        headers=_auth(token),
        files={"file": ("inspo.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert up.status_code == 201, up.text
    payload = up.json()
    assert payload["upload_id"].startswith(f"moodboards/u")
    assert payload["size"] == len(png_bytes)

    # File really persisted on disk under the configured storage dir
    stored = os.path.join(os.path.abspath(settings.STORAGE_LOCAL_DIR), payload["upload_id"])
    assert os.path.isfile(stored)
    assert open(stored, "rb").read() == png_bytes

    # Attach it as a mood-board item
    attach = client.post(f"/api/v1/me/mood-boards/{board_id}/items", headers=_auth(token), json={
        "kind": "upload", "payload": {"upload_id": payload["upload_id"], "url": payload["url"]},
    })
    assert attach.status_code == 201, attach.text
    items = attach.json()["items"]
    assert any(it["payload"].get("upload_id") == payload["upload_id"] for it in items)


def test_mood_board_upload_rejects_bad_content_type_and_oversize():
    token = _register_and_token(_unique_email())
    client = TestClient(app)
    board_id = _make_board(token)

    bad = client.post(
        f"/api/v1/me/mood-boards/{board_id}/upload",
        headers=_auth(token),
        files={"file": ("evil.exe", io.BytesIO(b"MZ" + b"\x00" * 32), "application/octet-stream")},
    )
    assert bad.status_code in (400, 422)

    big = client.post(
        f"/api/v1/me/mood-boards/{board_id}/upload",
        headers=_auth(token),
        files={"file": ("big.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 1)), "image/png")},
    )
    assert big.status_code in (400, 422)


def test_mood_board_upload_cross_user_and_unauthenticated_rejected():
    token_a = _register_and_token(_unique_email())
    token_b = _register_and_token(_unique_email())
    client = TestClient(app)
    board_id = _make_board(token_a)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    assert TestClient(app).post(
        f"/api/v1/me/mood-boards/{board_id}/upload",
        files={"file": ("x.png", io.BytesIO(png), "image/png")},
    ).status_code == 401

    assert client.post(
        f"/api/v1/me/mood-boards/{board_id}/upload",
        headers=_auth(token_b),
        files={"file": ("x.png", io.BytesIO(png), "image/png")},
    ).status_code in (403, 404)


def test_mood_board_item_rejects_forged_upload_reference():
    token = _register_and_token(_unique_email())
    client = TestClient(app)
    board_id = _make_board(token)
    # A plausible-looking but nonexistent/forged key must be rejected
    res = client.post(f"/api/v1/me/mood-boards/{board_id}/items", headers=_auth(token), json={
        "kind": "upload", "payload": {"upload_id": "moodboards/u1/b1/../../etc/passwd"},
    })
    assert res.status_code in (400, 422)


# =============================================================================
# §30 — Real persistence across sessions (not same-session ORM state)
# =============================================================================
def test_profile_persists_across_fresh_db_sessions():
    token = _register_and_token(_unique_email())
    client = TestClient(app)
    r = client.post("/api/v1/profile/onboarding-quiz", headers=_auth(token), json={
        "style_archetypes": ["Minimalist"], "preferred_colors": ["Navy"],
        "budget_monthly_max": 777,
    })
    assert r.status_code in (200, 201), r.text

    # Prove real persistence: open a brand-new ENGINE + session against the
    # same test database file — no shared identity map, no in-flight ORM
    # state. If the value wasn't committed to disk, it won't be here.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.models.profile import UserStyleProfile
    from backend.tests.conftest import TEST_DB_URL
    fresh_engine = create_engine(
        TEST_DB_URL.replace("sqlite:///./", "sqlite:///"),
        connect_args={"check_same_thread": False},
    )
    FreshSession = sessionmaker(autocommit=False, autoflush=False, bind=fresh_engine)
    fresh_session = FreshSession()
    try:
        profiles = fresh_session.query(UserStyleProfile).all()
        ours = None
        for p in profiles:
            if "Minimalist" in (p.style_archetypes or "") and p.budget_monthly_max == 777:
                ours = p
        assert ours is not None, "profile must exist in a fresh DB session"
        assert "Minimalist" in ours.style_archetypes
        assert "Navy" in ours.preferred_colors
        assert ours.budget_monthly_max == 777
    finally:
        fresh_session.close()
