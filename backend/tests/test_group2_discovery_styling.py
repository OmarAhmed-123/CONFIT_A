"""GROUP 2 regression tests: honest scoring, budget enforcement, ambiguity,
availability gating, and outfit authorization (IDOR)."""
import pytest
from fastapi.testclient import TestClient

from backend.app.services.styling_engine import StylingEngine
from backend.app.services.styling.composer import OutfitComposer


# ---------- Scoring integrity (deterministic, discriminating) ----------

COHERENT = [
    {"position": "outerwear", "product_title": "Tailored Wool Blazer", "slot_type": "formal_outer",
     "color_family": "Navy Blue", "occasion_tags": ["work", "business"], "style_tags": ["tailored"], "price": 289.0},
    {"position": "top", "product_title": "Poplin Shirt", "slot_type": "formal_shirt",
     "color_family": "Optic White", "occasion_tags": ["work"], "style_tags": ["tailored"], "price": 95.0},
    {"position": "bottom", "product_title": "Wool Trousers", "slot_type": "formal_bottom",
     "color_family": "Navy Blue", "occasion_tags": ["work"], "style_tags": ["tailored"], "price": 165.0},
    {"position": "footwear", "product_title": "Oxford Shoes", "slot_type": "formal_shoes",
     "color_family": "Obsidian Black", "occasion_tags": ["work", "formal"], "style_tags": ["formal"], "price": 245.0},
]

CLASHING = [
    {"position": "dress", "product_title": "Silk Gown", "slot_type": "dress",
     "color_family": "Champagne Gold", "occasion_tags": ["gala"], "style_tags": ["evening"], "price": 340.0},
    {"position": "bottom", "product_title": "Cargo Joggers", "slot_type": "casual_bottom",
     "color_family": "Neon Green", "occasion_tags": ["gym"], "style_tags": ["streetwear"], "price": 80.0},
]


def test_compatibility_discriminates_good_vs_bad():
    good = StylingEngine.calculate_compatibility(COHERENT, target_occasion="Work & Business")
    bad = StylingEngine.calculate_compatibility(CLASHING, target_occasion="Casual")
    assert good["compatibility_score"] > bad["compatibility_score"]
    # No artificial floor: a clashing/off-occasion combo must be able to score low.
    assert bad["compatibility_score"] < 70


def test_compatibility_empty_is_zero():
    res = StylingEngine.calculate_compatibility([], target_occasion="Casual")
    assert res["compatibility_score"] == 0
    assert res["is_complete_outfit"] is False


def test_scoring_is_deterministic():
    a = StylingEngine.calculate_compatibility(COHERENT, target_occasion="Work & Business")
    b = StylingEngine.calculate_compatibility(COHERENT, target_occasion="Work & Business")
    assert a["compatibility_score"] == b["compatibility_score"]


# ---------- Intent parsing: budget, occasion, ambiguity ----------

def test_intent_budget_explicit_vs_default():
    c = OutfitComposer()
    stated = c.parse_intent(prompt="work outfit under $600", budget_hint=None)
    assert stated["budget_explicit"] is True
    assert stated["detected_budget"] == 600.0
    defaulted = c.parse_intent(prompt="something nice", budget_hint=None)
    assert defaulted["budget_explicit"] is False


def test_intent_flags_gibberish_as_ambiguous():
    c = OutfitComposer()
    assert c.parse_intent(prompt="asdfqwer zzz")["is_ambiguous"] is True
    assert c.parse_intent(prompt="")["is_ambiguous"] is True
    assert c.parse_intent(prompt="formal wedding outfit")["is_ambiguous"] is False


# ---------- API: authorization / IDOR / contract / guest ----------

def _register(client, email):
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "T U"})
    assert r.status_code in (200, 201)
    return r.json()["access_token"]


def _csrf(client):
    return {"X-CSRF-Token": client.cookies.get("confit_csrf")}


