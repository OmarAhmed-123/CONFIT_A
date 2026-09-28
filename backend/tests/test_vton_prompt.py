"""Try-on prompt construction: literal, neutral, and honest about its reach."""
from __future__ import annotations

import pytest

from backend.app.providers.vton.prompt import (
    build_edit_prompt,
    garment_description,
    identity_directive,
)
from backend.app.providers.vton.registry import GarmentCategory as C


def test_marketing_noise_is_stripped():
    """A season code is not a garment. Neither is 'NEW IN'."""
    out = garment_description(title="Men's NEW IN Wool Blazer AW26", category=C.OUTERWEAR)
    low = out.lower()
    for junk in ("new in", "new ", "aw26", "men's", "mens"):
        assert junk not in low, f"{junk!r} survived in {out!r}"
    assert "wool" in low and "blazer" in low


def test_repeated_words_are_said_once():
    """colour='Silk' plus a title containing 'Silk' produced 'Silk Silk'.

    A repeated adjective reads as emphasis to a diffusion model, so the
    duplicate is not cosmetic — it skews the render.
    """
    out = garment_description(
        title="Silk Slip Maxi Dress", colour="Crimson", material="Silk", category=C.DRESS
    )
    assert out.lower().split().count("silk") == 1, out


def test_colour_and_material_lead():
    """The attributes these models most often lose go first."""
    out = garment_description(
        title="Double-Breasted Blazer", colour="Navy", material="Wool", category=C.OUTERWEAR
    )
    assert out.lower().startswith("navy wool"), out


@pytest.mark.parametrize("category,fragment", [
    (C.UPPER, "upper body"),
    (C.LOWER, "lower body"),
    (C.DRESS, "one-piece"),
    (C.OUTERWEAR, "outer layer"),
])
def test_placement_states_the_region_without_naming_the_body(category, fragment):
    out = garment_description(title="Item", category=category).lower()
    assert fragment in out


def test_wording_is_gender_neutral():
    """The photo carries the wearer; asserting it in words invites 'correction'."""
    for title in ("Men's Oxford Shirt", "Women's Silk Blouse"):
        out = garment_description(title=title, category=C.UPPER).lower()
        for term in ("man", "woman", "male", "female", "men", "women", "lady"):
            assert term not in out.split(), f"{term!r} leaked from {title!r}: {out!r}"


def test_empty_input_never_yields_an_empty_string():
    """Some Spaces read '' as 'describe anything' and drift."""
    assert garment_description().strip() != ""
    assert garment_description(title=None, colour=None) == "garment"


def test_description_is_truncated_on_a_word_boundary():
    out = garment_description(title="word " * 200, category=C.UPPER, max_chars=60)
    assert len(out) <= 60 + len(", worn on the upper body")
    assert not out.rstrip(", worn on the upper body").endswith("wor")


def test_identity_directive_is_stable_and_covers_the_named_risks():
    a, b = identity_directive(), identity_directive()
    assert a == b, "the directive must be identical on every call"
    low = a.lower()
    for risk in ("face", "hair", "skin tone", "body shape", "pose", "background"):
        assert risk in low, f"{risk} not constrained"
    for verb in ("reshape", "slim", "smooth", "retouch"):
        assert verb in low, f"{verb} not forbidden"


def test_edit_prompt_leads_with_the_garment_then_constrains_identity():
    prompt = build_edit_prompt(title="Silk Maxi Dress", category=C.DRESS, colour="Crimson")
    assert prompt.index("Crimson") < prompt.index("Replace only the clothing"), (
        "instruction models weight early tokens; the garment must come first"
    )
    assert identity_directive() in prompt


def test_the_same_builder_serves_menswear_and_womenswear():
    """No branching on gender: identical structure for both."""
    a = garment_description(title="Oxford Shirt", category=C.UPPER, colour="White")
    b = garment_description(title="Silk Blouse", category=C.UPPER, colour="White")
    assert a.endswith("worn on the upper body")
    assert b.endswith("worn on the upper body")
    assert a.startswith("White") and b.startswith("White")
