"""Saved wardrobe looks — /wardrobe/outfits (migration 0048).

Acceptance (Style List journey, step "save / revisit"):
* a recommendation can be saved and read back with the SAME item ids and
  photos resolved from the caller's wardrobe rows;
* the save is 201 only after persistence (GET returns it);
* ids that are not the caller's, do not exist, or are in the bin are
  rejected and reported — never stored, never leaked;
* a look made only of foreign ids is refused (422), not saved empty;
* role is derived from the STORED category, not the client's claim;
* provenance is preserved; a fallback can never be stored as AI-made;
* binning a garment afterwards hides it from the saved look and reports it;
* another user cannot read or delete the look (404, no existence oracle).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("setup_test_db")


def _register(client: TestClient) -> dict:
    email = f"wx_saved_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!", "full_name": "Saved Looks"})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _add_item(client: TestClient, headers: dict, **over) -> dict:
    payload = {
        "title": over.pop("title", "White Oxford Shirt"), "category": over.pop("category", "Tops"),
        "subcategory": over.pop("subcategory", "Oxford Shirt"), "color_name": over.pop("color_name", "White"),
        "color_hex": "#FFFFFF", "pattern": "Solid",
        "image_url": over.pop("image_url", f"https://cdn.example.com/{uuid.uuid4().hex}.jpg"),
        "occasions": ["Smart Casual"], "seasonality": "All-Season",
    }
    payload.update(over)
    res = client.post("/api/v1/wardrobe/items", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _closet(client: TestClient, headers: dict) -> dict:
    return {
        "top": _add_item(client, headers),
        "bottom": _add_item(client, headers, title="Navy Chinos", category="Bottoms", subcategory="Chinos", color_name="Navy"),
        "shoes": _add_item(client, headers, title="Brown Loafers", category="Footwear", subcategory="Loafers", color_name="Brown"),
    }


def _payload(closet: dict, **over) -> dict:
    body = {
        "title": "Smart Casual, evening",
        "occasion": "Smart Casual",
        "summary": "Crisp shirt, navy chinos, loafers.",
        "items": [
            {"wardrobe_item_id": closet["top"]["id"], "reason": "Clean base layer."},
            {"wardrobe_item_id": closet["bottom"]["id"], "reason": "Tonal contrast."},
            {"wardrobe_item_id": closet["shoes"]["id"], "reason": "Finishes the look."},
        ],
        "styling_notes": ["Roll the sleeves once."],
        "limitations": [],
        "missing_categories": [],
        "context": {"occasion": "Smart Casual", "time_of_day": "evening", "season": "autumn", "location": "Cairo"},
        "source": "watsonx",
        "ai_generated": True,
        "model_id": "ibm/granite-4-h-small",
        "prompt_version": "stylist-v1",
    }
    body.update(over)
    return body


def test_save_then_list_and_get_round_trip(client):
    h = _register(client)
    closet = _closet(client, h)

    res = client.post("/api/v1/wardrobe/outfits", json=_payload(closet), headers=h)
    assert res.status_code == 201, res.text
    saved = res.json()
    assert saved["id"] > 0
    assert [i["wardrobe_item_id"] for i in saved["items"]] == [closet["top"]["id"], closet["bottom"]["id"], closet["shoes"]["id"]]
    assert [i["role"] for i in saved["items"]] == ["top", "bottom", "footwear"]
    assert saved["items"][0]["image_url"] == closet["top"]["image_url"]  # photo from the stored row
    assert saved["is_complete"] is True
    assert saved["rejected_references"] == []
    assert saved["source"] == "watsonx" and saved["ai_generated"] is True
    assert saved["model_id"] == "ibm/granite-4-h-small" and saved["prompt_version"] == "stylist-v1"
    assert saved["context"]["time_of_day"] == "evening" and saved["context"]["location"] == "Cairo"

    listed = client.get("/api/v1/wardrobe/outfits", headers=h)
    assert listed.status_code == 200
    assert [o["id"] for o in listed.json()] == [saved["id"]]

    one = client.get(f"/api/v1/wardrobe/outfits/{saved['id']}", headers=h)
    assert one.status_code == 200
    assert one.json()["items"][2]["title"] == "Brown Loafers"
    assert one.json()["styling_notes"] == ["Roll the sleeves once."]


def test_foreign_and_unknown_ids_are_rejected_not_stored(client):
    owner, intruder = _register(client), _register(client)
    mine = _closet(client, owner)
    theirs = _add_item(client, intruder, title="Someone Else's Jacket", category="Outerwear", subcategory="Blazer")

    body = _payload(mine)
    body["items"].append({"wardrobe_item_id": theirs["id"], "reason": "stolen"})
    body["items"].append({"wardrobe_item_id": 99_999_999, "reason": "ghost"})
    res = client.post("/api/v1/wardrobe/outfits", json=body, headers=owner)
    assert res.status_code == 201, res.text
    saved = res.json()
    kept = {i["wardrobe_item_id"] for i in saved["items"]}
    assert theirs["id"] not in kept and 99_999_999 not in kept
    assert sorted(saved["rejected_references"]) == sorted([theirs["id"], 99_999_999])
    assert "Someone Else" not in res.text

    # Persisted state matches: re-reading shows only the owner's three pieces.
    again = client.get(f"/api/v1/wardrobe/outfits/{saved['id']}", headers=owner).json()
    assert {i["wardrobe_item_id"] for i in again["items"]} == {mine["top"]["id"], mine["bottom"]["id"], mine["shoes"]["id"]}


def test_look_made_only_of_foreign_ids_is_refused(client):
    owner, intruder = _register(client), _register(client)
    theirs = _closet(client, intruder)
    res = client.post("/api/v1/wardrobe/outfits", json=_payload(theirs), headers=owner)
    assert res.status_code == 422, res.text
    assert client.get("/api/v1/wardrobe/outfits", headers=owner).json() == []


def test_binned_item_is_rejected_at_save_and_hidden_afterwards(client):
    h = _register(client)
    closet = _closet(client, h)
    # Bin the shoes BEFORE saving → rejected at save time.
    assert client.delete(f"/api/v1/wardrobe/items/{closet['shoes']['id']}", headers=h).status_code in (200, 204)
    res = client.post("/api/v1/wardrobe/outfits", json=_payload(closet), headers=h)
    assert res.status_code == 201, res.text
    assert res.json()["rejected_references"] == [closet["shoes"]["id"]]
    assert res.json()["is_complete"] is False  # no footwear any more

    # Bin the chinos AFTER saving → hidden on read, counted, never a stale photo.
    outfit_id = res.json()["id"]
    assert client.delete(f"/api/v1/wardrobe/items/{closet['bottom']['id']}", headers=h).status_code in (200, 204)
    one = client.get(f"/api/v1/wardrobe/outfits/{outfit_id}", headers=h).json()
    assert [i["wardrobe_item_id"] for i in one["items"]] == [closet["top"]["id"]]
    assert one["dropped_item_count"] == 1
    assert one["is_complete"] is False


def test_role_comes_from_stored_category_and_fallback_is_never_ai(client):
    h = _register(client)
    closet = _closet(client, h)
    body = _payload(closet, source="deterministic_fallback", ai_generated=True, model_id="ibm/granite-4-h-small")
    res = client.post("/api/v1/wardrobe/outfits", json=body, headers=h)
    assert res.status_code == 201, res.text
    saved = res.json()
    # The client lied about ai_generated for a fallback → stored truthfully.
    assert saved["source"] == "deterministic_fallback"
    assert saved["ai_generated"] is False and saved["model_id"] is None
    # Roles are not something the client can set at all.
    assert [i["role"] for i in saved["items"]] == ["top", "bottom", "footwear"]


def test_other_user_cannot_read_or_delete_a_saved_look(client):
    owner, intruder = _register(client), _register(client)
    closet = _closet(client, owner)
    outfit_id = client.post("/api/v1/wardrobe/outfits", json=_payload(closet), headers=owner).json()["id"]

    assert client.get(f"/api/v1/wardrobe/outfits/{outfit_id}", headers=intruder).status_code == 404
    assert client.delete(f"/api/v1/wardrobe/outfits/{outfit_id}", headers=intruder).status_code == 404
    assert client.get("/api/v1/wardrobe/outfits", headers=intruder).json() == []
    # Still there for the owner, and the owner can delete it.
    assert client.get(f"/api/v1/wardrobe/outfits/{outfit_id}", headers=owner).status_code == 200
    assert client.delete(f"/api/v1/wardrobe/outfits/{outfit_id}", headers=owner).status_code == 204
    assert client.get(f"/api/v1/wardrobe/outfits/{outfit_id}", headers=owner).status_code == 404


def test_saved_outfits_require_auth_and_validate_shape(client):
    assert client.get("/api/v1/wardrobe/outfits").status_code == 401
    h = _register(client)
    res = client.post("/api/v1/wardrobe/outfits", json={"title": "x", "occasion": "Smart Casual", "items": [], "source": "watsonx", "ai_generated": True}, headers=h)
    assert res.status_code == 422


def test_watsonx_look_cannot_claim_a_foreign_model_id(client, monkeypatch):
    """Provenance integrity (NFR truthful provenance, found 2026-10-26 on the
    PostgreSQL rig): a look labelled ``source=watsonx`` may only carry the
    model identifier this deployment is configured to call. Anything else
    (``gpt-4o``, a typo, a withdrawn Granite id) is rejected — never stored and
    never badged as a Granite look."""
    from backend.app.core.config import settings

    h = _register(client)
    closet = _closet(client, h)

    res = client.post("/api/v1/wardrobe/outfits", json=_payload(closet, model_id="gpt-4o"), headers=h)
    assert res.status_code == 422
    assert "model attribution" in res.json()["error"]["message"]
    assert client.get("/api/v1/wardrobe/outfits", headers=h).json() == []

    # The configured reasoning model is accepted …
    res = client.post("/api/v1/wardrobe/outfits", json=_payload(closet, model_id=settings.WATSONX_REASONING_MODEL_ID), headers=h)
    assert res.status_code == 201

    # … and so is the reasoning *deployment* id when DoD routing is configured,
    # because the allow-list follows configuration rather than a hard-coded id.
    monkeypatch.setattr(settings, "WATSONX_REASONING_DEPLOYMENT_ID", "dep-1234")
    res = client.post("/api/v1/wardrobe/outfits", json=_payload(closet, model_id="dep-1234"), headers=h)
    assert res.status_code == 201

    # Fallback looks never carry a model id, whatever the client sends (unchanged behaviour).
    res = client.post("/api/v1/wardrobe/outfits", json=_payload(closet, source="deterministic_fallback", ai_generated=False, model_id="gpt-4o"), headers=h)
    assert res.status_code == 201 and res.json()["model_id"] is None
