"""Which engine answered is part of the record, not a log detail.

Root cause (audit 2026-09-24): the orchestrator labelled every answer
truthfully — a real call returns ``"<Provider> <model actually served>"``
(``test_ai_model_truthfulness.py`` pins the model), and a total provider
failure returns ``"CONFIT Grounded Styling Engine"``. ``stylist_service`` then
**dropped that label**: it was not written to the message, and not returned by
``POST /api/v1/stylist/chat``. Two consequences, both invisible before this
test existed:

* the consumer drawer presented deterministic fallback prose under the header
  "CONFIT Senior AI Stylist" while ``/catalog/capabilities`` still reported
  ``ai_stylist_live = true`` — an AI claim with no engine behind it;
* a reviewer could not tell a provider answer from fallback prose at the API
  boundary at all, i.e. the "record requested/actual engine" requirement had no
  observable implementation.

These tests drive the real endpoint and then read the stored row back, so they
fail if the propagation is removed anywhere on that path.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.stylist import StylistMessage
from backend.app.providers.orchestrator import MultiProviderAIOrchestrator
from backend.tests.conftest import TestingSessionLocal

#: A prompt with no signal-bearing styling token, so the service takes the
#: clarification branch — see StylingComposer.parse_intent (is_ambiguous).
VAGUE_PROMPT = "please help"
SIGNALLED_PROMPT = "a formal wedding outfit under $500"


def _stub_orchestrator(engine: str, text: str = "Grounded styling advice for your look."):
    """Replace only the provider call; the rest of the service path is real."""

    async def _fake(self, **kwargs):
        return {
            "occasion": "Wedding",
            "detected_budget": 500.0,
            "aesthetic": "Quiet Luxury",
            "styling_advice_text": text,
            "color_palette_advice": ["#1B1F3B"],
            "harmony_type": "Balanced",
            "provider_used": engine,
        }

    return patch.object(MultiProviderAIOrchestrator, "generate_styling_advice", new=_fake)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _stored_message(message_id: int) -> StylistMessage:
    db = TestingSessionLocal()
    try:
        row = db.query(StylistMessage).filter(StylistMessage.id == message_id).first()
        assert row is not None, "assistant message must be persisted"
        return row
    finally:
        db.close()


def test_provider_answer_reports_the_engine_that_answered(client):
    with _stub_orchestrator("NVIDIA meta/llama-3.1-70b-instruct"):
        r = client.post("/api/v1/stylist/chat", json={"prompt": SIGNALLED_PROMPT})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body.get("engine") == "NVIDIA meta/llama-3.1-70b-instruct", (
        f"the engine label must survive to the API boundary, got {body.get('engine')!r}"
    )

    stored = json.loads(_stored_message(body["id"]).intent_json or "{}")
    assert stored.get("engine") == "NVIDIA meta/llama-3.1-70b-instruct", (
        "the engine must also be persisted with the message"
    )


def test_grounded_fallback_is_reported_as_the_fallback_not_as_ai(client):
    grounded = "CONFIT Grounded Styling Engine (Grounded & Resilient)"
    with _stub_orchestrator(grounded):
        r = client.post("/api/v1/stylist/chat", json={"prompt": SIGNALLED_PROMPT})
    assert r.status_code == 200, r.text
    body = r.json()

    # The client needs to be able to tell fallback from a model answer; the
    # drawer renders a distinct label for exactly this value.
    assert body.get("engine") == grounded
    assert "Grounded Styling Engine" in str(body.get("engine"))
    stored = json.loads(_stored_message(body["id"]).intent_json or "{}")
    assert stored.get("engine") == grounded


def test_clarifying_question_states_that_no_engine_was_used(client):
    """No provider is called on the clarify path — say so, don't leave it blank."""
    r = client.post("/api/v1/stylist/chat", json={"prompt": VAGUE_PROMPT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("engine") == "none", (
        f"a clarifying question must not look like a generated answer, got {body.get('engine')!r}"
    )


def test_engine_field_is_declared_in_the_openapi_contract(client):
    """A client cannot rely on a field the published schema does not declare."""
    schema = client.get("/openapi.json").json()
    props = schema["components"]["schemas"]["StylistMessageOut"]["properties"]
    assert "engine" in props, "StylistMessageOut must declare `engine`"
