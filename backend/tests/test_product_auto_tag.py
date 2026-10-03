"""Feature 07 (Brand Portal auto-tagging) — backend contract tests.

Pins the /partner/products/{id}/auto-tag pipeline against the LIVE worker
contract (mirrors the real response captured from confit-tagging-worker on
2026-10-03, job live_smoke_001):

  * happy path: brand-owned product -> honest tag set with per-tag
    provenance, append-only union merge for style/occasion tags, colour /
    material filled ONLY when empty (never overwriting brand-curated
    data), category column never mutated (suggestion only);
  * dry_run writes nothing but reports what would change;
  * foreign product -> 404; non-brand role -> 403; nothing to tag -> 422;
  * worker refusals -> 422 with the worker's actionable code; worker
    unavailable -> 503 retryable, no writes;
  * provider unit tests: response validation, honest error envelopes,
    dedicated token + payload shape at the HTTP boundary.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import httpx
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
from backend.app.providers.tagging_provider import (
    TaggingProvider,
    _validate_worker_response,
)

DEAD_REDIS = "redis://127.0.0.1:63790/9"


# ── the real worker response shape (live 2026-10-03) ────────────────────────
def _worker_ok(quality: str = "full") -> dict:
    return {
        "status": "completed",
        "quality": quality,
        "tags": [
            {"axis": "category", "value": "suit jacket", "confidence": 0.7024,
             "source": "fashionclip", "corroborated_by": ["fashionclip"]},
            {"axis": "material", "value": "Italian virgin wool", "confidence": 0.8983,
             "source": "gliner", "language": "en", "corroborated_by": ["gliner"]},
            {"axis": "brand", "value": "Massimo Dutti", "confidence": 0.9796,
             "source": "gliner", "language": "en", "corroborated_by": ["gliner"]},
            {"axis": "color", "value": "dark navy", "confidence": 0.9186,
             "source": "gliner", "language": "en", "corroborated_by": ["gliner"]},
        ],
        "tag_count": 4,
        "axes_unresolved": [],
        "product_suggestions": {
            "color_family": "Navy Blue",
            "material": "wool",
            "style_tags": ["suit jacket", "plaid"],
            "occasion_tags": ["smart_casual"],
            "platform_category": "outerwear",
        },
        "text_language": "ar+en",
        "models": {
            "fashionclip": {"id": "patrickjohncyh/fashion-clip", "params": "ViT-B/32",
                            "license": "mit", "commercial": True, "used": True},
            "gliner": {"id": "urchade/gliner_multi-v2.1", "params": "289M (DeBERTa, multilingual)",
                       "license": "apache-2.0", "commercial": True, "used": True},
        },
        "disclaimer": "Auto-tags are model suggestions with per-tag confidence and provenance.",
        "timings": {"total_seconds": 2.326},
    }


@pytest.fixture
def worker_env(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "TAGGING_WORKER_URL",
                        "https://tagging-worker.test/tag", raising=False)
    monkeypatch.setattr(config_mod.settings, "TAGGING_WORKER_ADMIN_TOKEN",
                        "test-admin-token", raising=False)
    monkeypatch.setattr(config_mod.settings, "REDIS_URL", DEAD_REDIS, raising=False)


@pytest.fixture
def tag_ok(monkeypatch):
    """Mock at the HTTP boundary (_call_worker) so the REAL provider
    validation runs inside every API test."""
    async def fake_call(self, image_url, title="", description="", title_ar="", description_ar=""):
        body = _worker_ok()
        body["tagging_available"] = True
        return body
    monkeypatch.setattr(TaggingProvider, "_call_worker", fake_call)


@pytest.fixture
def tag_refused(monkeypatch):
    async def fake_call(self, image_url, **kw):
        return {"tagging_available": False,
                "reason": "worker_refused:IMAGE_FETCH_FAILED",
                "guidance": "The image URL could not be fetched. Check it is public."}
    monkeypatch.setattr(TaggingProvider, "_call_worker", fake_call)


@pytest.fixture
def tag_down(monkeypatch):
    async def fake_call(self, image_url, **kw):
        return {"tagging_available": False, "reason": "tagging_worker_timeout",
                "guidance": "Tagging took too long. Please try again."}
    monkeypatch.setattr(TaggingProvider, "_call_worker", fake_call)


@pytest.fixture
def portal(worker_env):
    """Isolated app: in-memory SQLite, two brand tenants, one consumer."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        owner = User(email=f"owner_{uuid.uuid4().hex[:8]}@example.test",
                     full_name="Owner", hashed_password="x", role=UserRole.BRAND_OWNER)
        other = User(email=f"other_{uuid.uuid4().hex[:8]}@example.test",
                     full_name="Other", hashed_password="x", role=UserRole.BRAND_OWNER)
        consumer = User(email=f"cons_{uuid.uuid4().hex[:8]}@example.test",
                        full_name="Cons", hashed_password="x", role=UserRole.CONSUMER)
        db.add_all([owner, other, consumer])
        db.flush()
        brand = BrandProfile(user_id=owner.id, brand_name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}")
        brand2 = BrandProfile(user_id=other.id, brand_name="Beta", slug=f"beta-{uuid.uuid4().hex[:6]}")
        db.add_all([brand, brand2])
        cat = Category(name="Coats", name_ar="معاطف", slug="coats")
        db.add(cat)
        db.commit()
        cat_id, brand_id, brand2_id = cat.id, brand.id, brand2.id
        headers = {
            "owner": {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"},
            "other": {"Authorization": f"Bearer {create_access_token({'sub': str(other.id)})}"},
            "consumer": {"Authorization": f"Bearer {create_access_token({'sub': str(consumer.id)})}"},
        }

    def add_product(**over):
        base = dict(
            brand_id=brand_id, category_id=cat_id,
            title="Tailored Italian Wool Double-Breasted Blazer",
            title_ar="بليزر صوف إيطالي",
            slug=f"p-{uuid.uuid4().hex[:10]}",
            description="Massimo Dutti tailored blazer in dark navy virgin wool.",
            description_ar="بدلة زرقاء داكنة من صوف إيطالي.",
            base_price=19.99, color_family="", material=None,
            style_tags='["existing_human_tag"]', occasion_tags="[]",
            thumbnail_url="https://example.com/blazer.jpg", images="[]",
            size_chart_json="{}",
        )
        base.update(over)
        with factory() as db:
            p = Product(**base)
            db.add(p)
            db.commit()
            return p.id

    def get_product(pid):
        with factory() as db:
            p = db.query(Product).filter(Product.id == pid).first()
            return p

    old = app.dependency_overrides.get(get_db)

    def session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = session
    try:
        yield {"client": TestClient(app), "add_product": add_product,
               "get_product": get_product, "headers": headers}
    finally:
        if old is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = old
        engine.dispose()


# ───────────────────────── API contract ─────────────────────────

def test_auto_tag_applies_honest_merge(portal, tag_ok):
    pid = portal["add_product"]()
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 200, res.text
    body = res.json()

    # Full worker disclosure passes through.
    assert body["quality"] == "full"
    assert body["models"]["fashionclip"]["license"] == "mit"
    assert body["models"]["gliner"]["license"] == "apache-2.0"
    assert all({"axis", "value", "confidence", "source"} <= set(t) for t in body["tags"])
    assert body["disclaimer"]

    # Append-only union merge: the human tag SURVIVES, AI tags are added.
    p = portal["get_product"](pid)
    style = json.loads(p.style_tags)
    assert "existing_human_tag" in style
    assert "suit jacket" in style and "plaid" in style
    assert json.loads(p.occasion_tags) == ["smart_casual"]

    # Colour/material filled because the columns were empty.
    assert p.color_family == "Navy Blue"
    assert p.material == "wool"

    applied = {a["field"]: a for a in body["applied"]}
    assert set(applied) == {"style_tags", "occasion_tags", "color_family", "material"}

    # Category column is NEVER mutated — the platform category is a suggestion.
    skipped = {s["field"]: s for s in body["skipped"]}
    assert skipped["category"]["reason"] == "suggestion_only"
    assert p.category_id is not None  # untouched


def test_ai_never_overwrites_brand_curated_values(portal, tag_ok):
    pid = portal["add_product"](color_family="Midnight Black", material="cashmere blend")
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 200, res.text
    body = res.json()
    skipped = {s["field"]: s for s in body["skipped"]}
    assert skipped["color_family"]["reason"] == "kept_existing"
    assert skipped["color_family"]["existing"] == "Midnight Black"
    assert skipped["material"]["reason"] == "kept_existing"
    p = portal["get_product"](pid)
    assert p.color_family == "Midnight Black"          # human value kept
    assert p.material == "cashmere blend"              # human value kept
    assert "color_family" not in {a["field"] for a in body["applied"]}


def test_dry_run_writes_nothing_but_reports(portal, tag_ok):
    pid = portal["add_product"]()
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag?dry_run=true",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["dry_run"] is True
    assert body["applied"], "dry run should report what WOULD change"
    p = portal["get_product"](pid)
    assert p.color_family == ""                          # nothing written
    assert json.loads(p.style_tags) == ["existing_human_tag"]


def test_foreign_product_is_404(portal, tag_ok):
    pid = portal["add_product"]()  # belongs to "owner"
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["other"])
    assert res.status_code == 404, res.text


