"""A system default is never presented as a shopper's profile (defect D-3).

MEASURED DEFECT (2026-09-24, local stack, anonymous caller)
    POST /api/v1/stylist/chat {"prompt": "I need a smart casual outfit for an art
    gallery opening under $300"}
    -> "Here is your grounded Evening & Party ensemble tailored to your Smart
        Casual profile."

There is no profile on that request. "Smart Casual" is a system default that
``stylist_service`` used as a *matching input*; the prose then promoted it to a
fact about the shopper. Same class as the fabricated body measurements.

WHAT THESE TESTS PIN
  * anonymous      -> the answer must not claim a profile (and must say where the
                      direction came from);
  * profiled       -> a profile-backed claim is still allowed, so the fix cannot
                      be "delete the sentence everywhere";
  * conversation   -> a direction the shopper typed is attributed to the request,
                      not to a stored profile;
  * persisted      -> the source travels in the stored intent record, so a
                      reviewer can tell which claim was made;
  * mutation       -> forcing the source back to "profile" fails the anonymous
                      case (the test can fail, so its PASS means something).
"""
from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.stylist import StylistMessage
from backend.app.providers.orchestrator import MultiProviderAIOrchestrator
from backend.app.services.styling.attribution import (
    STYLE_SOURCE_CONVERSATION,
    STYLE_SOURCE_DEFAULT,
    STYLE_SOURCE_PROFILE,
    STYLE_SOURCE_UNKNOWN,
    resolve_style_source,
    style_attribution_phrase,
)
from backend.tests.conftest import TestingSessionLocal

PROMPT = "I need a smart casual outfit for an art gallery opening under $300"
PROFILE_CLAIM = re.compile(r"\byour\b[^.]{0,60}\bprofile\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _stub(engine: str = "CONFIT Grounded Styling Engine (Grounded & Resilient)"):
    """Let the real service/composer run; stub only the provider call."""

    async def _fake(self, **kwargs):
        return {
            "occasion": "Evening & Party",
            "detected_budget": 300.0,
            "aesthetic": "Smart Casual",
            "styling_advice_text": "Grounded advice.",
            "color_palette_advice": ["#1B1F3B"],
            "harmony_type": "Balanced",
            "provider_used": engine,
        }

    return patch.object(MultiProviderAIOrchestrator, "generate_styling_advice", new=_fake)


def _no_providers():
    """Run the REAL orchestrator with no provider configured.

    A first version of these tests stubbed the orchestrator's return value and
    then asserted the fallback PROSE — which the stub had replaced, so the
    assertion could never have been about the shipped sentence. This context
    manager disables the provider list instead: every provider is skipped, the
    real deterministic fallback writes the text, and no network call is possible.
    """
    from backend.app.core.config import settings

    return patch.object(settings, "AI_PROVIDERS", "")


def _stored_intent(message_id: int) -> dict:
    db = TestingSessionLocal()
    try:
        row = db.query(StylistMessage).filter(StylistMessage.id == message_id).one()
        return json.loads(row.intent_json or "{}")
    finally:
        db.close()


# ── the unit-level rule ───────────────────────────────────────────────────────
def test_resolve_style_source_matrix():
    assert resolve_style_source(profile_styles_present=False, prompt_drove_aesthetic=False) == STYLE_SOURCE_DEFAULT
    assert resolve_style_source(profile_styles_present=True, prompt_drove_aesthetic=False) == STYLE_SOURCE_PROFILE
    # The shopper's own words win the attribution even when a profile exists,
    # because the profile is not what produced this answer.
    assert resolve_style_source(profile_styles_present=True, prompt_drove_aesthetic=True) == STYLE_SOURCE_CONVERSATION


def test_only_the_profile_source_may_claim_a_profile():
    assert "your Quiet Luxury profile" in style_attribution_phrase("Quiet Luxury", STYLE_SOURCE_PROFILE)
    for source in (STYLE_SOURCE_DEFAULT, STYLE_SOURCE_CONVERSATION, STYLE_SOURCE_UNKNOWN):
        phrase = style_attribution_phrase("Quiet Luxury", source)
        assert not PROFILE_CLAIM.search(phrase), f"{source} produced a profile claim: {phrase!r}"


# ── the endpoint, anonymous ───────────────────────────────────────────────────
def test_anonymous_caller_is_never_told_they_have_a_profile(client):
    with _no_providers():
        r = client.post("/api/v1/stylist/chat", json={"prompt": PROMPT, "occasion": "work", "budget_limit": 300})
    assert r.status_code == 200, r.text
    body = r.json()

    content = body["content"]
    assert not PROFILE_CLAIM.search(content), f"fabricated profile claim: {content!r}"
    assert "no style profile is on file" in content, (
        "the answer should say out loud that no profile exists, got: " + content
    )

    source = body["intent_detected"].get("style_source")
    assert source in (STYLE_SOURCE_DEFAULT, STYLE_SOURCE_CONVERSATION, STYLE_SOURCE_UNKNOWN), source
    assert source != STYLE_SOURCE_PROFILE

    # and the claim is part of the persisted record, not just the response
    assert _stored_intent(body["id"]).get("style_source") == source


def test_anonymous_caller_who_states_a_direction_gets_it_attributed_to_the_request(client):
    with _no_providers():
        r = client.post("/api/v1/stylist/chat", json={"prompt": "make it minimalist for the office", "occasion": "work"})
    assert r.status_code == 200, r.text
    body = r.json()
    source = body["intent_detected"].get("style_source")
    assert source == STYLE_SOURCE_CONVERSATION, source
    assert "in this request" in body["content"], body["content"]
    assert not PROFILE_CLAIM.search(body["content"])


# ── the endpoint, profiled ────────────────────────────────────────────────────
def test_a_profile_backed_answer_may_still_claim_the_profile(client):
    """The fix must not be 'remove the sentence': a real profile still licenses it."""
    email = "attribution-profiled@example.com"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "Attr!2345", "full_name": "Attr"})
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]

    upsert = client.patch(
        "/api/v1/profile/preferences",
        json={"style_archetypes": ["Old Money"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upsert.status_code in (200, 201), upsert.text

    with _no_providers():
        r = client.post(
            "/api/v1/stylist/chat",
            json={"prompt": "an outfit for the office"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent_detected"].get("style_source") == STYLE_SOURCE_PROFILE, body["intent_detected"].get("style_source")
    assert "your Old Money profile" in body["content"], body["content"]


def test_a_direction_typed_in_the_request_outranks_the_stored_profile(client):
    email = "attribution-override@example.com"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "Attr!2345", "full_name": "Attr"})
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    client.patch(
        "/api/v1/profile/preferences",
        json={"style_archetypes": ["Old Money"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    with _no_providers():
        r = client.post(
            "/api/v1/stylist/chat",
            json={"prompt": "make it minimalist for the office"},
            headers={"Authorization": f"Bearer {token}"},
        )
    body = r.json()
    assert body["intent_detected"].get("style_source") == STYLE_SOURCE_CONVERSATION
    assert not PROFILE_CLAIM.search(body["content"]), body["content"]
