from fastapi.testclient import TestClient


def _extract_error_code(body: dict) -> str | None:
    """Helper to extract error code from both {"error": {"code": ...}} and {"detail": {"error": {"code": ...}}} formats"""
    if "error" in body and isinstance(body["error"], dict):
        return body["error"].get("code")
    if "detail" in body:
        detail = body["detail"]
        if isinstance(detail, dict):
            if "error" in detail and isinstance(detail["error"], dict):
                return detail["error"].get("code")
            if "code" in detail:
                return detail.get("code")
        if isinstance(detail, str) and "VTON_ENGINE_UNAVAILABLE" in detail:
            return "VTON_ENGINE_UNAVAILABLE"
    # Also check stringified body
    body_str = str(body)
    if "VTON_ENGINE_UNAVAILABLE" in body_str:
        return "VTON_ENGINE_UNAVAILABLE"
    return None


def test_dynamic_multi_garment_male_suit_tryon(client: TestClient):
    """D1/A7 guard: multi-render with no GPU worker must fail truthfully (503),
    never returning a static asset or the input photo as the dressed result."""
    res = client.post("/api/v1/try-on/multi-render", json={
        # supported slots only (engine renders tops/outerwear/bottoms/one-pieces):
        # this guard isolates the NO-WORKER failure, not input validation
        # (unsupported slots have their own fast-fail guard:
        # test_vton_person_reference.py::test_multi_render_unsupported_slot_rejected_upfront)
        "product_ids": [1, 3, 4],  # Blazer, Oxford Shirt, Suit Trousers
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "consent_retain_photo": False
    })
    assert res.status_code == 503
    body = res.json()
    code = _extract_error_code(body)
    assert code == "VTON_ENGINE_UNAVAILABLE", f"Expected VTON_ENGINE_UNAVAILABLE, got {body}"


def test_dynamic_multi_garment_female_dress_tryon(client: TestClient):
    """D1/A7 guard: dress multi-render also fails truthfully without a worker."""
    res = client.post("/api/v1/try-on/multi-render", json={
        "product_ids": [5],  # Silk Column Dress (supported slot; the other
        # former picks — sandals/clutch — are engine-unsupported and have
        # their own fast-fail guard)
        "user_image_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600",
        "avatar_model_id": "avatar_hourglass_f",
        "gender_mode": "female",
        "consent_retain_photo": False
    })
    assert res.status_code == 503
    body = res.json()
    code = _extract_error_code(body)
    assert code == "VTON_ENGINE_UNAVAILABLE", f"Expected VTON_ENGINE_UNAVAILABLE, got {body}"


def test_dynamic_animation_tryon_render(client: TestClient):
    """D1/A7 guard: animation render must not fabricate keyframes from static
    assets — it fails truthfully while no render backend exists."""
    res = client.post("/api/v1/try-on/animation-render", json={
        # supported slots only: this guard isolates the NO-WORKER failure
        # (footwear/accessory inputs are rejected upfront with 422 before
        # the availability check — see test_vton_person_reference.py)
        "product_ids": [1, 3, 4],
        "user_image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "output_aspect": "9:16",
        "background_mode": "studio",
        "animation_style": "premium_realistic"
    })
    assert res.status_code == 503
    body = res.json()
    code = _extract_error_code(body)
    assert code == "VTON_ENGINE_UNAVAILABLE", f"Expected VTON_ENGINE_UNAVAILABLE, got {body}"


def test_tryon_session_creation_fails_truthfully_without_worker(client: TestClient):
    """A7 guard: creating a try-on session requires rendering, so without a
    GPU worker it must return 503 — not a session with a fabricated image."""
    sess_res = client.post("/api/v1/try-on/sessions", json={
        "product_id": 1,
        "avatar_model_id": "avatar_athletic_m"
    })
    # Should fail truthfully with 503, or if implementation creates job that fails later, accept 200 with error_code
    # But per honest failure principle, 503 is expected
    if sess_res.status_code == 503:
        code = _extract_error_code(sess_res.json())
        assert code == "VTON_ENGINE_UNAVAILABLE", f"Expected VTON_ENGINE_UNAVAILABLE, got {sess_res.json()}"
    elif sess_res.status_code == 200:
        # Some implementations return session but with failed render - check if rendered is not fake
        body = sess_res.json()
        # If it returns 200, it must not contain fake image that equals input
        # For now, accept 503 path only - if 200, fail to enforce honest 503
        assert False, f"Expected 503 VTON_ENGINE_UNAVAILABLE but got 200: {body}"
    else:
        assert sess_res.status_code == 503, f"Expected 503, got {sess_res.status_code}: {sess_res.text[:500]}"


def test_tryon_session_rest_lifecycle(client: TestClient):
    """Tests the non-rendering REST session mechanics (reorder, query, purge)
    on a session created directly in the repository — rendering endpoints are
    covered by the truthful-failure tests above."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.repositories.tryon_repository import TryOnRepository

    # Sessions are ownership-bound (try-on session IDOR closure): a guest
    # session is bound to a guest token, which the caller must present. The
    # mechanics under test (reorder/query/purge) are unchanged.
    tok = "lifecycle_gtoken"
    hdr = {"X-Session-Token": tok}
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
            guest_token=tok,
        )
        session_id = session.id
    finally:
        db.close()

    # Reorder session items (pure state operation, no rendering)
    reorder_res = client.post(f"/api/v1/try-on/sessions/{session_id}/reorder", json={
        "slot_order": ["upper_outer"]
    }, headers=hdr)
    assert reorder_res.status_code == 200

    # Query session details
    get_res = client.get(f"/api/v1/try-on/sessions/{session_id}", headers=hdr)
    assert get_res.status_code == 200
    assert get_res.json()["session_id"] == session_id

    # An unbound anonymous caller (no token) is denied — the IDOR is closed.
    assert client.get(f"/api/v1/try-on/sessions/{session_id}").status_code == 404

    # Purge session (GDPR Article 17)
    purge_res = client.delete(f"/api/v1/try-on/sessions/{session_id}/purge", headers=hdr)
    assert purge_res.status_code == 200
    assert purge_res.json()["status"] == "purged"


def test_tryon_gdpr_purge_task():
    """Verifies the background GDPR privacy cleanup task purges expired unconsented media assets."""
    from backend.app.workers.tasks import purge_expired_sessions_task
    res = purge_expired_sessions_task()
    assert "purged_count" in res


def test_tryon_image_validation_endpoint(client: TestClient):
    """Honest contract: real base64 decode succeeds; remote URLs are refused (SSRF) — no fabricated analysis."""
    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 96), (120, 60, 40)).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    res = client.post("/api/v1/try-on/validate-image", json={"image_base64": f"data:image/png;base64,{b64}"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert data["format"] == "png"
    assert data["width"] == 64 and data["height"] == 96
    assert data.get("detected_gender") is None
    assert data.get("body_framing") is None

    res2 = client.post("/api/v1/try-on/validate-image", json={
        "image_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"
    })
    assert res2.status_code == 200
    assert res2.json()["is_valid"] is False