def test_non_brand_role_is_403(portal, tag_ok):
    pid = portal["add_product"]()
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["consumer"])
    assert res.status_code == 403, res.text


def test_product_with_no_image_and_no_text_is_422(portal, tag_ok):
    pid = portal["add_product"](thumbnail_url="", title="", title_ar="",
                                description="", description_ar="")
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 422, res.text


def test_worker_refusal_is_422_with_code(portal, tag_refused):
    pid = portal["add_product"]()
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 422, res.text
    err = res.json()["detail"]["error"]
    assert err["code"] == "IMAGE_FETCH_FAILED"
    assert "public" in err["message"]
    p = portal["get_product"](pid)
    assert json.loads(p.style_tags) == ["existing_human_tag"]  # nothing written


def test_worker_unavailable_is_503_retryable_no_writes(portal, tag_down):
    pid = portal["add_product"]()
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 503, res.text
    assert res.json()["detail"]["error"]["code"] == "TAGGING_UNAVAILABLE"
    p = portal["get_product"](pid)
    assert p.color_family == ""


def test_unconfigured_worker_is_503_not_fake_tags(portal, worker_env, monkeypatch):
    monkeypatch.setattr(config_mod.settings, "TAGGING_WORKER_URL", None, raising=False)
    pid = portal["add_product"]()
    res = portal["client"].post(f"/partner/products/{pid}/auto-tag",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 503, res.text
    assert res.json()["detail"]["error"]["reason"] == "tagging_not_configured"


def test_brand_alias_route_works(portal, tag_ok):
    pid = portal["add_product"]()
    res = portal["client"].post(f"/brand/products/{pid}/auto-tag",
                                headers=portal["headers"]["owner"])
    assert res.status_code == 200, res.text


# ───────────────────────── provider unit tests ─────────────────────────

def test_validate_accepts_real_worker_body():
    _, problem = _validate_worker_response(_worker_ok())
    assert problem is None


def test_validate_rejects_missing_disclosures():
    for mutate in (
        lambda b: b.pop("models"),
        lambda b: b.pop("disclaimer"),
        lambda b: b.update(quality="excellent"),
        lambda b: b["tags"][0].update(source="human"),
        lambda b: b["tags"][0].pop("confidence"),
        lambda b: b["models"]["gliner"].update(license="unknown"),
        lambda b: b.update(product_suggestions=None),
    ):
        body = _worker_ok()
        mutate(body)
        _, problem = _validate_worker_response(body)
        assert problem, body


def test_provider_http_boundary_maps_errors_and_sends_token(worker_env):
    """Mock ONLY the HTTP layer (AsyncClient) so the provider's real
    error-mapping and payload construction run."""
    import asyncio

    captured = {}

    class FakeResp:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload or {})
        def json(self):
            if self._payload is None:
                raise ValueError
            return self._payload

    class FakeClient:
        def __init__(self, timeout=None):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None):
            captured.update(url=url, headers=headers, payload=json)
            return FakeResp(self._next_status, self._next_payload)

    FakeClient._next_status = 200
    FakeClient._next_payload = _worker_ok()

    async def call():
        provider = TaggingProvider()
        with patch.object(httpx, "AsyncClient", FakeClient):
            return await provider._call_worker(
                "https://example.com/blazer.jpg",
                title="Blazer", description="navy wool",
                title_ar="", description_ar="صوف")

    result = asyncio.run(call())
    assert result["status"] == "completed"
    # dedicated token + full payload shape
    assert captured["url"] == "https://tagging-worker.test/tag"
    assert captured["headers"]["X-VTON-Admin"] == "test-admin-token"
    assert captured["payload"]["image_base64_or_url"] == "https://example.com/blazer.jpg"
    assert captured["payload"]["title"] == "Blazer"
    assert captured["payload"]["description_ar"] == "صوف"
    assert captured["payload"]["job_id"].startswith("tag_")
    assert "backend_call_seconds" in result

    # error mapping
    FakeClient._next_status = 422
    FakeClient._next_payload = {"detail": {"error": {"code": "IMAGE_FETCH_FAILED",
                                                     "message": "check public"}}}
    refused = asyncio.run(call())
    assert refused["reason"] == "worker_refused:IMAGE_FETCH_FAILED"
    assert refused["guidance"] == "check public"

    FakeClient._next_status = 500
    infra = asyncio.run(call())
    assert infra["reason"] == "tagging_worker_infra_error"

    FakeClient._next_status = 401
    auth = asyncio.run(call())
    assert auth["reason"] == "tagging_worker_auth_failure"


def test_provider_not_configured_is_honest():
    import asyncio
    provider = TaggingProvider()
    with patch.object(config_mod.settings, "TAGGING_WORKER_URL", None):
        result = asyncio.run(provider.tag_product(None, title="x"))
    assert result["tagging_available"] is False
    assert result["reason"] == "tagging_not_configured"
