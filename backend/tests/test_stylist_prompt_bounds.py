"""The AI stylist prompt bound — cost protection that a shopper cannot trip.

THE GAP (§13–§16 of the closure brief)
--------------------------------------
`StylistPromptRequest.prompt` was `str` with **no maximum**. The endpoint accepts
anonymous callers, spends provider quota per call and writes a row per accepted
call, so one request could carry an arbitrarily large body. Nothing in the
repository required a limit: the closest thing to a requirement was the previous
acceptance report, which recorded the absence as an open item.

THE DECISION
------------
`STYLIST_PROMPT_MAX_CHARS = 2000`, labelled **ENGINEERING SAFETY DEFAULT** in the
schema, because no product requirement exists. Chosen against measured production
usage on 2026-09-24 (71 user prompts; p50 53, p95 146, p99 240, max 240 characters;
none above 1000), so it cannot truncate observed behaviour while it caps abuse.

WHAT THESE TESTS PROTECT
------------------------
  1. The boundary behaves: 2000 accepted, 2001 refused, in CHARACTERS (Arabic is
     one character per letter, not four bytes).
  2. A refused request costs nothing: no stylist message row is written, so no
     provider call happened. That is the point of the bound — not the status code.
  3. The contract is discoverable: the limit is published in the OpenAPI schema, so
     a client can read it instead of learning it from a rejection.
  4. The frontend cap and the API cap are the same number (see
     `frontend/src/i18n/promptBounds.ts` and the guard at the end of this file).

Mutation control (CONFIT_evidence/45-*): with `max_length` removed from the schema,
`test_one_character_over_the_limit_is_refused` and the cost test must fail.
"""
import pytest

from backend.app.schemas.stylist import STYLIST_PROMPT_MAX_CHARS, StylistPromptRequest


@pytest.fixture
def db_session():
    """A session on the suite's own database (same engine the app is bound to)."""
    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _chat(client, prompt, **extra):
    return client.post("/api/v1/stylist/chat", json={"prompt": prompt, **extra})


# ── the boundary, at the model level (no HTTP, no rate-limit interference) ────

def test_the_limit_is_2000_and_is_documented_as_an_engineering_default():
    assert STYLIST_PROMPT_MAX_CHARS == 2000
    schema = StylistPromptRequest.model_json_schema()
    described = schema["properties"]["prompt"]["description"]
    assert str(STYLIST_PROMPT_MAX_CHARS) in described
    assert "engineering safety default" in described.lower(), (
        "the bound must say what it is: an engineering decision, not a product rule"
    )


def test_a_prompt_at_the_limit_is_accepted():
    assert StylistPromptRequest(prompt="x" * STYLIST_PROMPT_MAX_CHARS).prompt


def test_one_character_over_the_limit_is_refused():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        StylistPromptRequest(prompt="x" * (STYLIST_PROMPT_MAX_CHARS + 1))


def test_the_limit_counts_characters_not_bytes():
    """Arabic must not be penalised by a byte-based bound."""
    arabic = "أ" * STYLIST_PROMPT_MAX_CHARS
    assert len(arabic.encode("utf-8")) > STYLIST_PROMPT_MAX_CHARS * 1.5   # it really is multibyte
    assert StylistPromptRequest(prompt=arabic).prompt == arabic


def test_an_empty_prompt_is_refused():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        StylistPromptRequest(prompt="")


# ── the property that matters over HTTP: a refused request spends nothing ─────

def test_an_over_long_prompt_is_refused_without_writing_anything(client, db_session):
    from backend.app.models.stylist import StylistMessage

    before = db_session.query(StylistMessage).count()
    res = _chat(client, "x" * (STYLIST_PROMPT_MAX_CHARS + 1))
    assert res.status_code == 422, res.text
    after = db_session.query(StylistMessage).count()
    assert after == before, (
        "a rejected prompt wrote a message row — the request reached the service, so it "
        "may already have spent provider quota"
    )


def test_a_prompt_at_the_limit_is_answered(client, db_session):
    """The positive control for the test above: the same path DOES write on success."""
    from backend.app.models.stylist import StylistMessage

    before = db_session.query(StylistMessage).count()
    res = _chat(client, "خ" * STYLIST_PROMPT_MAX_CHARS, occasion="Work")
    assert res.status_code == 200, res.text
    assert db_session.query(StylistMessage).count() > before


# ── the frontend cap must not drift from the API cap ─────────────────────────

def test_the_frontend_cap_matches_the_api_cap():
    """One number, two languages.

    A UI cap that is stricter than the API hides valid requests; a looser one lets a
    shopper type a request the server will refuse. Either way the two must agree, and
    nothing else in CI compares a TypeScript constant with a Python one.
    """
    import re
    from pathlib import Path

    ts = Path(__file__).resolve().parents[2] / "frontend/src/i18n/promptBounds.ts"
    if not ts.exists():                                   # backend-only checkouts
        import pytest
        pytest.skip("frontend source not present in this checkout")
    match = re.search(r"STYLIST_PROMPT_MAX_CHARS\s*=\s*(\d+)", ts.read_text(encoding="utf-8"))
    assert match, "the frontend constant could not be found"
    assert int(match.group(1)) == STYLIST_PROMPT_MAX_CHARS
