"""Upload safety and per-user image budget — FR-008/009, SC-005, STY-08/09.

* An image the classifier blocks is refused (422) and never reaches analysis.
* A classifier that cannot give a verdict fails CLOSED (503) for image turns.
* A deployment without a classifier stands down visibly (same policy as wardrobe).
* Image-carrying turns have their own per-caller budget; text turns are unaffected.
* Refused and over-budget requests leave no transcript rows.
"""
from __future__ import annotations

import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from backend.app.core.config import settings
from backend.app.core.rate_limit import limiter
from backend.app.services.content_safety_service import SafetyVerdict, Severity, content_safety_service
from backend.tests.conftest import TestingSessionLocal


def _png_url(colour=(27, 31, 59)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), colour).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def safety_configured(monkeypatch):
    monkeypatch.setattr(type(content_safety_service), "configured", property(lambda self: True))


@pytest.fixture
def no_text_provider(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDERS", "none")


@pytest.fixture
def vision_probe(monkeypatch):
    """Records whether the analysis step ran at all."""
    from backend.app.services import stylist_service as svc
    from backend.app.services.stylist_vision import VisionAnalysis

    calls = {"n": 0}

    async def fake(images, shopper_request):
        calls["n"] += 1
        return VisionAnalysis(available=False, reason="stub")

    monkeypatch.setattr(svc, "analyze_images", fake)
    return calls


def _message_count() -> int:
    db = TestingSessionLocal()
    try:
        return db.execute(text("select count(*) from stylist_messages")).scalar()
    finally:
        db.close()


def _block_verdict():
    return SafetyVerdict(safe=False, measured=True, severity=Severity.HARD_BLOCK,
                         categories=["Sexual Content"], model_id="nvidia/test-safety")


class TestUploadSafety:
    def test_blocked_image_is_refused_and_never_analysed(
        self, client: TestClient, safety_configured, no_text_provider, vision_probe, monkeypatch
    ):
        async def blocked(image_url, *, caption="", context="upload"):
            return _block_verdict()

        monkeypatch.setattr(content_safety_service, "check_image", blocked)
        before = _message_count()
        res = client.post("/api/v1/stylist/chat", json={"prompt": "look", "images": [_png_url()]})
        assert res.status_code == 422, res.text
        assert "categor" not in res.text.lower(), "the refusal never echoes the category"
        assert vision_probe["n"] == 0, "a blocked image must not reach the vision model"
        assert _message_count() == before, "nothing is persisted for a refused image"

    def test_unmeasured_safety_check_fails_closed(
        self, client: TestClient, safety_configured, no_text_provider, vision_probe, monkeypatch
    ):
        async def unmeasured(image_url, *, caption="", context="upload"):
            return SafetyVerdict(safe=True, measured=False, error="timeout")

        monkeypatch.setattr(content_safety_service, "check_image", unmeasured)
        res = client.post("/api/v1/stylist/chat", json={"prompt": "look", "images": [_png_url()]})
        assert res.status_code == 503
        assert vision_probe["n"] == 0, "an unscreened image must not be analysed"

    def test_safe_image_proceeds_and_is_screened_once_per_image(
        self, client: TestClient, safety_configured, no_text_provider, vision_probe, monkeypatch
    ):
        seen = []

        async def safe(image_url, *, caption="", context="upload"):
            seen.append(context)
            return SafetyVerdict(safe=True, measured=True, model_id="nvidia/test-safety")

        monkeypatch.setattr(content_safety_service, "check_image", safe)
        res = client.post("/api/v1/stylist/chat", json={
            "prompt": "look", "images": [_png_url(), _png_url((1, 2, 3))],
        })
        assert res.status_code == 200, res.text
        assert seen == ["stylist_upload", "stylist_upload"]
        assert vision_probe["n"] == 1
        db = TestingSessionLocal()
        try:
            stored = db.execute(text(
                "select count(*) from stylist_messages where content like '%base64,%' "
                "or intent_json like '%base64,%' or recommendations_json like '%base64,%'"
            )).scalar()
        finally:
            db.close()
        assert stored == 0, "SC-005: no base64 image may be stored in the database"

    def test_unconfigured_classifier_stands_down_visibly(
        self, client: TestClient, no_text_provider, vision_probe, monkeypatch
    ):
        monkeypatch.setattr(type(content_safety_service), "configured", property(lambda self: False))

        async def must_not_run(*a, **k):  # pragma: no cover - would be a bug
            raise AssertionError("classifier called while unconfigured")

        monkeypatch.setattr(content_safety_service, "check_image", must_not_run)
        res = client.post("/api/v1/stylist/chat", json={"prompt": "look", "images": [_png_url()]})
        assert res.status_code == 200
        assert vision_probe["n"] == 1

    def test_text_turn_never_calls_the_image_classifier(
        self, client: TestClient, safety_configured, no_text_provider, monkeypatch
    ):
        async def must_not_run(*a, **k):  # pragma: no cover
            raise AssertionError("text-only turn must not screen an image")

        monkeypatch.setattr(content_safety_service, "check_image", must_not_run)
        res = client.post("/api/v1/stylist/chat", json={"prompt": "smart casual dinner"})
        assert res.status_code == 200


class TestImageBudget:
    @pytest.fixture
    def enforced_limits(self, monkeypatch):
        limiter.reset()
        limiter.enabled = True
        monkeypatch.setattr(settings, "STYLIST_IMAGE_TURNS_PER_HOUR", 2)
        yield
        limiter.enabled = False
        limiter.reset()

    def test_image_turns_are_capped_per_caller(
        self, client: TestClient, enforced_limits, no_text_provider, vision_probe, monkeypatch
    ):
        monkeypatch.setattr(type(content_safety_service), "configured", property(lambda self: False))
        headers = {"X-Session-Token": "budget-caller-a"}
        codes = [
            client.post("/api/v1/stylist/chat", json={"prompt": "look", "images": [_png_url()]}, headers=headers).status_code
            for _ in range(3)
        ]
        assert codes[:2] == [200, 200]
        assert codes[2] == 429

    def test_text_turns_are_not_counted_against_the_image_budget(
        self, client: TestClient, enforced_limits, no_text_provider, monkeypatch
    ):
        monkeypatch.setattr(type(content_safety_service), "configured", property(lambda self: False))
        headers = {"X-Session-Token": "budget-caller-b"}
        for _ in range(3):
            res = client.post("/api/v1/stylist/chat", json={"prompt": "smart casual dinner"}, headers=headers)
            assert res.status_code == 200
