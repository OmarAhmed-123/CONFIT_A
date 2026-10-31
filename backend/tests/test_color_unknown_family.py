"""Unknown colour family (2026-10-29).

Before this change ``normalize_color`` fell back to "Black" for anything it did
not recognise (and for an empty value). Consequences that were all false claims:
"no black" excluded a periwinkle cardigan; an unclassified item counted as a
neutral; gap analysis reported "same color family (Black)" against a black
product. The sentinel family "Unknown" is never neutral, preferred, banned or
matched.
"""
from __future__ import annotations

import pytest

from backend.app.schemas.wardrobe_stylist import OutfitRecommendationRequest
from backend.app.services import wardrobe_taxonomy as taxonomy
from backend.app.services.wardrobe_stylist_service import WardrobeStylistService


@pytest.mark.parametrize("raw", ["Periwinkle", "Chartreuse-ish", "???", "", None, "xqzv"])
def test_unrecognised_or_empty_colour_is_unknown_not_black(raw):
    assert taxonomy.normalize_color(raw) == taxonomy.UNKNOWN_COLOR


@pytest.mark.parametrize("raw,family", [
    ("Black", "Black"), ("navy blue", "Navy"), ("Dark indigo", "Navy"), ("Teal", "Blue"),
    ("Charcoal", "Grey"), ("Camel", "Tan"), ("Burgundy", "Red"), ("أسود", "Black"), ("كحلي", "Navy"),
    ("Gray", "Grey"), ("Olive", "Green"),
])
def test_known_colours_keep_their_family(raw, family):
    assert taxonomy.normalize_color(raw) == family
    assert taxonomy.is_known_color(family)


def test_is_known_color_rejects_unknown_and_garbage():
    assert not taxonomy.is_known_color(taxonomy.UNKNOWN_COLOR)
    assert not taxonomy.is_known_color(None)
    assert not taxonomy.is_known_color("NotAFamily")


def test_unknown_has_a_neutral_swatch_but_model_hex_wins():
    assert taxonomy.color_hex_for_family(taxonomy.UNKNOWN_COLOR) == "#A3A3A3"
    assert taxonomy.color_hex_for_family(taxonomy.UNKNOWN_COLOR, "#c3b1e1") == "#C3B1E1"


def test_unknown_words_never_enter_the_ban_list_or_preferences():
    req = OutfitRecommendationRequest(occasion="Casual", excluded_colors=["periwinkle", "black"], color_preferences=["chartreuse"])
    banned = WardrobeStylistService.banned_color_families(req)
    assert banned == {"Black"}
    assert taxonomy.UNKNOWN_COLOR not in banned


def test_gap_analysis_does_not_match_unknown_against_unknown():
    from backend.app.services.gap_analysis_service import DuplicateDetectorService

    class _Item:  # minimal duck type for the scoring loop
        id = 1; title = "Mystery top"; category = "Tops"; color_name = "Unknown"; pattern = "Solid"; image_url = None

    class _Repo:
        def get_user_items(self, user_id):
            return [_Item()]

    svc = DuplicateDetectorService.__new__(DuplicateDetectorService)
    svc.wardrobe_repo = _Repo()
    out = svc.check_duplicate(user_id=1, product_id=9, product_title="Periwinkle blouse",
                              category="Tops", color_family="Periwinkle", pattern="Solid", strict_mode=True)
    notes = out.get("comparison_notes") or ""
    assert "same color family" not in notes
    # type (55) + pattern (10) at most — never the 35-point colour match
    assert out["similarity_score"] <= 65