def test_outfit_ownership_and_guest_gating(client: TestClient):
    tok_a = _register(client, "g2_a@confit.io")
    headers_a = {**_csrf(client), "Authorization": f"Bearer {tok_a}"}

    # Save with the canonical product_ids contract.
    save = client.post("/api/v1/outfits", headers=headers_a,
                       json={"title": "A look", "occasion": "Work & Business", "product_ids": [1, 3, 4]})
    assert save.status_code == 201, save.text
    outfit_id = save.json()["id"]

    # A second user must NOT be able to read/patch/delete/share it.
    client.cookies.clear()
    tok_b = _register(client, "g2_b@confit.io")
    hb = {**_csrf(client), "Authorization": f"Bearer {tok_b}"}
    assert client.get(f"/api/v1/outfits/{outfit_id}", headers=hb).status_code == 404
    assert client.patch(f"/api/v1/outfits/{outfit_id}", headers=hb, json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/v1/outfits/{outfit_id}", headers=hb).status_code == 404
    assert client.post(f"/api/v1/outfits/{outfit_id}/share", headers=hb).status_code == 404

    # Guests must not access My Looks or save.
    client.cookies.clear()
    assert client.get("/api/v1/outfits/my-looks").status_code == 401
    assert client.post("/api/v1/outfits", json={"title": "g", "occasion": "c", "product_ids": [1]}).status_code == 401


def test_outfit_mass_assignment_blocked(client: TestClient):
    tok = _register(client, "g2_c@confit.io")
    h = {**_csrf(client), "Authorization": f"Bearer {tok}"}
    save = client.post("/api/v1/outfits", headers=h,
                       json={"title": "Mine", "occasion": "Casual", "product_ids": [1, 3]})
    oid = save.json()["id"]
    original_score = save.json()["compatibility_score"]
    # Attempt to overwrite protected fields — must be ignored.
    r = client.patch(f"/api/v1/outfits/{oid}", headers=h,
                     json={"user_id": 999, "compatibility_score": 1, "is_saved": False, "title": "Renamed"})
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"
    assert r.json()["compatibility_score"] == original_score  # unchanged


def test_outfit_delete_roundtrip(client: TestClient):
    tok = _register(client, "g2_d@confit.io")
    h = {**_csrf(client), "Authorization": f"Bearer {tok}"}
    save = client.post("/api/v1/outfits", headers=h,
                       json={"title": "ToDelete", "occasion": "Casual", "product_ids": [1]})
    oid = save.json()["id"]
    assert client.delete(f"/api/v1/outfits/{oid}", headers=h).status_code == 200
    assert client.get(f"/api/v1/outfits/{oid}", headers=h).status_code == 404


# ---------- Budget hard constraint (BRD 2.1D / 2.15) ----------

def test_budget_enforced_when_feasible_and_complete():
    """A stated budget must be satisfied with a COMPLETE look when the catalog
    has a feasible combination (cheapest complete look <= budget)."""
    from backend.app.core.database import SessionLocal
    from backend.app.repositories.catalog_repository import CatalogRepository
    from backend.app.services.styling.composer import OutfitComposer
    db = SessionLocal()
    try:
        prods = CatalogRepository(db).filter_products(limit=100)
        c = OutfitComposer()
        intent = c.parse_intent(prompt="smart casual work outfit under $600", budget_hint=None)
        assert intent["budget_explicit"] is True
        outfits = c.compose_outfits(available_products=prods, intent=intent, max_outfits=2)
        assert outfits, "expected at least one outfit"
        # At least one recommendation must satisfy the budget AND be complete.
        assert any(o["within_budget"] and o["is_complete"] and o["total_price"] <= 600.0 for o in outfits)
    finally:
        db.close()


def test_budget_impossible_reports_minimum_honestly():
    """An infeasible budget must NOT be silently met; it must return the closest
    achievable complete look and mark within_budget=False with an honest note."""
    from backend.app.core.database import SessionLocal
    from backend.app.repositories.catalog_repository import CatalogRepository
    from backend.app.services.styling.composer import OutfitComposer
    db = SessionLocal()
    try:
        prods = CatalogRepository(db).filter_products(limit=100)
        c = OutfitComposer()
        intent = c.parse_intent(prompt="dinner outfit under $100", budget_hint=None)
        outfits = c.compose_outfits(available_products=prods, intent=intent, max_outfits=2)
        assert outfits
        for o in outfits:
            assert o["within_budget"] is False
            assert o["is_complete"] is True  # never fabricate an incomplete 'cheap' look
            assert "minimum complete look" in (o["budget_note"] or "").lower()
    finally:
        db.close()
