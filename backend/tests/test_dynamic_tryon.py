import pytest
from fastapi.testclient import TestClient


def test_dynamic_multi_garment_male_suit_tryon(client: TestClient):
    """Verifies multi-garment try-on with identity preservation for male suit ensemble."""
    res = client.post("/api/v1/try-on/multi-render", json={
        "product_ids": [1, 3, 4, 6, 8],  # Blazer, Oxford Shirt, Suit Trousers, Oxfords, Silk Tie
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "consent_retain_photo": False
    })
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "completed"
    assert len(data["applied_items"]) == 5
    assert data["fit_confidence_score"] >= 90
    assert "VTON-CERT-" in data["traceability_hash"]
    assert "CONFIT VTON Engine" in data["ai_disclosure"]

    positions = [it["position"] for it in data["applied_items"]]
    assert "upper_inner" in positions
    assert "upper_outer" in positions
    assert "lower" in positions
    assert "footwear" in positions
    assert "accessory_neck" in positions or "accessory" in positions

    assert "STRICT MANDATORY PRESERVATION" in data["dynamic_prompt_generated"]
    assert "NEGATIVE PROMPT" in data["dynamic_prompt_generated"]


def test_dynamic_multi_garment_female_dress_tryon(client: TestClient):
    """Verifies multi-garment try-on with dress slot override and accessories."""
    res = client.post("/api/v1/try-on/multi-render", json={
        "product_ids": [5, 7, 9],  # Silk Column Dress, Heeled Sandals, Evening Clutch
        "user_image_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600",
        "avatar_model_id": "avatar_hourglass_f",
        "gender_mode": "female",
        "consent_retain_photo": False
    })
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "completed"
    assert len(data["applied_items"]) >= 2
    positions = [it["position"] for it in data["applied_items"]]
    assert "dress" in positions or "dresses" in positions
    assert "footwear" in positions


def test_dynamic_animation_tryon_render(client: TestClient):
    """Verifies dynamic animation try-on prompt generation and keyframe motion sequence."""
    res = client.post("/api/v1/try-on/animation-render", json={
        "product_ids": [1, 3, 4, 6, 8],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "output_aspect": "9:16",
        "background_mode": "studio",
        "animation_style": "premium_realistic"
    })
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "completed"
    assert data["animation_style"] == "premium_realistic"
    assert data["output_aspect"] == "9:16"
    assert len(data["keyframes_sequence"]) == 5
    assert "VTON-ANIM-" in data["traceability_hash"]
    assert "CONFIT DYNAMIC ANIMATION TRY-ON SPECIFICATION" in data["dynamic_animation_prompt"]
    assert "IDENTITY PRESERVATION — MANDATORY" in data["dynamic_animation_prompt"]
    assert "PHYSICAL REALISM & FOOTWEAR TRANSFER" in data["dynamic_animation_prompt"]


def test_tryon_session_rest_lifecycle(client: TestClient):
    """Tests the full REST try-on session lifecycle: create, apply item, remove item, reorder, query, purge."""
    # 1. Create Session
    sess_res = client.post("/api/v1/try-on/sessions", json={
        "product_id": 1,
        "avatar_model_id": "avatar_athletic_m"
    })
    assert sess_res.status_code == 201
    sess_data = sess_res.json()
    session_id = sess_data["session_id"]

    # 2. Apply Item to Session
    apply_res = client.post(f"/api/v1/try-on/sessions/{session_id}/apply-item", json={
        "product_id": 3,  # Oxford shirt
        "slot": "upper_inner"
    })
    assert apply_res.status_code == 200
    applied_data = apply_res.json()
    assert len(applied_data["applied_items"]) >= 1

    # 3. Reorder session items
    reorder_res = client.post(f"/api/v1/try-on/sessions/{session_id}/reorder", json={
        "slot_order": ["upper_inner", "upper_outer", "lower", "footwear", "accessory"]
    })
    assert reorder_res.status_code == 200

    # 4. Query session details
    get_res = client.get(f"/api/v1/try-on/sessions/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["session_id"] == session_id

    # 5. Remove item from session
    remove_res = client.post(f"/api/v1/try-on/sessions/{session_id}/remove-item", json={
        "product_id": 3
    })
    assert remove_res.status_code == 200

    # 6. Purge session (GDPR Article 17)
    purge_res = client.delete(f"/api/v1/try-on/sessions/{session_id}/purge")
    assert purge_res.status_code == 200
    assert purge_res.json()["status"] == "purged"


def test_tryon_gdpr_purge_task():
    """Verifies the background GDPR privacy cleanup task purges expired unconsented media assets."""
    from backend.app.workers.tasks import purge_expired_sessions_task
    res = purge_expired_sessions_task()
    assert "purged_count" in res


def test_tryon_image_validation_endpoint(client: TestClient):
    """Verifies that uploaded user photos are validated for framing and quality."""
    res = client.post("/api/v1/try-on/validate-image", json={
        "image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert "body_framing" in data
    assert len(data["suggestions"]) > 0
