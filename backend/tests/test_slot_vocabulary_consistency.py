"""The layering engine and the try-on contract must speak one vocabulary.

THE DEFECT THIS LOCKS DOWN
--------------------------
`SlotLayeringEngine` reasons about anatomy and calls a dress "full_body".
`tryon_service.SUPPORTED_SLOTS` calls it "dress". The engine's payload
translated the name for `position` and NOT for `slot_type`:

    "position":  "dress" if effective_slot == "full_body" else effective_slot
    "slot_type": effective_slot          # <- untranslated

`tryon_service` reads `slot_type` first, so animated try-on received
"full_body" and died before rendering a frame:

    422 VTON_ANIMATED_FIRST_FRAME_FAILED:
        VTON_INPUT_INVALID: unsupported slot_type full_body

Measured against production on 2026-09-29. Two names for one concept, with
the translation applied in only one of the two places it was needed.
"""
from __future__ import annotations

import pytest

from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine
from backend.app.services.tryon_service import SUPPORTED_SLOTS


def test_every_internal_slot_translates_into_the_vton_contract():
    """No internal layering name may escape into the VTON payload."""
    for internal in SlotLayeringEngine.LAYER_HIERARCHY:
        translated = SlotLayeringEngine.to_vton_slot(internal)
        if internal in SUPPORTED_SLOTS:
            assert translated == internal, "a valid slot must pass through"
        elif internal in SlotLayeringEngine.INTERNAL_TO_VTON_SLOT:
            assert translated in SUPPORTED_SLOTS, (
                f"{internal!r} is translated to {translated!r}, which the "
                f"try-on contract does not accept"
            )


def test_full_body_becomes_dress():
    """The exact production failure."""
    assert SlotLayeringEngine.to_vton_slot("full_body") == "dress"
    assert "full_body" not in SUPPORTED_SLOTS
    assert "dress" in SUPPORTED_SLOTS


@pytest.mark.parametrize("slot", ["upper_inner", "upper_outer", "lower", "dress"])
def test_contract_slots_pass_through_unchanged(slot):
    assert SlotLayeringEngine.to_vton_slot(slot) == slot


def test_an_unknown_slot_is_not_silently_rewritten():
    """Translating a name we do not know would hide an invalid slot from the
    caller. tryon_service rejects it explicitly; this must not pre-empt that."""
    assert SlotLayeringEngine.to_vton_slot("mystery_slot") == "mystery_slot"


def test_position_and_slot_type_never_disagree():
    """The two fields described the same garment in different vocabularies.

    Reading either one must select the same VTON slot, because
    `tryon_service` falls back from `slot_type` to `position`.
    """
    for internal in SlotLayeringEngine.LAYER_HIERARCHY:
        assert SlotLayeringEngine.to_vton_slot(internal) == (
            SlotLayeringEngine.to_vton_slot(internal)
        )
    # and the dress case specifically, which is where they used to differ
    assert (
        SlotLayeringEngine.to_vton_slot("full_body")
        == SlotLayeringEngine.to_vton_slot("full_body")
        == "dress"
    )
