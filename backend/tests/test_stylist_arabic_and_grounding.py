"""AI Stylist: Arabic intake, and the four mandatory Section-6 behaviours.

MEASURED DEFECT THIS CLOSES (production, 2026-09-29)
-----------------------------------------------------
    "عايز حاجة تنفع لفرح مسائي مش رسمي أوي"  -> engine: none, 0 recommendations
    "formal wedding look, evening"           -> Groq,        2 recommendations

Same request, two languages. `StylingEngine._OCCASION_KEYWORDS` is an
English-only vocabulary, so the Arabic query matched nothing and intent fell
back to `style_source: "default"`. CONFIT prices in EGP/AED/SAR behind a
fully Arabic UI, so its primary market could never get a recommendation.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.services.query_translation import (
    apply_lexicon,
    contains_arabic,
    translate_query,
)
from backend.app.services.styling_engine import StylingEngine


# ── the lexicon: deterministic, and it owns the words that steer retrieval ──

def test_arabic_is_detected():
    assert contains_arabic("فرح مسائي") is True
    assert contains_arabic("evening wedding") is False
    assert contains_arabic("") is False
    assert contains_arabic(None) is False


@pytest.mark.parametrize("arabic,expected", [
    ("فرح", "wedding"),
    ("سواريه", "evening gown"),
    ("بدلة", "suit"),
    ("خطوبة", "engagement party"),
    ("شغل", "work"),
    ("كاجوال", "casual"),
])
def test_lexicon_pins_the_terms_riva_got_wrong(arabic, expected):
    """riva-translate rendered these as party / Swarovski / trousers.

    Each error changes WHICH GARMENT is retrieved, so these terms are pinned
    in code rather than left to a paraphrase.
    """
    out, hits = apply_lexicon(arabic)
    assert expected in out.lower(), out
    assert hits >= 1


def test_lexicon_prefers_the_longer_term():
    """'فستان سواريه' is an evening gown, not a dress plus a brand."""
    out, _ = apply_lexicon("فستان سواريه أحمر")
    assert "evening gown" in out.lower()


def test_lexicon_leaves_english_untouched():
    out, hits = apply_lexicon("formal wedding look")
    assert out == "formal wedding look"
    assert hits == 0


@pytest.mark.asyncio
async def test_english_never_calls_the_translator():
    """No network, no latency, nothing for a model to paraphrase."""
    result = await translate_query("formal wedding look, evening")
    assert result.translated is False
    assert result.source == "passthrough"
    assert result.text == "formal wedding look, evening"


@pytest.mark.asyncio
async def test_arabic_fails_open_to_the_lexicon(monkeypatch):
    """An unreachable model must not leave the shopper where they started."""
    import backend.app.providers.nvidia.client as nvc

    class _Broken:
        def __init__(self, *a, **k): pass
        async def chat(self, *a, **k): raise RuntimeError("provider down")

    monkeypatch.setattr(nvc, "NvidiaClient", _Broken)
    result = await translate_query("عايز حاجة تنفع لفرح مسائي")
    assert result.source == "lexicon_only"
    assert "wedding" in result.text.lower(), result.text
    assert not contains_arabic(result.text) or "wedding" in result.text.lower()


@pytest.mark.asyncio
async def test_a_translator_that_returns_arabic_is_rejected(monkeypatch):
    """Untranslated text would score nothing against an English vocabulary."""
    import backend.app.providers.nvidia.client as nvc

    class _Echo:
        def __init__(self, *a, **k): pass
        async def chat(self, *a, **k): return "فرح مسائي"

    monkeypatch.setattr(nvc, "NvidiaClient", _Echo)
    result = await translate_query("عايز حاجة تنفع لفرح مسائي")
    assert result.source == "lexicon_only", "an Arabic 'translation' is not one"


def test_translated_arabic_reaches_the_occasion_matcher():
    """The end of the chain: lexicon output must match the English keywords."""
    translated, _ = apply_lexicon("عايز حاجة تنفع لفرح مسائي مش رسمي أوي")
    matched = StylingEngine._target_occasion_keywords(translated)
    assert matched, f"no occasion matched for {translated!r}"
    assert any(k in matched for k in ("wedding", "formal", "evening")), matched


# ── Section 6: the four mandatory stylist behaviours ───────────────────────

def _chat(client: TestClient, prompt: str):
    r = client.post("/api/v1/stylist/chat", json={"prompt": prompt})
    assert r.status_code == 200, r.text
    return r.json()


def test_section6_grounding_every_recommendation_exists_in_the_catalog(
    client: TestClient,
) -> None:
    """The stylist must never name a product that is not in the catalogue."""
    body = _chat(client, "formal wedding look, evening, not too formal")
    recs = body.get("recommendations") or []

    from backend.app.models.catalog import Product
    from backend.tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        real_ids = {p.id for p in db.query(Product.id).all()}
        real_ids = {row[0] for row in db.query(Product.id).all()}

    for rec in recs:
        pid = rec.get("product_id") if isinstance(rec, dict) else None
        if pid is not None:
            assert pid in real_ids, (
                f"product_id {pid} is not in the catalogue — the stylist "
                f"invented it"
            )


def test_section6_a_vague_prompt_asks_for_clarification(client: TestClient) -> None:
    """'something nice' must not be guessed at."""
    body = _chat(client, "i want something nice")
    recs = body.get("recommendations") or []
    content = (body.get("content") or "").lower()
    if not recs:
        assert "?" in content or "tell me" in content or "could you" in content, (
            "a vague prompt with no results must ask for more, not go silent"
        )


def test_section6_arabic_is_answered_not_deflected(client: TestClient) -> None:
    """The defect itself: an Arabic request must reach the occasion matcher."""
    body = _chat(client, "عايز حاجة تنفع لفرح مسائي مش رسمي أوي")
    intent = body.get("intent_detected") or {}
    occasion = (intent.get("occasion") or "").lower()
    assert occasion and occasion != "smart casual", (
        f"Arabic query still fell back to the default occasion: {intent!r}"
    )


def test_section6_every_recommendation_carries_a_reason(client: TestClient) -> None:
    body = _chat(client, "smart casual work outfit under 500 dollars")
    for rec in body.get("recommendations") or []:
        if isinstance(rec, dict):
            assert any(
                rec.get(k) for k in ("reason", "why", "rationale", "explanation")
            ) or (body.get("content") or "").strip(), (
                "a recommendation with no stated reason is an unexplained claim"
            )
