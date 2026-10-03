"""Feature 06 (Outfit Builder compatibility) — backend contract tests.

Pins the /api/stylist/compatibility and /api/outfits/fill-in-the-blank
pipelines against the LIVE worker contract (mirrors the real response of
confit-outfit-worker — OutfitTransformer OutfitCLIPTransformer, Modal CPU):

  * model path: score comes from the worker, engine is named
    outfit_transformer_clip, the type-aware block and TATTOO-style advisory
    axes travel through, model warnings surface as suggestions;
  * honest fallbacks: worker down / not configured / product image missing /
    single product → the deterministic rules heuristic answers with
    engine=rules_heuristic and a reason — SAME numbers as pre-06, never a
    fabricated model score;
  * FITB: model ranking maps worker candidate ids back to real catalog
    products; worker down → rules-engine ranking over outfit+candidate sets
    (labeled rules_heuristic); unknown product → 404; empty pool → honest
    fitb_available=False; top_k bounds enforced;
  * provider unit tests: response validation, honest error envelopes,
    dedicated token + payload shape at the HTTP boundary.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core import config as config_mod
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token
from backend.app.main import app
from backend.app.models.catalog import Category, Product
from backend.app.models.user import User, UserRole, BrandProfile
from backend.app.providers.outfit_compat_provider import (
    OutfitCompatProvider,
    _validate_compat_response,
    _validate_fitb_response,
)

DEAD_REDIS = "redis://127.0.0.1:63790/9"


# ── the real worker response shapes (contract pinned 2026-10-03) ────────────

def _worker_compat_ok(score: float = 0.91) -> dict:
    return {
        "status": "ok",
        "engine": "outfit_transformer_clip_cpu",
        "compatibility_score": score,
        "compatibility_score_0_100": int(round(score * 100)),
        "score_interpretation": (
            "Probability the outfit reads as a coherent Polyvore-style look."),
        "items_count": 3,
        "type_aware": {
            "slots": ["upper_outer", "lower", "footwear"],
            "polyvore_categories": ["outerwear", "bottoms", "shoes"],
            "duplicate_slots": [],
            "coverage": {
                "has_upper": True, "has_lower_or_full_body": True,
                "has_footwear": True, "missing_essentials": ["upper_inner"],
            },
            "warnings": [],
        },
        "aesthetic_axes": {
            "method": "clip_text_anchor_projection",
            "inspired_by": "TATTOO (arXiv:2509.23242) aesthetic axes — "
                           "training-free profiling. NOT the paper's MLLM pipeline.",
            "axes": {"color": 81, "style": 74, "season": 80,
                     "occasion": 77, "material": 65, "balance": 72},
            "overall": 75,
        },
        "models": {
            "outfit_transformer": {"license": "mit", "commercial": True},
            "fashionclip": {"license": "mit", "commercial": True,
                            "bias_note": "Farfetch white-background bias"},
        },
        "training_data_note": "Polyvore",
        "timings": {"model_seconds": 1.9},
    }


def _worker_fitb_ok() -> dict:
    return {
        "status": "ok",
        "engine": "outfit_transformer_clip_cpu",
        "target_category_used": "shoes",
        "outfit_items_count": 2,
        "candidates_count": 2,
        "ranked": [
            {"id": "101", "rank": 1, "similarity": 0.8123},
            {"id": "201", "rank": 2, "similarity": 0.4102},
        ],
        "models": _worker_compat_ok()["models"],
        "training_data_note": "Polyvore",
        "disclaimer": "CIR cosine ranking.",
        "timings": {"model_seconds": 2.4},
    }


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def worker_env(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_COMPAT_URL",
                        "https://outfit-worker.test/compatibility", raising=False)
    monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_FITB_URL",
                        "https://outfit-worker.test/fill-in-the-blank", raising=False)
    monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_ADMIN_TOKEN",
                        "test-admin-token", raising=False)
    monkeypatch.setattr(config_mod.settings, "REDIS_URL", DEAD_REDIS, raising=False)


@pytest.fixture
def outfit_ok(monkeypatch):
    """Mock at the HTTP boundary (_call_worker) so the REAL provider
    validation runs inside every API test."""
    async def fake_call(self, url, payload):
        if "compatibility" in url:
            body = _worker_compat_ok()
            body["compatibility_available"] = True
            return body
        body = _worker_fitb_ok()
        body["compatibility_available"] = True
        return body
    monkeypatch.setattr(OutfitCompatProvider, "_call_worker", fake_call)


@pytest.fixture
def outfit_down(monkeypatch):
    async def fake_call(self, url, payload):
        return {"compatibility_available": False,
                "reason": "outfit_worker_timeout"}
    monkeypatch.setattr(OutfitCompatProvider, "_call_worker", fake_call)


@pytest.fixture
def compat_env(worker_env, outfit_ok):
    return worker_env


@pytest.fixture
def world(worker_env):
    """Isolated app: in-memory SQLite, shopper, catalog with a coherent
    three-piece outfit plus completion candidates."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        shopper = User(email=f"shop_{uuid.uuid4().hex[:8]}@example.test",
                       full_name="Shopper", hashed_password="x",
                       role=UserRole.CONSUMER)
        db.add(shopper)
        brand_owner = User(email=f"own_{uuid.uuid4().hex[:8]}@example.test",
                           full_name="Owner", hashed_password="x",
                           role=UserRole.BRAND_OWNER)
        db.add(brand_owner)
        cat = Category(name="Apparel", name_ar="ملابس", slug="apparel")
        db.add(cat)
        db.commit()
        brand = BrandProfile(user_id=brand_owner.id, brand_name="TestLabel",
                             slug=f"testlabel-{uuid.uuid4().hex[:6]}")
        db.add(brand)
        db.commit()
        cat_id, brand_id = cat.id, brand.id

        def add_product(title, image=None, **over):
            base = dict(
                brand_id=brand_id, category_id=cat_id, title=title,
                title_ar="", slug=f"p-{uuid.uuid4().hex[:10]}",
                description="", description_ar="",
                base_price=49.0, color_family="Navy Blue", material=None,
                style_tags='["smart_casual"]', occasion_tags='["work"]',
                thumbnail_url=image or "https://cdn.example.com/thumb.jpg",
                images=f'["{image or "https://cdn.example.com/x.jpg"}"]',
                size_chart_json="{}",
            )
            base.update(over)
            p = Product(**base)
            db.add(p)
            db.commit()
            return p.id

        blazer = add_product("Tailored Wool Blazer")
        trousers = add_product("Wool Suit Trousers")
        oxfords = add_product("Leather Oxford Shoes")
        sandals = add_product("Casual Beach Sandals")
        dress = add_product("Silk Maxi Dress")
        no_image = add_product("Mystery Item", image=None, images="[]",
                               thumbnail_url="")
        ids = dict(blazer=blazer, trousers=trousers, oxfords=oxfords,
                   sandals=sandals, dress=dress, no_image=no_image)
        shopper_id = shopper.id

    headers = {"Authorization":
               f"Bearer {create_access_token({'sub': str(shopper_id)})}"}

    old = app.dependency_overrides.get(get_db)

    def session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = session
    yield type("World", (), {"ids": ids, "headers": headers})()
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


