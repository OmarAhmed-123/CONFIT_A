from fastapi.testclient import TestClient


def test_stylist_grounded_formal_wedding(client: TestClient):
    """Verifies that a formal wedding prompt returns complete, occasion-appropriate tailoring with exact text grounding."""
    res = client.post("/api/v1/stylist/chat", json={
        "prompt": "I need a formal wedding outfit with navy suit and green tie under 500",
        "occasion": "Formal & Wedding",
        "budget_limit": 500.0
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["recommendations"]) > 0

    primary_outfit = data["recommendations"][0]
    items = primary_outfit["items"]
    positions = [it["position"] for it in items]

    # Verify Slot Completeness
    assert "top" in positions or "outerwear" in positions
    assert "bottom" in positions
    assert "footwear" in positions

    # Verify no casual items in formal wedding look
    for it in items:
        title_lower = it["product_title"].lower()
        assert "sneaker" not in title_lower
        assert "denim" not in title_lower
        assert "t-shirt" not in title_lower

    # Verify Total Price matches sum of individual items
    computed_sum = sum(it["price"] for it in items)
    assert round(primary_outfit["total_price"], 2) == round(computed_sum, 2)


def test_stylist_prompt_diversity(client: TestClient):
    """Verifies that different prompt intents return distinct items rather than repeating fixed mock items."""
    res_formal = client.post("/api/v1/stylist/chat", json={
        "prompt": "Formal black tie gala dinner look",
        "occasion": "Formal & Wedding"
    })
    res_casual = client.post("/api/v1/stylist/chat", json={
        "prompt": "Casual weekend summer linen look",
        "occasion": "Casual Weekend"
    })

    assert res_formal.status_code == 200
    assert res_casual.status_code == 200

    formal_outfit = res_formal.json()["recommendations"][0]
    casual_outfit = res_casual.json()["recommendations"][0]

    formal_product_ids = {it["product_id"] for it in formal_outfit["items"]}
    casual_product_ids = {it["product_id"] for it in casual_outfit["items"]}

    # The formal outfit and casual outfit must have distinct product sets
    assert formal_product_ids != casual_product_ids
    assert formal_outfit["occasion"] != casual_outfit["occasion"]


def test_measurement_session_tryon_scaling(client: TestClient):
    """Verifies that biometric measurements apply scaling factors to try-on sessions."""
    # 1. Create try-on session directly in the repository — the HTTP creation
    # endpoint requires a render backend (covered by the 503 truthful-failure
    # tests); measurement scaling itself is a pure state operation.
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.repositories.tryon_repository import TryOnRepository

    db = TestingSessionLocal()
    try:
        repo = TryOnRepository(db)
        session = repo.create_tryon_session(
            product_id=1,
            input_user_image_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        )
        tryon_sess_id = session.id
    finally:
        db.close()

    # 2. Apply derived measurements
    apply_res = client.post(f"/api/v1/try-on/sessions/{tryon_sess_id}/apply-measurements", json={
        "height_cm": 182.0,
        "chest_cm": 102.0,
        "waist_cm": 84.0,
        "shoulder_cm": 48.0
    })
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    assert apply_data["status"] == "scaling_applied"
    assert apply_data["scaling_factor"] == round(182.0 / 175.0, 2)
