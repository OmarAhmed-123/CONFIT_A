"""Group 4 — Personal Wardrobe & Smart Reuse integration + unit tests.

Covers:
  * Taxonomy normalization boundary (unit)
  * Duplicate-detection scoring + strict/loose thresholds (integration)
  * Wardrobe lifecycle: upload -> processing status -> retry
  * Authorization / user-isolation (User A cannot touch User B's wardrobe)
  * Wardrobe-first outfit recommendation (BRD §24)
  * Bulk import partial-success semantics (BRD §13)
  * Cross-user duplicate-check leak protection
  * AI provider boundary is real (auto-tag honestly reports unavailability
    when no GEMINI_API_KEY is configured, never fabricates tags)
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.services import wardrobe_taxonomy as taxonomy


# ─────────────────────────── unit: taxonomy ───────────────────────────
class TestTaxonomyNormalization:
    def test_color_family_collapses_synonyms(self):
        assert taxonomy.normalize_color("Navy Blue") == "Navy"
        assert taxonomy.normalize_color("dark navy") == "Navy"
        assert taxonomy.normalize_color("midnight blue") == "Navy"
        assert taxonomy.normalize_color("BLACK") == "Black"
        assert taxonomy.normalize_color("charcoal grey") == "Grey"

    def test_category_normalization_uses_aliases(self):
        assert taxonomy.normalize_category("blazer") == "Outerwear"
        assert taxonomy.normalize_category("trousers") == "Bottoms"
        assert taxonomy.normalize_category("t-shirt") == "Tops"
        assert taxonomy.normalize_category("Sneakers") == "Footwear"

    def test_pattern_and_occasion_normalization(self):
        assert taxonomy.normalize_pattern("pinstripe") == "Striped"
        assert taxonomy.normalize_pattern("tartan") == "Plaid"
        occ = taxonomy.normalize_occasions(["smart-casual", "office", "unknown-xyz"])
        assert "Smart Casual" in occ and "Work & Business" in occ

    def test_analysis_validator_rejects_non_dict(self):
        with pytest.raises(ValueError):
            taxonomy.normalize_wardrobe_analysis("not-a-dict")

    def test_analysis_validator_normalizes_full_payload(self):
        raw = {
            "category": "Blazer",           # -> Outerwear via alias
            "item_type": "Oversized Blazer",
            "primary_color": "Navy Blue",   # -> Navy
            "primary_color_hex": "#112233",
            "secondary_colors": ["Beige"],
            "style_tags": ["Tailored", "Wool Blend"],
            "pattern": "solid",
            "occasion_suitability": ["Work", "smart-casual"],
            "seasonality": "Winter",
            "confidence": "0.87",
        }
        out = taxonomy.normalize_wardrobe_analysis(raw)
        assert out["category"] == "Outerwear"
        assert out["primary_color"] == "Navy"
        assert out["primary_color_hex"] == "#112233"
        assert out["pattern"] == "Solid"
        assert out["seasonality"] == "Winter"
        assert out["confidence"] == pytest.approx(0.87)
        assert "Smart Casual" in out["occasion_suitability"]


# ────────────────── shared login helpers (real seed users) ─────────────────
def _login(client: TestClient, email: str = "shopper@confit.io") -> dict:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ───────────────────── duplicate-detection integration ─────────────────────
class TestDuplicateDetection:
    def test_seeded_wardrobe_returns_navy_outerwear_match(self, client):
        headers = _login(client)
        res = client.post("/api/v1/wardrobe/duplicate-check", headers=headers, json={
            "product_id": 1, "product_title": "Any Navy Outerwear",
            "category": "Outerwear", "color_family": "Navy Blue",
            "strict_mode": True,
        })
        assert res.status_code == 200
        body = res.json()
        # Seed data ships a Navy Blue Outerwear wardrobe item; scorer should
        # earn 55 (type) + 35 (color) = 90 -> at the strict 0.90 threshold.
        assert body["has_duplicate_risk"] is True
        assert body["similarity_score"] >= 90
        assert body["owned_item"]["color_name"] == "Navy Blue"
        assert "same type" in (body["comparison_notes"] or "")

    def test_different_color_below_strict_threshold(self, client):
        """Same type (Outerwear) but different color -> only 55, below 0.90."""
        headers = _login(client)
        res = client.post("/api/v1/wardrobe/duplicate-check", headers=headers, json={
            "product_id": 2, "product_title": "Beige Trench",
            "category": "Outerwear", "color_family": "Beige",
            "strict_mode": True,
        })
        body = res.json()
        assert body["has_duplicate_risk"] is False
        assert body["similarity_score"] < 90

    def test_loose_mode_flags_same_type_only(self, client):
        headers = _login(client)
        res = client.post("/api/v1/wardrobe/duplicate-check", headers=headers, json={
            "product_id": 2, "product_title": "Beige Trench",
            "category": "Outerwear", "color_family": "Beige",
            "strict_mode": False,  # loose: 65% threshold, type alone (55) still misses
        })
        body = res.json()
        # 55 (type) < 65 loose threshold -> no risk
        assert body["has_duplicate_risk"] is False
        # But same type + color would trigger loose easily:
        res2 = client.post("/api/v1/wardrobe/duplicate-check", headers=headers, json={
            "product_id": 3, "product_title": "Another Navy Blazer",
            "category": "Outerwear", "color_family": "Navy",
            "strict_mode": False,
        })
        assert res2.json()["has_duplicate_risk"] is True

    def test_anonymous_call_never_reveals_wardrobe(self, client):
        """Ensures the anon path returns constant no-risk without touching any user's data."""
        res = client.post("/api/v1/wardrobe/duplicate-check", json={
            "product_id": 1, "product_title": "X",
            "category": "Outerwear", "color_family": "Navy",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["has_duplicate_risk"] is False
        assert body["owned_item"] is None


# ─────────────────────── authorization / isolation ─────────────────────────
class TestWardrobeAuthorization:
    def test_anonymous_cannot_read_wardrobe(self, client):
        assert client.get("/api/v1/wardrobe/items").status_code == 401

    def test_cross_user_item_read_is_404(self, client):
        """IDOR guard: another user's item id must resolve to 404, not 403 —
        the API never confirms whether an ID belongs to someone else."""
        shopper = _login(client, "shopper@confit.io")
        admin = _login(client, "admin@confit.io")

        # Shopper creates an item
        created = client.post("/api/v1/wardrobe/items", headers=shopper, json={
            "title": "Isolation Test Item", "category": "Tops",
            "color_name": "Black", "image_url": "https://example.com/x.jpg",
        }).json()
        item_id = created["id"]

        # Admin tries to read it — must be 404 (ownership scoped in repo)
        assert client.get(f"/api/v1/wardrobe/items/{item_id}", headers=admin).status_code == 404
        # And cannot delete it
        assert client.delete(f"/api/v1/wardrobe/items/{item_id}", headers=admin).status_code == 404


# ─────────────────── wardrobe-first outfit recommendation ──────────────────
class TestWardrobeFirstOutfits:
    def test_returns_owned_pieces_and_purchase_gaps(self, client):
        headers = _login(client)
        res = client.get("/api/v1/wardrobe/outfit-suggestions?occasion=Smart%20Casual", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["wardrobe_first"] is True
        # Seeded shopper owns exactly one Outerwear piece -> that position is
        # filled from the wardrobe, other positions are gaps with catalog recs.
        assert body["owned_count"] >= 1
        owned_positions = {item["position"] for item in body["owned_items"]}
        assert "outerwear" in owned_positions
        # Any purchase suggestion must NOT be for a position we already filled
        for rec in body["purchase_suggestions"]:
            assert rec["position"] not in owned_positions
            assert rec["source"] == "catalog"


# ───────────────────────── gap analysis honesty ────────────────────────────
class TestGapAnalysis:
    def test_gaps_only_include_uncovered_categories(self, client):
        headers = _login(client)
        res = client.get("/api/v1/wardrobe/gap-analysis", headers=headers)
        assert res.status_code == 200
        gaps = res.json()
        # Seeded shopper has an Outerwear item -> Outerwear must NOT be a gap.
        assert all(g["missing_category"] != "Outerwear" for g in gaps)
        # But has zero Bottoms/Footwear/Accessories -> those must appear.
        missing = {g["missing_category"] for g in gaps}
        assert "Bottoms" in missing
        assert "Footwear" in missing


# ───────────────────── lifecycle / upload pipeline ─────────────────────────
def _tiny_png(seed: bytes = b"") -> bytes:
    # 1x1 transparent PNG — a real image, not fabricated bytes claiming to be
    # one. ``seed`` varies the trailing bytes so distinct tests produce
    # distinct sha256 content hashes (duplicate-upload protection keys on
    # content, so identical bytes across tests would legitimately dedupe).
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    ) + seed


class TestWardrobeUploadPipeline:
    def test_manual_create_persists_and_is_ready(self, client):
        headers = _login(client)
        res = client.post("/api/v1/wardrobe/items", headers=headers, json={
            "title": "Lifecycle Test Item",
            "category": "blazer",            # alias -> normalized to Outerwear
            "color_name": "navy blue",       # alias -> normalized to Navy
            "image_url": "https://example.com/nav.jpg",
        })
        assert res.status_code == 201
        item = res.json()
        assert item["category"] == "Outerwear"
        assert item["color_name"] == "Navy"
        assert item["processing_status"] == "ready"

    def test_image_upload_without_vision_key_reports_failure_honestly(self, client, monkeypatch):
        """With no GEMINI_API_KEY, the vision provider returns
        analysis_available=False -> service marks item 'failed' (retryable).
        The photo is still safely stored; no fabricated tags are written."""
        from backend.app.core import config as config_mod
        monkeypatch.setattr(config_mod.settings, "GEMINI_API_KEY", None, raising=False)

        headers = _login(client)
        res = client.post(
            "/api/v1/wardrobe/upload",
            headers=headers,
            files={"file": ("test.png", _tiny_png(), "image/png")},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["summary"]["total"] == 1
        entry = body["results"][0]
        # Item is created but honestly marked failed — never a fake success.
        assert entry["status"] == "created"
        assert entry["item"]["processing_status"] == "failed"
        assert entry["item"]["processing_error"]

    def test_upload_rejects_unsupported_content_type(self, client):
        headers = _login(client)
        res = client.post(
            "/api/v1/wardrobe/upload",
            headers=headers,
            files={"file": ("evil.exe", b"MZ\x00", "application/octet-stream")},
        )
        assert res.status_code == 422

    def test_bulk_upload_partial_success_isolation(self, client, monkeypatch):
        """One bad file must not roll back the good ones (BRD §13)."""
        from backend.app.core import config as config_mod
        monkeypatch.setattr(config_mod.settings, "GEMINI_API_KEY", None, raising=False)

        headers = _login(client)
        res = client.post(
            "/api/v1/wardrobe/upload/bulk",
            headers=headers,
            files=[
                ("files", ("ok.png", _tiny_png(b"bulk-batch"), "image/png")),
                ("files", ("bad.exe", b"nope", "application/octet-stream")),
            ],
        )
        assert res.status_code == 201
        body = res.json()
        assert body["summary"]["total"] == 2
        assert body["summary"]["succeeded"] == 1
        assert body["summary"]["failed"] == 1
        # Per-item status lets the UI show which one failed and retry it.
        statuses = {r["filename"]: r["status"] for r in body["results"]}
        assert statuses["ok.png"] == "created"
        assert statuses["bad.exe"] == "failed"

    def test_retry_analysis_endpoint_scoped_to_owner(self, client):
        shopper = _login(client, "shopper@confit.io")
        admin = _login(client, "admin@confit.io")
        # Create a shopper item and try to re-analyze it as admin -> 404.
        item = client.post("/api/v1/wardrobe/items", headers=shopper, json={
            "title": "Retry Test", "category": "Tops",
            "color_name": "Black", "image_url": "https://example.com/x.jpg",
        }).json()
        cross = client.post(f"/api/v1/wardrobe/items/{item['id']}/analyze", headers=admin)
        assert cross.status_code == 404


# ────────────────────── auto-tag honesty (no fake AI) ──────────────────────
class TestAutoTagHonesty:
    def test_auto_tag_without_key_returns_analysis_unavailable(self, client, monkeypatch):
        from backend.app.core import config as config_mod
        monkeypatch.setattr(config_mod.settings, "GEMINI_API_KEY", None, raising=False)

        headers = _login(client)
        res = client.post("/api/v1/wardrobe/auto-tag", headers=headers, json={
            "image_url": "https://example.com/nav.jpg",
        })
        assert res.status_code == 200
        body = res.json()
        # Honest degradation: no fake attributes are returned.
        assert body["analysis_available"] is False
        assert body.get("detected_title") in (None, "")
