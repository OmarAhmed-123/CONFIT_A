"""Explicit anchor garments (hard) and photo-palette scoring (preference).

Composer tests run the real composer over the seeded test catalogue. No provider
is involved (MOCKED-NONE: deterministic, DB-backed)."""
from backend.app.core.database import SessionLocal
from backend.app.models.catalog import Product
from backend.app.services.styling.constraints import anchor_matches, palette_bonus, parse_anchor
from backend.app.services.styling_engine import StylingEngine


# --- parsing: an explicit anchor needs a cue; a bare colour is only a preference ---

def test_build_around_names_the_anchor_garment_and_colour():
    assert parse_anchor("Build an outfit around my navy trousers for work") == {
        "slot": "bottom", "garment": "trousers", "colour": "navy"}


def test_what_goes_with_my_trousers_is_an_anchor():
    a = parse_anchor("What shoes go with my navy trousers?")
    assert a and a["colour"] == "navy" and a["garment"] == "trousers"


def test_a_bare_colour_mention_is_not_a_hard_anchor():
    assert parse_anchor("I like navy trousers") is None


def test_no_garment_means_no_anchor():
    assert parse_anchor("Build a formal wedding look") is None


# --- matching uses real product fields only ---

class _P:
    def __init__(self, title, color):
        self.title, self.color_family = title, color


def test_anchor_matches_navy_trousers_only():
    anchor = {"slot": "bottom", "garment": "trousers", "colour": "navy"}
    assert anchor_matches(_P("Pleated Tapered Virgin Wool Trousers", "Navy Blue"), anchor)
    assert not anchor_matches(_P("Pleated Tapered Virgin Wool Trousers", "Midnight Black"), anchor)
    assert not anchor_matches(_P("Tailored Italian Wool Double-Breasted Blazer", "Navy Blue"), anchor)


# --- palette preference: bounded, signed, never exclusionary ---

def test_empty_palette_changes_nothing():
    assert palette_bonus("Navy Blue", []) == 0.0


def test_same_colour_reinforces_and_harmony_adds_and_is_capped():
    assert palette_bonus("Navy Blue", ["navy"]) == 12.0          # same colour named
    assert palette_bonus("Optic White", ["navy"]) == 8.0         # neutral harmonises
    assert palette_bonus("Burgundy", ["olive"]) == -8.0          # clash
    assert palette_bonus("Navy Blue", ["navy"] * 6) == 20.0      # capped


# --- composer on the real seeded catalogue ---

def _compose(prompt, palette=None):
    db = SessionLocal()
    try:
        products = db.query(Product).all()
        intent = StylingEngine.parse_intent(prompt)
        intent["image_palette"] = palette or []
        return StylingEngine.compose_outfits_with_meta(products, intent, None, 3)
    finally:
        db.close()


def _ids(look):
    return {i.get("product_id") for i in look.get("items", [])}


def test_work_request_excludes_evening_only_pieces():
    outfits, _ = _compose("Build an office look for work")
    assert outfits, "catalogue supports a work look"
    for look in outfits:
        assert 2 not in _ids(look) and 7 not in _ids(look), look.get("title")


def test_navy_trousers_anchor_is_in_every_published_look():
    outfits, meta = _compose("Build an outfit around navy trousers for work")
    assert outfits, "catalogue has navy trousers"
    assert meta["anchor_satisfied"] is True
    for look in outfits:
        assert 4 in _ids(look), look.get("title")  # product 4: navy wool trousers


def test_missing_anchor_is_reported_not_silently_ignored():
    outfits, meta = _compose("Build an outfit around black trousers for work")
    assert outfits == []
    assert meta["anchor_satisfied"] is False
    assert any("black trousers" in r for r in meta["reasons"])


def test_no_occasion_is_not_invented():
    db = SessionLocal()
    try:
        intent = StylingEngine.parse_intent("Put together something versatile for me")
        products = db.query(Product).all()
        assert intent["occasion"] not in ("Work & Business", "Formal & Wedding", "Evening & Party")
        _, meta = StylingEngine.compose_outfits_with_meta(products, intent, None, 3)
        assert meta["occasion_excluded"] == []  # no occasion gate when none was stated
    finally:
        db.close()
