"""G4 gap analysis — data-driven unlock estimates (BRD PR3, G-GAPCOUNT).

The "Unlocks +N New Outfits" badge used to be a hardcoded 3/4/5 constant
shown identically to every user. These tests pin the new contract: the
number is a deterministic function of the customer's READY items, the
source counts ship in the payload (``owned_counts``), and an empty wardrobe
reports 0 with an honest starter rationale instead of an invented number.
"""
import uuid

from fastapi.testclient import TestClient


def _register(client: TestClient) -> dict:
    email = f"gap_e2e_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "Gap E2E",
    })
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _add(client: TestClient, headers: dict, category: str, color: str = "Black") -> dict:
    res = client.post("/api/v1/wardrobe/items", headers=headers, json={
        "title": f"Fixture {category}",
        "category": category,
        "color_name": color,
        "image_url": "https://images.unsplash.com/photo-gap-fixture",
    })
    assert res.status_code == 201, res.text
    return res.json()


def _gaps(client: TestClient, headers: dict) -> dict:
    res = client.get("/api/v1/wardrobe/gap-analysis", headers=headers)
    assert res.status_code == 200, res.text
    return {g["missing_category"]: g for g in res.json()}


class TestUnlockEstimate:
    def test_empty_wardrobe_reports_zero_unlocks(self, client):
        """No core pieces -> 0, and the rationale must not claim a number."""
        headers = _register(client)
        gaps = _gaps(client, headers)
        assert set(gaps) == {"Tops", "Bottoms", "Outerwear", "Footwear", "Accessories"}
        for cat, gap in gaps.items():
            assert gap["unlocks_outfit_count"] == 0, cat
            assert gap["owned_counts"] == {}
            assert "starter staple" in gap["rationale"].lower(), cat

    def test_core_gap_pairs_with_other_core_positions(self, client):
        """2 bottoms + 2 shoes, no tops -> each new top completes 4 pairings."""
        headers = _register(client)
        _add(client, headers, "Bottoms", "Navy")
        _add(client, headers, "Bottoms", "Beige")
        _add(client, headers, "Footwear", "White")
        _add(client, headers, "Footwear", "Black")

        gaps = _gaps(client, headers)
        assert "Tops" in gaps
        assert gaps["Tops"]["unlocks_outfit_count"] == 2 * 2  # bottoms x footwear
        # Source data ships with the claim:
        assert gaps["Tops"]["owned_counts"] == {"Bottoms": 2, "Footwear": 2}
        assert "2 bottoms" in gaps["Tops"]["rationale"]
        assert "2 footwear" in gaps["Tops"]["rationale"]

    def test_layering_gap_dresses_core_combinations(self, client):
        """3 tops + 2 bottoms + 1 shoe -> a new coat dresses 3*2*1 = 6 combos."""
        headers = _register(client)
        for _ in range(3):
            _add(client, headers, "Tops")
        for _ in range(2):
            _add(client, headers, "Bottoms")
        _add(client, headers, "Footwear")

        gaps = _gaps(client, headers)
        # Tops(3>=2) and Bottoms(2>=2) and Footwear(1>=1) are covered:
        assert set(gaps) == {"Outerwear", "Accessories"}
        assert gaps["Outerwear"]["unlocks_outfit_count"] == 6
        assert gaps["Accessories"]["unlocks_outfit_count"] == 6

    def test_estimate_is_capped(self, client):
        """10x10x10 owned -> the badge caps at 12, never marketing inflation."""
        headers = _register(client)
        for _ in range(10):
            _add(client, headers, "Tops")
            _add(client, headers, "Bottoms")
            _add(client, headers, "Footwear")

        gaps = _gaps(client, headers)
        # All core positions are covered; the two layering positions (own 0,
        # min 1) remain gaps.
        assert set(gaps) == {"Outerwear", "Accessories"}
        assert gaps["Outerwear"]["unlocks_outfit_count"] == 12
        assert gaps["Accessories"]["unlocks_outfit_count"] == 12
        # Per-category cap: min(10,5) per position -> 125 capped to 12,
        # never the raw 1000.

    def test_failed_or_processing_items_do_not_count(self, client):
        """Only READY items are wardrobe coverage — a stuck upload cannot
        suppress a genuine gap (and cannot inflate the estimate)."""
        from sqlalchemy import text
        from backend.tests.conftest import TestingSessionLocal

        headers = _register(client)
        ready = _add(client, headers, "Tops")
        # Force the item into 'processing' — it must stop counting.
        res = client.get("/api/v1/wardrobe/items", headers=headers).json()
        assert res[0]["id"] == ready["id"]
        db = TestingSessionLocal()
        try:
            db.execute(
                text("update wardrobe_items set processing_status = 'processing' where id = :i"),
                {"i": ready["id"]},
            )
            db.commit()
        finally:
            db.close()

        gaps = _gaps(client, headers)
        assert gaps["Tops"]["owned_counts"].get("Tops", 0) == 0
        assert gaps["Tops"]["unlocks_outfit_count"] == 0
