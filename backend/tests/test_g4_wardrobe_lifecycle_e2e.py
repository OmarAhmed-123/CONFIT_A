"""G4 wardrobe — full-lifecycle E2E + analysis-execution + IDOR regression.

BRD PR2 (docs/G4_WARDROBE_BRD.md): proves the lifecycle the audit could not —
upload -> analyze -> edit -> outfit -> gap -> delete — with fixture data that
is created and cleaned inside the test, and pins the honesty contracts:

  * analysis mode strategy (auto probes the broker, sync never enqueues,
    async fails CLOSED instead of leaving items in `processing`);
  * an inline-analysis crash reports `failed` per file (the old code reported
    `created` with a perpetually-`processing` item);
  * stuck-`processing` items self-heal to `failed` on the next read;
  * cross-user access to wardrobe items, outfits and mood boards is 404 with
    no existence oracle (mood boards previously leaked existence via 403).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core import config as config_mod
from backend.app.providers.tryon_provider import VisualSearchAIProvider
from backend.app.services.wardrobe_service import WardrobeService
from backend.tests.conftest import TestingSessionLocal

DEAD_REDIS = "redis://127.0.0.1:9/0"  # port 9/discard: connect refused, fast


def _register(client: TestClient, label: str) -> dict:
    email = f"wardrobe_e2e_{label}_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": f"Wardrobe E2E {label}",
    })
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _register_with_email(client: TestClient, label: str) -> tuple[dict, str]:
    email = f"wardrobe_e2e_{label}_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": f"Wardrobe E2E {label}",
    })
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}, email


def _tiny_png(seed: bytes = b"") -> bytes:
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (8, 8), (12, 18, 24)).save(buf, format="PNG")
    return buf.getvalue() + seed


FAKE_ANALYSIS = {
    "analysis_available": True,
    "category": "Tops",
    "item_type": "Oxford Shirt",
    "primary_color": "White",
    "primary_color_hex": "#FFFFFF",
    "secondary_colors": [],
    "pattern": "Solid",
    "style_tags": ["Cotton", "Breathable"],
    "occasion_suitability": ["Smart Casual"],
    "seasonality": "All-Season",
    "confidence": 0.93,
}


@pytest.fixture
def vision_ok(monkeypatch):
    """Real provider class, analysis method replaced by a deterministic fake
    (the model call is the only network dependency in this suite)."""
    async def fake_analyze(self, ref):  # noqa: ARG001
        return dict(FAKE_ANALYSIS)
    monkeypatch.setattr(VisualSearchAIProvider, "analyze_wardrobe_image", fake_analyze)
    return True


@pytest.fixture
def broker_down(monkeypatch):
    """No broker anywhere near this process (serverless default)."""
    monkeypatch.setattr(config_mod.settings, "REDIS_URL", DEAD_REDIS, raising=False)


def _manual_item(client: TestClient, headers: dict, **fields) -> dict:
    payload = {
        "title": "Piece", "category": "Tops", "color_name": "Black",
        "image_url": "https://images.unsplash.com/photo-lifecycle-fixture",
    }
    payload.update(fields)
    res = client.post("/api/v1/wardrobe/items", headers=headers, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


# ─────────────────────── full lifecycle (the audit's ask) ───────────────────

def test_full_lifecycle_upload_edit_outfit_gap_delete(client, broker_down, vision_ok):
    """top + bottom + bottom + shoe (manual, ready) plus one photo upload:
    upload -> analyze -> edit -> wardrobe-first outfit -> gap analysis ->
    delete (DB row AND stored object removed)."""
    headers, _ = _register_with_email(client, "alice")

    # 4 manual pieces: Tops x1, Bottoms x2, Footwear x1
    top = _manual_item(client, headers, title="Oxford Shirt", category="Tops", color_name="White")
    _manual_item(client, headers, title="Pleated Trousers", category="Bottoms", color_name="Navy")
    _manual_item(client, headers, title="Slim Chinos", category="Bottoms", color_name="Beige")
    _manual_item(client, headers, title="Leather Sneakers", category="Footwear", color_name="White")

    # UPLOAD: photo goes through validate -> store -> analyze (inline: no broker)
    res = client.post(
        "/api/v1/wardrobe/upload", headers=headers,
        files={"file": ("shirt.png", _tiny_png(b"lifecycle-e2e"), "image/png")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    entry = body["results"][0]
    assert entry["status"] == "created"
    uploaded = entry["item"]
    # Inline analysis ran inside the request: final state is in the response.
    assert uploaded["processing_status"] == "ready"
    # Tags come from the (mocked) model output, normalized — not fabricated.
    assert uploaded["category"] == "Tops"
    assert uploaded["color_name"] == "White"
    assert "Cotton" in uploaded["ai_tags"]
    assert uploaded["ai_confidence"] == pytest.approx(0.93)

    # EDIT: controlled fields update through the allowlist
    res = client.put(f"/api/v1/wardrobe/items/{uploaded['id']}", headers=headers,
                     json={"title": "Renamed Oxford Shirt"})
    assert res.status_code == 200
    assert res.json()["title"] == "Renamed Oxford Shirt"

    # OUTFIT: wardrobe-first picks every owned position, only missing ones buy
    res = client.get("/api/v1/wardrobe/outfit-suggestions",
                     headers=headers, params={"occasion": "Smart Casual"})
    assert res.status_code == 200
    sug = res.json()
    owned_positions = {it["position"] for it in sug["owned_items"]}
    assert {"top", "bottom", "footwear"} <= owned_positions
    assert not ({"top", "bottom", "footwear"} & set(sug["missing_positions"]))
    assert set(sug["missing_positions"]) <= {"outerwear", "accessory"}
    assert sug["owned_count"] >= 3

    # GAP: the three covered categories are suppressed; the uncovered ones remain
    res = client.get("/api/v1/wardrobe/gap-analysis", headers=headers)
    assert res.status_code == 200
    gap_cats = {g["missing_category"] for g in res.json()}
    assert gap_cats == {"Outerwear", "Accessories"}

    # DELETE: DB row and the stored object both go away
    stored_url = client.get(f"/api/v1/wardrobe/items/{uploaded['id']}", headers=headers) \
        .json()["image_url"]
    res = client.delete(f"/api/v1/wardrobe/items/{uploaded['id']}", headers=headers)
    assert res.status_code == 200
    remaining = client.get("/api/v1/wardrobe/items", headers=headers).json()
    assert all(it["id"] != uploaded["id"] for it in remaining)
    if stored_url.startswith("/uploads/"):
        # Local dev backend root (STORAGE_LOCAL_DIR default, relative to CWD).
        local_path = os.path.join("backend", "data", "uploads", stored_url[len("/uploads/"):])
        assert not os.path.exists(local_path), "delete must remove the stored object"


def test_upload_report_and_listing_consistent_after_failure(client, monkeypatch):
    """Provider down (no key): upload is saved, entry is `created` with the
    item honestly `failed` — and the same state comes back on listing."""
    monkeypatch.setattr(config_mod.settings, "GEMINI_API_KEY", None, raising=False)
    headers, _ = _register_with_email(client, "bob")
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("b.png", _tiny_png(b"no-key"), "image/png")})
    assert res.status_code == 201
    item = res.json()["results"][0]["item"]
    assert item["processing_status"] == "failed"
    assert item["processing_error"]
    listed = client.get("/api/v1/wardrobe/items", headers=headers).json()
    match = next(it for it in listed if it["id"] == item["id"])
    assert match["processing_status"] == "failed"


# ─────────────────── analysis execution strategy (G-ASYNC) ─────────────────

def test_sync_mode_never_enqueues(client, broker_down, vision_ok, monkeypatch):
    from backend.app.workers import tasks as worker_tasks

    def boom(self, *a, **k):
        raise AssertionError("sync mode must not touch the queue")
    monkeypatch.setattr(worker_tasks.auto_tag_wardrobe_task, "delay", boom)
    monkeypatch.setattr(config_mod.settings, "WARDROBE_ANALYSIS_MODE", "sync", raising=False)

    headers, _ = _register_with_email(client, "carol")
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("c.png", _tiny_png(b"sync"), "image/png")})
    assert res.status_code == 201
    assert res.json()["results"][0]["item"]["processing_status"] == "ready"


def test_auto_mode_runs_inline_when_broker_down(client, broker_down, vision_ok, monkeypatch):
    """The production (Vercel) shape: no broker -> inline analysis, final
    state in the upload response, queue never touched."""
    from backend.app.workers import tasks as worker_tasks

    def boom(self, *a, **k):
        raise AssertionError("auto mode with a dead broker must analyze inline")
    monkeypatch.setattr(worker_tasks.auto_tag_wardrobe_task, "delay", boom)
    monkeypatch.setattr(config_mod.settings, "WARDROBE_ANALYSIS_MODE", "auto", raising=False)

    headers, _ = _register_with_email(client, "dave")
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("d.png", _tiny_png(b"auto"), "image/png")})
    assert res.status_code == 201
    assert res.json()["results"][0]["item"]["processing_status"] == "ready"


def test_inline_crash_reports_failed_entry_not_created(client, broker_down, monkeypatch):
    """The swallowed-error defect: previously an inline crash produced
    `created` + a perpetually-`processing` item. The contract now is:
    the per-file report says `failed` and the item row is failed/retryable."""
    async def crash(self, item):
        raise RuntimeError("simulated provider crash")
    monkeypatch.setattr(WardrobeService, "_run_ai_analysis", crash)
    monkeypatch.setattr(config_mod.settings, "WARDROBE_ANALYSIS_MODE", "sync", raising=False)

    headers, _ = _register_with_email(client, "erin")
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("e.png", _tiny_png(b"crash"), "image/png")})
    # Single-upload endpoint: a failed file is a 422 with the honest detail
    # (bulk upload keeps 201 + per-file status for partial success).
    assert res.status_code == 422
    assert "analysis" in res.json()["detail"].lower()

    listed = client.get("/api/v1/wardrobe/items", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["processing_status"] == "failed"


def test_async_mode_dead_broker_fails_closed(client, monkeypatch, vision_ok):
    """`async` is an operator choice that requires a worker. When the broker
    is unreachable the item must end `failed` (retryable) and the report must
    say so — never `created`/`processing` with nothing to pick it up."""
    from backend.app.workers import tasks as worker_tasks
    monkeypatch.setattr(
        worker_tasks.auto_tag_wardrobe_task, "delay",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("broker down")),
    )
    monkeypatch.setattr(config_mod.settings, "WARDROBE_ANALYSIS_MODE", "async", raising=False)

    headers, _ = _register_with_email(client, "frank")
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("f.png", _tiny_png(b"async"), "image/png")})
    assert res.status_code == 422
    assert "queue" in res.json()["detail"].lower()
    listed = client.get("/api/v1/wardrobe/items", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["processing_status"] == "failed"


def test_stuck_processing_self_heals_on_next_read(client, monkeypatch):
    """An item stuck in `processing` (lost worker, killed function) beyond
    the stale window becomes `failed` + retryable on the next wardrobe read."""
    monkeypatch.setattr(config_mod.settings, "WARDROBE_PROCESSING_STALE_MINUTES", 10, raising=False)
    headers, _ = _register_with_email(client, "grace")
    item = _manual_item(client, headers, title="Stuck Piece", category="Tops")

    db = TestingSessionLocal()
    try:
        db.execute(
            text("update wardrobe_items set processing_status = 'processing', "
                 "created_at = :c where id = :i"),
            {"c": datetime.now(timezone.utc) - timedelta(hours=2), "i": item["id"]},
        )
        db.commit()
    finally:
        db.close()

    listed = client.get("/api/v1/wardrobe/items", headers=headers).json()
    match = next(it for it in listed if it["id"] == item["id"])
    assert match["processing_status"] == "failed"
    assert "timed out" in (match["processing_error"] or "").lower()

    # A FRESH stuck item (within the window) is left alone.
    db = TestingSessionLocal()
    try:
        db.execute(
            text("update wardrobe_items set processing_status = 'processing', "
                 "created_at = CURRENT_TIMESTAMP where id = :i"),
            {"i": item["id"]},
        )
        db.commit()
    finally:
        db.close()
    listed = client.get("/api/v1/wardrobe/items", headers=headers).json()
    match = next(it for it in listed if it["id"] == item["id"])
    assert match["processing_status"] == "processing"


# ───────────────────── cross-user IDOR regression (G-IDOR) ──────────────────

class TestCrossUserIsolation:
    def test_wardrobe_analyze_cross_user_is_404(self, client):
        alice, _ = _register_with_email(client, "ida")
        bob, _ = _register_with_email(client, "idb")
        item = _manual_item(client, alice, title="Alidas Item", category="Tops")
        cross = client.post(f"/api/v1/wardrobe/items/{item['id']}/analyze", headers=bob)
        assert cross.status_code == 404  # not 403: no existence oracle

    def test_outfit_cross_user_is_404_no_oracle(self, client):
        alice, _ = _register_with_email(client, "idc")
        bob, _ = _register_with_email(client, "idd")

        db = TestingSessionLocal()
        try:
            product_id = db.execute(text("select id from products limit 1")).scalar()
        finally:
            db.close()
        assert product_id, "seed catalog must provide a product"

        res = client.post("/api/v1/outfits", headers=alice, json={
            "title": "Alidas Look", "occasion": "Work & Business",
            "product_ids": [product_id],
        })
        assert res.status_code == 201, res.text
        outfit_id = res.json()["id"]

        for method, url in [
            ("GET", f"/api/v1/outfits/{outfit_id}"),
            ("PATCH", f"/api/v1/outfits/{outfit_id}"),
            ("DELETE", f"/api/v1/outfits/{outfit_id}"),
            ("POST", f"/api/v1/outfits/{outfit_id}/share"),
        ]:
            r = client.request(method, url, headers=bob,
                               json={} if method == "PATCH" else None)
            assert r.status_code == 404, f"{method} as stranger must be 404, got {r.status_code}"

        # Alice's outfit is intact and still 200 for her.
        assert client.get(f"/api/v1/outfits/{outfit_id}", headers=alice).status_code == 200

    def test_moodboard_cross_user_is_404_not_403(self, client):
        """Mood boards previously answered cross-user access with 403 — an
        existence oracle. Contract: 404, indistinguishable from missing."""
        alice, _ = _register_with_email(client, "ide")
        bob, _ = _register_with_email(client, "idf")

        res = client.post("/api/v1/me/mood-boards", headers=alice,
                          json={"title": "Autumn Textures"})
        assert res.status_code == 201, res.text
        board_id = res.json()["id"]

        for method, url in [
            ("GET", f"/api/v1/me/mood-boards/{board_id}"),
            ("PATCH", f"/api/v1/me/mood-boards/{board_id}"),
            ("DELETE", f"/api/v1/me/mood-boards/{board_id}"),
            ("POST", f"/api/v1/me/mood-boards/{board_id}/items"),
        ]:
            r = client.request(method, url, headers=bob,
                               json=(
                                   {"title": "hax"} if method == "PATCH"
                                   else {"kind": "url", "payload": {"url": "https://example.com"}}
                                   if method == "POST" else None
                               ))
            assert r.status_code == 404, f"{method} as stranger must be 404, got {r.status_code}"

        assert client.get(f"/api/v1/me/mood-boards/{board_id}", headers=alice).status_code == 200
        # And a NON-EXISTENT board is the same 404 (no oracle either way).
        assert client.get("/api/v1/me/mood-boards/999999", headers=bob).status_code == 404