# ── provider unit tests ─────────────────────────────────────────────────────


class TestProviderValidation:
    def test_valid_compat_response(self):
        assert _validate_compat_response(_worker_compat_ok()) is None

    def test_compat_rejects_wrong_engine(self):
        body = _worker_compat_ok()
        body["engine"] = "something_else"
        assert "engine" in _validate_compat_response(body)

    def test_compat_rejects_out_of_range_score(self):
        body = _worker_compat_ok()
        body["compatibility_score"] = 1.5
        assert "compatibility_score" in _validate_compat_response(body)

    def test_compat_rejects_missing_type_aware(self):
        body = _worker_compat_ok()
        body["type_aware"] = None
        assert "type_aware" in _validate_compat_response(body)

    def test_valid_fitb_response(self):
        assert _validate_fitb_response(_worker_fitb_ok()) is None

    def test_fitb_rejects_malformed_ranking(self):
        body = _worker_fitb_ok()
        body["ranked"] = [{"id": "101"}]
        assert "ranked entry" in _validate_fitb_response(body)

    def test_not_configured_is_honest(self, monkeypatch):
        monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_COMPAT_URL", None, raising=False)
        monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_FITB_URL", None, raising=False)
        monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_ADMIN_TOKEN", None, raising=False)
        provider = OutfitCompatProvider()
        assert provider.is_configured() is False

    def test_fallback_never_fabricates(self):
        import asyncio
        provider = OutfitCompatProvider()
        result = asyncio.run(provider.fallback())
        assert result["compatibility_available"] is False
        assert result["reason"]


# ── /api/stylist/compatibility ─────────────────────────────────────────────


