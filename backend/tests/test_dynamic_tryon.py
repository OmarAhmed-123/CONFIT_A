from fastapi.testclient import TestClient


def test_dynamic_multi_garment_male_suit_tryon(client: TestClient):
    """D1/A7 guard: multi-render with no GPU worker must fail truthfully (503),
    never returning a static asset or the input photo as the dressed result."""
    res = client.post("/api/v1/try-on/multi-render", json={
        "product_ids": [1, 3, 4, 6, 8],  # Blazer, Oxford Shirt, Suit Trousers, Oxfords, Silk Tie
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "consent_retain_photo": False
    })
    assert res.status_code == 503
    body = res.json()
    assert body["error"]["code"] == "VTON_ENGINE_UNAVAILABLE"


def test_dynamic_multi_garment_female_dress_tryon(client: TestClient):
    """D1/A7 guard: dress multi-render also fails truthfully without a worker."""
    res = client.post("/api/v1/try-on/multi-render", json={
        "product_ids": [5, 7, 9],  # Silk Column Dress, Heeled Sandals, Evening Clutch
        "user_image_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600",
        "avatar_model_id": "avatar_hourglass_f",
        "gender_mode": "female",
        "consent_retain_photo": False
    })
    assert res.status_code == 503
    body = res.json()
    assert body["error"]["code"] == "VTON_ENGINE_UNAVAILABLE"


def test_dynamic_animation_tryon_render(client: TestClient):
    """D1/A7 guard: animation render must not fabricate keyframes from static
    assets — it fails truthfully while no render backend exists."""
    res = client.post("/api/v1/try-on/animation-render", json={
        "product_ids": [1, 3, 4, 6, 8],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "output_aspect": "9:16",
        "background_mode": "studio",
        "animation_style": "premium_realistic"
    })
    assert res.status_code == 503
    body = res.json()
    assert body["error"]["code"] == "VTON_ENGINE_UNAVAILABLE"


def test_tryon_session_creation_fails_truthfully_without_worker(client: TestClient):
    """A7 guard: creating a try-on session requires rendering, so without a
    GPU worker it must return 503 — not a session with a fabricated image."""
    sess_res = client.post("/api/v1/try-on/sessions", json={
        "product_id": 1,
        "avatar_model_id": "avatar_athletic_m"
    })
    assert sess_res.status_code == 503
    assert sess_res.json()["error"]["code"] == "VTON_ENGINE_UNAVAILABLE"


def test_tryon_session_rest_lifecycle(client: TestClient):
    """Tests the non-rendering REST session mechanics (reorder, query, purge)
    on a session created directly in the repository — rendering endpoints are
    covered by the truthful-failure tests above."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.repositories.tryon_repository import TryOnRepository

    db = TestingSessionLocal()
    try:
        repo = TryOnRepository(db)
        session = repo.create_tryon_session(
            product_id=1,
            input_user_image_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
            applied_items=[{
                "product_id": 1,
                "position": "upper_outer",
                "image_url": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=600",
            }],
            slot_mapping={"upper_outer": 1},
        )
        session_id = session.id
    finally:
        db.close()

    # Reorder session items (pure state operation, no rendering)
    reorder_res = client.post(f"/api/v1/try-on/sessions/{session_id}/reorder", json={
        "slot_order": ["upper_outer"]
    })
    assert reorder_res.status_code == 200

    # Query session details
    get_res = client.get(f"/api/v1/try-on/sessions/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["session_id"] == session_id

    # Purge session (GDPR Article 17)
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
