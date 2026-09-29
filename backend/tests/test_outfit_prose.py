"""Every outfit shown must be described, and never mis-described.

THE DEFECT
----------
`stylist_service` sent only `recommended_outfits[0]` to the model. A second
recommendation reached the shopper carrying a template string — "A cohesive
multi-brand ensemble combining structured Arket with..." — that never named
anything actually in it. Two looks shown, one described.

Fixed by sending the alternates in the SAME request (a second call would
double an already ~9s response) and splitting the reply here.
"""
from __future__ import annotations

import pytest

from backend.app.services.styling.outfit_prose import (
    attach_prose,
    is_grounded_in,
    split_outfit_prose,
)


def _outfit(title, brand="Reiss", description="template"):
    return {
        "items": [{"product_title": title, "brand_name": brand, "position": "dress"}],
        "description": description,
    }


# ── splitting ──────────────────────────────────────────────────────────────

def test_markers_are_stripped_from_the_main_answer():
    """The shopper must never see the scaffolding we asked the model for."""
    main, notes = split_outfit_prose(
        "The dress anchors the look.\n\nOUTFIT_2: The tuxedo sharpens it."
    )
    assert "OUTFIT_2" not in main
    assert main == "The dress anchors the look."
    assert notes == {2: "The tuxedo sharpens it."}


@pytest.mark.parametrize("line", [
    "OUTFIT_2: A sharper evening option.",
    "**OUTFIT_2** - A sharper evening option.",
    "Outfit 2 — A sharper evening option.",
    "outfit_2 : A sharper evening option.",
    "  ## OUTFIT 2: A sharper evening option.",
])
def test_formatting_variations_are_all_understood(line):
    """Forgiving about format, strict about grounding — models vary."""
    _, notes = split_outfit_prose("Main answer.\n" + line)
    assert notes.get(2) == "A sharper evening option."


def test_a_repeated_marker_does_not_overwrite():
    _, notes = split_outfit_prose(
        "Main.\nOUTFIT_2: First sentence.\nOUTFIT_2: Second sentence."
    )
    assert notes[2] == "First sentence."


def test_no_markers_leaves_the_text_untouched():
    main, notes = split_outfit_prose("Just a normal answer with no markers.")
    assert main == "Just a normal answer with no markers."
    assert notes == {}


def test_empty_input_is_safe():
    assert split_outfit_prose("") == ("", {})
    assert split_outfit_prose(None) == ("", {})


# ── grounding: the guard that keeps this from hallucinating ────────────────

def test_a_sentence_naming_the_real_garment_is_grounded():
    outfit = _outfit("Tuxedo Peak Lapel Evening Dinner Jacket")
    assert is_grounded_in("The Tuxedo jacket sharpens the line.", outfit) is True


def test_a_sentence_naming_nothing_real_is_rejected():
    """The model describes several looks at once and can cross-attribute."""
    outfit = _outfit("Tuxedo Peak Lapel Evening Dinner Jacket")
    assert is_grounded_in("Something vague and pleasant.", outfit) is False


def test_an_outfit_with_no_items_cannot_ground_anything():
    """Refuse rather than accept blindly when there is nothing to check."""
    assert is_grounded_in("Any sentence at all.", {"items": []}) is False


# ── attaching ──────────────────────────────────────────────────────────────

def test_a_grounded_sentence_replaces_the_template():
    outfits = [_outfit("Silk Slip Dress"), _outfit("Tuxedo Peak Lapel Jacket")]
    attached = attach_prose(outfits, {2: "The Tuxedo jacket adds structure."})
    assert attached == 1
    assert outfits[1]["description"] == "The Tuxedo jacket adds structure."
    assert outfits[1]["description_source"] == "ai"


def test_an_ungrounded_sentence_leaves_the_template_in_place():
    """A wrong description is worse than a generic one."""
    outfits = [_outfit("Silk Slip Dress"), _outfit("Tuxedo Peak Lapel Jacket")]
    attached = attach_prose(outfits, {2: "Entirely unrelated prose."})
    assert attached == 0
    assert outfits[1]["description"] == "template"
    assert "description_source" not in outfits[1]


def test_outfit_one_is_never_overwritten():
    """Outfit 1 IS the main answer; its description must not be replaced."""
    outfits = [_outfit("Silk Slip Dress"), _outfit("Tuxedo Jacket")]
    attach_prose(outfits, {1: "Silk Slip Dress note."})
    assert outfits[0]["description"] == "template"


def test_an_index_past_the_end_is_ignored():
    outfits = [_outfit("Silk Slip Dress")]
    assert attach_prose(outfits, {5: "Silk Slip Dress note."}) == 0


def test_the_service_sends_the_alternates():
    """Pins the wiring: sending only outfit[0] is the defect itself."""
    import inspect

    from backend.app.services import stylist_service

    source = inspect.getsource(stylist_service)
    assert "alternate_outfits=recommended_outfits[1:]" in source
    assert "split_outfit_prose" in source
