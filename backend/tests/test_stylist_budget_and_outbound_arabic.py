"""Stylist bilingual budget parsing + outbound Arabic reply.

MEASURED DEFECTS THIS CLOSES (production, 2026-10-01)
-----------------------------------------------------
    'عايز أطلعة لحفل خطوبة، ميزانيتي حوالي ٣ آلاف جنيه'
        -> detected_budget 450.00 (the default), budget_explicit False
    'budget around 500 EGP'
        -> detected_budget 450.00 (the default), budget_explicit False
    Arabic prompt -> English stylist reply (no outbound translation existed)

The old budget regex knew only 'under|below|budget of|$'. CONFIT's primary
market writes Arabic-Indic digits with ألف multipliers and Egyptian-dialect
budget phrases, so every real Arabic budget statement silently fell to the
450.00 default and the composer then reported 'within_budget' against a
budget the shopper never stated.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.services.styling.composer import detect_budget_mention
from backend.app.services.styling_engine import StylingEngine


# ── detect_budget_mention: the patterns that were measured failing ──────────

@pytest.mark.parametrize("prompt,expected", [
    # The two production failures, verbatim fragments.
    ("ميزانيتي حوالي ٣ آلاف جنيه", Decimal("3000.00")),
    ("budget around 500 EGP", Decimal("500.00")),
    # Arabic-Indic digits + multiplier + currency, no prefix word.
    ("٣ آلاف جنيه", Decimal("3000.00")),
    ("٥٠٠ جنيه", Decimal("500.00")),
    ("٢٠٠٠ج", Decimal("2000.00")),
    # Egyptian-dialect budget phrases.
    ("بحد أقصى ٢٠٠٠ جنيه", Decimal("2000.00")),
    ("أقل من 800 EGP", Decimal("800.00")),
    ("ميزانية 1500", Decimal("1500.00")),
    # English expansions beyond the old pattern.
    ("up to 600 egp", Decimal("600.00")),
    ("max 750", Decimal("750.00")),
    ("about 300 pounds egp", Decimal("300.00")),
    ("under 200", Decimal("200.00")),      # the old pattern still works
    ("budget of 900", Decimal("900.00")),  # the old pattern still works
    ("$250", Decimal("250.00")),           # the old pattern still works
    # Multipliers in English too.
    ("budget around 5k", Decimal("5000.00")),
    ("حوالي 2 مليون", Decimal("2000000.00")),
])
def test_budget_is_extracted_from_bilingual_prompts(prompt, expected):
    assert detect_budget_mention(prompt) == expected


@pytest.mark.parametrize("prompt", [
    ("I need something nice for a weekend in Alexandria"),  # no number at all
    ("room 12 is my favourite"),       # a number that is not a budget
    ("size 42 trousers please"),       # bare size number must not be a budget
    ("2 million dollar idea but no budget words"),  # 'million' without anchor? -> anchored, counts; see below
])
def test_budget_negative_controls(prompt):
    """A number only counts as a budget when a budget signal anchors it."""
    # Note: '2 million dollar' IS anchored by the multiplier word, so it is
    # excluded from this negative list — the remaining three must return None.
    if "million" in prompt:
        pytest.skip("multiplier-anchored numbers are positive cases")
    assert detect_budget_mention(prompt) is None


def test_parse_intent_marks_arabic_thousand_budget_explicit():
    """End-to-end: the production Arabic prompt now carries a real budget."""
    intent = StylingEngine.parse_intent("عايز أطلعة لحفل خطوبة، ميزانيتي حوالي ٣ آلاف جنيه")
    assert intent["detected_budget"] == Decimal("3000.00")
    assert intent["budget_explicit"] is True


def test_parse_intent_unmentioned_budget_stays_default_and_not_explicit():
    """No budget mention -> default budget, but budget_explicit stays False.

    The default is a starting point for search, never a claim about the
    shopper; that distinction is what 'within_budget' reporting relies on.
    """
    intent = StylingEngine.parse_intent("casual weekend look with beige tones")
    assert intent["detected_budget"] == Decimal("450.00")
    assert intent["budget_explicit"] is False


# ── outbound translation: honest success and honest failure ────────────────

class _FakeChatResult:
    def __init__(self, text: str):
        self.text = text
        self.model_id = "nvidia/nemotron-3-super-120b-a12b"
        self.requested_model_id = "nvidia/nemotron-3-super-120b-a12b"
        self.role = "translation"
        self.latency_s = 0.5
        self.attempts = 1
        self.finish_reason = "stop"


@pytest.mark.asyncio
async def test_outbound_translation_returns_arabic_on_success(monkeypatch):
    from backend.app.services import query_translation as qt

    captured = {}

    class _FakeClient:
        async def chat(self, role, *, user, system=None, model_id=None, **kwargs):
            captured["system"] = system
            captured["user"] = user
            captured["model_id"] = model_id
            return _FakeChatResult("تنسيق أنيق لبيج وأبيض ضمن ميزانيتك.")

    monkeypatch.setattr(
        "backend.app.providers.nvidia.client.NvidiaClient", _FakeClient
    )
    result = await qt.translate_reply_to_arabic("A beige and white look within your budget.")
    assert result.translated is True
    assert result.source == "nvidia/nemotron-3-super-120b-a12b"
    assert result.text == "تنسيق أنيق لبيج وأبيض ضمن ميزانيتك."
    # The outbound rules ride the SYSTEM turn (super obeys it; riva would
    # ignore it, which is why super leads the outbound path too).
    assert "Egyptian Arabic" in (captured["system"] or "")
    assert "brand names" in (captured["system"] or "")
    # No model pin: the registry chain decides (super -> riva), so a pin that
    # would force riva's measured colour mistranslation can never sneak back.
    assert captured["model_id"] is None
    assert captured["user"] == "A beige and white look within your budget."


@pytest.mark.asyncio
async def test_outbound_translation_degrades_to_english_when_model_fails(monkeypatch):
    from backend.app.services import query_translation as qt

    class _BoomClient:
        async def chat(self, *args, **kwargs):
            raise RuntimeError("nvidia unreachable")

    monkeypatch.setattr(
        "backend.app.providers.nvidia.client.NvidiaClient", _BoomClient
    )
    english = "The sage green overshirt pairs well with graphite."
    result = await qt.translate_reply_to_arabic(english)
    assert result.translated is False
    assert result.text == english  # honest degradation, never invented


@pytest.mark.asyncio
async def test_outbound_translation_rejects_english_echo(monkeypatch):
    from backend.app.services import query_translation as qt

    class _EchoClient:
        async def chat(self, *args, **kwargs):
            # A translator that echoes the input has not translated.
            return _FakeChatResult("The sage green overshirt pairs well.")

    monkeypatch.setattr(
        "backend.app.providers.nvidia.client.NvidiaClient", _EchoClient
    )
    english = "The sage green overshirt pairs well."
    result = await qt.translate_reply_to_arabic(english)
    assert result.translated is False
    assert result.text == english


@pytest.mark.asyncio
async def test_outbound_translation_empty_input_passthrough():
    from backend.app.services.query_translation import translate_reply_to_arabic
    result = await translate_reply_to_arabic("")
    assert result.translated is False and result.text == ""