class TestCompatibilityEndpoint:
    def test_model_path_names_engine_and_score(self, compat_env, world):
        ids = world.ids
        resp = TestClient(app).post("/stylist/compatibility", json={
            "product_ids": [ids["blazer"], ids["trousers"], ids["oxfords"]]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["engine"] == "outfit_transformer_clip"
        assert body["compatibility_source"] == "model"
        assert body["compatibility_available"] is True
        assert body["compatibility_score"] == 91  # from the model, not the heuristic
        assert body["model_detail"]["model_score"] == 0.91
        assert body["model_detail"]["type_aware"]["coverage"][
            "missing_essentials"] == ["upper_inner"]
        assert body["model_detail"]["aesthetic_axes"]["method"] == \
            "clip_text_anchor_projection"
        # pre-06 fields still present (backwards contract)
        for field in ("color_harmony_type", "color_harmony_verdict",
                      "aesthetic_consistency_verdict", "occasion_score",
                      "budget_status", "suggestions"):
            assert field in body

    def test_model_warning_surfaced_as_suggestion(self, compat_env, world, monkeypatch):
        async def fake_call(self, url, payload):
            body = _worker_compat_ok()
            body["compatibility_available"] = True
            body["type_aware"]["warnings"] = [
                "Two items compete for the same slot ('upper_outer')"]
            return body
        monkeypatch.setattr(OutfitCompatProvider, "_call_worker", fake_call)
        ids = world.ids
        resp = TestClient(app).post("/stylist/compatibility", json={
            "product_ids": [ids["blazer"], ids["trousers"], ids["oxfords"]]})
        assert resp.status_code == 200
        assert "upper_outer" in resp.json()["suggestions"][0]

    def test_worker_down_falls_back_to_heuristic_honestly(
            self, worker_env, outfit_down, world):
        ids = world.ids
        resp = TestClient(app).post("/stylist/compatibility", json={
            "product_ids": [ids["blazer"], ids["trousers"], ids["oxfords"]]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["engine"] == "rules_heuristic"
        assert body["compatibility_source"] == "heuristic"
        assert body["compatibility_available"] is False
        assert body["reason"] == "outfit_worker_timeout"
        assert body["model_detail"] is None

    def test_heuristic_matches_pre_feature06_behavior(self, world, monkeypatch):
        """With the provider unconfigured the endpoint must return EXACTLY
        the pre-06 heuristic numbers (plus the new labeling fields)."""
        monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_COMPAT_URL", None, raising=False)
        monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_FITB_URL", None, raising=False)
        monkeypatch.setattr(config_mod.settings, "OUTFIT_WORKER_ADMIN_TOKEN", None, raising=False)
        ids = world.ids
        from backend.app.services.outfit_service import OutfitService
        product_ids = [ids["blazer"], ids["trousers"], ids["oxfords"]]
        resp = TestClient(app).post("/stylist/compatibility",
                                    json={"product_ids": product_ids})
        assert resp.status_code == 200
        body = resp.json()
        assert body["engine"] == "rules_heuristic"
        assert body["reason"] == "outfit_model_not_configured"
        # Same numbers the legacy heuristic alone produces
        session = next(app.dependency_overrides[get_db]())
        service = OutfitService(session)
        legacy = service._heuristic_result(product_ids)
        assert body["compatibility_score"] == legacy["compatibility_score"]
        assert body["color_harmony_type"] == legacy["color_harmony_type"]
        assert body["occasion_score"] == legacy["occasion_score"]

    def test_single_product_never_calls_model(self, compat_env, world, monkeypatch):
        called = {"n": 0}

        async def spy(self, url, payload):
            called["n"] += 1
            return {"compatibility_available": False, "reason": "never"}
        monkeypatch.setattr(OutfitCompatProvider, "_call_worker", spy)
        resp = TestClient(app).post("/stylist/compatibility", json={
            "product_ids": [world.ids["blazer"]]})
        assert resp.status_code == 200
        assert resp.json()["reason"] == "not_enough_products"
        assert called["n"] == 0

    def test_product_without_image_declines_model_path(
            self, compat_env, world, monkeypatch):
        called = {"n": 0}

        async def spy(self, url, payload):
            called["n"] += 1
            return {"compatibility_available": False, "reason": "never"}
        monkeypatch.setattr(OutfitCompatProvider, "_call_worker", spy)
        resp = TestClient(app).post("/stylist/compatibility", json={
            "product_ids": [world.ids["blazer"], world.ids["no_image"]]})
        assert resp.status_code == 200
        assert resp.json()["reason"] == "product_image_missing"
        assert resp.json()["engine"] == "rules_heuristic"
        assert called["n"] == 0


# ── /api/outfits/fill-in-the-blank ─────────────────────────────────────────


class TestFillInTheBlankEndpoint:
    def test_model_path_ranks_real_ids(self, compat_env, world, monkeypatch):
        ids = world.ids

        async def fake_call(self, url, payload):
            assert "fill-in-the-blank" in url
            # the outfit arrives with slots in the coarse layering vocabulary
            slots = [i["slot"] for i in payload["outfit"]]
            assert slots == ["upper_outer", "lower"]
            first = payload["candidates"][0]
            assert first["id"] == str(ids["oxfords"])
            body = _worker_fitb_ok()
            body["compatibility_available"] = True
            body["ranked"] = [
                {"id": str(ids["oxfords"]), "rank": 1, "similarity": 0.8123},
                {"id": str(ids["sandals"]), "rank": 2, "similarity": 0.4102},
            ]
            return body
        monkeypatch.setattr(OutfitCompatProvider, "_call_worker", fake_call)

        resp = TestClient(app).post(
            "/outfits/fill-in-the-blank",
            json={
                "product_ids": [ids["blazer"], ids["trousers"]],
                "target_slot": "footwear",
                "candidate_product_ids": [ids["oxfords"], ids["sandals"]],
            }, headers=world.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["engine"] == "outfit_transformer_clip"
        assert body["target_category_used"] == "shoes"
        assert [r["product_id"] for r in body["ranked"]] == [
            ids["oxfords"], ids["sandals"]]
        assert body["ranked"][0]["title"] == "Leather Oxford Shoes"
        assert body["ranked"][0]["image_url"].startswith("https://")

    def test_worker_down_falls_back_to_rules_ranking(
            self, worker_env, outfit_down, world):
        ids = world.ids
        resp = TestClient(app).post(
            "/outfits/fill-in-the-blank",
            json={
                "product_ids": [ids["blazer"], ids["trousers"]],
                "target_slot": "footwear",
                "candidate_product_ids": [ids["oxfords"], ids["sandals"]],
            }, headers=world.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["fitb_available"] is True
        assert body["engine"] == "rules_heuristic"
        assert body["reason"] == "outfit_worker_timeout"
        assert len(body["ranked"]) == 2
        assert {r["product_id"] for r in body["ranked"]} == {
            ids["oxfords"], ids["sandals"]}
        # heuristic similarity is a normalized 0-1 score
        for entry in body["ranked"]:
            assert 0.0 <= entry["similarity"] <= 1.0

    def test_unknown_product_404(self, compat_env, world):
        resp = TestClient(app).post(
            "/outfits/fill-in-the-blank",
            json={"product_ids": [999999]},
            headers=world.headers)
        assert resp.status_code == 404

    def test_empty_outfit_declined(self, compat_env, world):
        resp = TestClient(app).post(
            "/outfits/fill-in-the-blank",
            json={"product_ids": []},
            headers=world.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["fitb_available"] is False
        assert body["reason"] == "empty_outfit"
        assert body["ranked"] == []

    def test_top_k_bounds_enforced(self, compat_env, world):
        resp = TestClient(app).post(
            "/outfits/fill-in-the-blank",
            json={"product_ids": [world.ids["blazer"]], "top_k": 21},
            headers=world.headers)
        assert resp.status_code == 422

    def test_requires_auth(self, compat_env, world):
        resp = TestClient(app).post(
            "/outfits/fill-in-the-blank",
            json={"product_ids": [world.ids["blazer"]]})
        assert resp.status_code in (401, 403)

    def test_default_pool_excludes_outfit_and_filters_slot(
            self, compat_env, world):
        ids = world.ids
        seen = {}

        async def fake_call(self, url, payload):
            seen["candidates"] = payload["candidates"]
            body = _worker_fitb_ok()
            body["compatibility_available"] = True
            body["ranked"] = []
            return body
        with patch.object(OutfitCompatProvider, "_call_worker", fake_call):
            resp = TestClient(app).post(
                "/outfits/fill-in-the-blank",
                json={
                    "product_ids": [ids["blazer"], ids["trousers"]],
                    "target_slot": "footwear",
                }, headers=world.headers)
            assert resp.status_code == 200
            cand_ids = {int(c["id"]) for c in seen["candidates"]}
            # only footwear products from the sweep, never the outfit itself
            assert cand_ids == {ids["oxfords"], ids["sandals"]}
