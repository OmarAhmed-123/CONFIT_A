"""Wardrobe grounding — FR-004, SC-002, STY-03.

``include_wardrobe_items`` used to be accepted and silently ignored. These tests
pin that it now changes the output: with it on, a signed-in shopper's owned pieces
appear as pairings and in the response; with it off, or for a guest, they do not.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core.config import settings
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def no_text_provider(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDERS", "none")


def _register(client: TestClient) -> dict:
    email = f"wardrobe_{uuid.uuid4().hex[:10]}@confit.io"
    reg = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "Wardrobe Shopper",
    })
    assert reg.status_code == 201, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}", "_email": email}


def _add_wardrobe_piece(email: str, *, title: str, category: str, color_name: str, color_hex: str) -> int:
    db = TestingSessionLocal()
    try:
        user_id = db.execute(text("select id from users where email = :e"), {"e": email}).scalar()
        db.execute(text(
            "insert into wardrobe_items (user_id, title, category, color_name, color_hex, "
            "pattern, brand_name, image_url, ai_tags, occasions, secondary_colors, seasonality, "
            "wear_frequency, wear_count, is_favorite, processing_status, created_at) values "
            "(:u, :t, :c, :cn, :ch, 'Solid', 'Own Collection', 'https://example.com/x.jpg', "
            "'[]', '[]', '[]', 'All-Season', 'regular', 0, :fav, 'ready', CURRENT_TIMESTAMP)"
        ), {"u": user_id, "t": title, "c": category, "cn": color_name, "ch": color_hex, "fav": False})
        db.commit()
        return db.execute(text(
            "select id from wardrobe_items where user_id = :u and title = :t"
        ), {"u": user_id, "t": title}).scalar()
    finally:
        db.close()


def _post(client, headers, **extra):
    body = {"prompt": "a smart casual dinner look", **extra}
    res = client.post("/api/v1/stylist/chat", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _pairings(data):
    return [p for o in data["recommendations"] for p in (o.get("wardrobe_pairings") or [])]


def test_flag_on_with_owned_pieces_produces_pairings(client: TestClient, no_text_provider):
    headers = _register(client)
    # A navy top-layer piece is a classic partner for the catalogue's neutral looks.
    _add_wardrobe_piece(headers["_email"], title="Owned Navy Overshirt", category="Outerwear",
                        color_name="Navy", color_hex="#1B1F3B")
    headers = {"Authorization": headers["Authorization"]}

    data = _post(client, headers, include_wardrobe_items=True)
    intent = data["intent_detected"]
    assert intent["wardrobe"]["requested"] is True
    assert intent["wardrobe"]["used"] is True
    assert intent["wardrobe"]["owned_items_considered"] == 1
    pairings = _pairings(data)
    # The pairing must reference the owned item by title, and must not duplicate a
    # category the look already contains.
    assert pairings, "an owned piece that harmonises must appear as a pairing"
    for p in pairings:
        assert p["title"] == "Owned Navy Overshirt"
        assert p["category"] == "Outerwear"
        assert p["pairs_with"], "every pairing states what it pairs with"


def test_flag_off_never_uses_the_wardrobe(client: TestClient, no_text_provider):
    headers = _register(client)
    _add_wardrobe_piece(headers["_email"], title="Owned Navy Overshirt", category="Outerwear",
                        color_name="Navy", color_hex="#1B1F3B")
    headers = {"Authorization": headers["Authorization"]}

    data = _post(client, headers, include_wardrobe_items=False)
    assert data["intent_detected"]["wardrobe"]["requested"] is False
    assert data["intent_detected"]["wardrobe"]["used"] is False
    assert _pairings(data) == []
    for outfit in data["recommendations"]:
        assert "wardrobe_pairings" not in outfit or outfit["wardrobe_pairings"] is None


def test_toggling_the_flag_changes_the_output(client: TestClient, no_text_provider):
    headers = _register(client)
    _add_wardrobe_piece(headers["_email"], title="Owned Navy Overshirt", category="Outerwear",
                        color_name="Navy", color_hex="#1B1F3B")
    headers = {"Authorization": headers["Authorization"]}
    on = _post(client, headers, include_wardrobe_items=True)
    off = _post(client, headers, include_wardrobe_items=False)
    assert _pairings(on) != _pairings(off)


def test_guest_asking_for_wardrobe_is_told_to_sign_in(client: TestClient, no_text_provider):
    data = _post(client, {}, include_wardrobe_items=True)
    wardrobe = data["intent_detected"]["wardrobe"]
    assert wardrobe["used"] is False
    assert wardrobe["reason"] and "sign in" in wardrobe["reason"].lower()
    assert _pairings(data) == []


def test_signed_in_user_with_empty_wardrobe_is_told_so(client: TestClient, no_text_provider):
    headers = _register(client)
    data = _post(client, {"Authorization": headers["Authorization"]}, include_wardrobe_items=True)
    wardrobe = data["intent_detected"]["wardrobe"]
    assert wardrobe["used"] is False
    assert "no items" in wardrobe["reason"].lower()


def test_pairing_never_duplicates_a_category_already_in_the_look():
    from backend.app.services.stylist_service import _wardrobe_pairings

    class _Piece:
        def __init__(self, id, title, category, color_name, color_hex):
            self.id, self.title, self.category = id, title, category
            self.color_name, self.color_hex = color_name, color_hex

    look = {"items": [
        {"position": "outerwear", "color_family": "navy"},
        {"position": "top", "color_family": "white"},
        {"position": "bottom", "color_family": "beige"},
    ]}
    owned = [
        _Piece(1, "Second Blazer", "Outerwear", "Navy", "#1B1F3B"),   # category already in look
        _Piece(2, "Olive Field Jacket", "Outerwear", "Olive", "#6E6E32"),  # category already in look
        _Piece(3, "Grey Knit Belt", "Accessories", "Grey", "#808080"),
    ]
    pairings = _wardrobe_pairings(look, owned)
    titles = [p["title"] for p in pairings]
    assert "Second Blazer" not in titles
    assert "Olive Field Jacket" not in titles
    assert "Grey Knit Belt" in titles
