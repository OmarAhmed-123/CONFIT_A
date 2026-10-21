"""Priority Three: one field contract, honest warnings, safe size charts.

These tests exist because the failures they describe were all SILENT: a column
that vanished, two columns fighting, a tag that could never match, and a chart
that was never validated. In every case the import reported success, so no
existing test noticed.

Nothing here asserts that a function exists. Each test states the behaviour a
brand owner or a shopper would experience.
"""

from __future__ import annotations

import io
import json

import pytest

from backend.app.services import catalog_field_contract as contract
from backend.app.services import size_chart_schema as charts


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: a real SQLite session with a real brand, built the way this suite
# builds them elsewhere (no shared state, no network).
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from backend.app.core.database import Base
    from backend.app.models.catalog import Category

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for slug in ("outerwear", "tops", "bottoms", "dresses", "footwear", "accessories"):
        session.add(Category(name=slug.title(), name_ar=slug, slug=slug))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def brand_with_products(db_session):
    from backend.app.models.user import BrandProfile, User, UserRole

    owner = User(email="contract@qa.example.com", hashed_password="x",
                 full_name="Contract QA", role=UserRole.BRAND_OWNER,
                 preferred_language="en", is_active=True, is_verified=True)
    db_session.add(owner)
    db_session.flush()
    brand = BrandProfile(user_id=owner.id, brand_name="Contract Atelier",
                         slug="contract-atelier", is_verified=True)
    db_session.add(brand)
    db_session.commit()
    return brand


# ─────────────────────────────────────────────────────────────────────────────
# Header contract
# ─────────────────────────────────────────────────────────────────────────────

KNOWN = ["title", "base_price", "thumbnail_url", "style_tags", "occasion_tags"]
ALIASES = {"name": "title", "price": "base_price", "image_url": "thumbnail_url"}


def test_a_recognised_alias_resolves_to_its_canonical_field():
    out = contract.resolve_headers(["name", "price"], aliases=ALIASES, known=KNOWN)
    assert out["fields"] == {"name": "title", "price": "base_price"}
    assert out["unknown"] == []


def test_a_typo_is_reported_as_unknown_rather_than_vanishing():
    """`materiel` used to be dropped in silence: product created, no material."""
    out = contract.resolve_headers(["title", "materiel"], aliases=ALIASES, known=KNOWN)
    assert out["unknown"] == ["materiel"]


def test_two_columns_meaning_one_field_are_reported_as_a_collision():
    """`price` and `base_price` in one file: the FIRST non-empty wins, so the
    price a brand previews can differ from the next export of "the same" file."""
    out = contract.resolve_headers(
        ["price", "base_price"], aliases=ALIASES, known=KNOWN
    )
    assert out["collisions"] == [("base_price", ["price", "base_price"])]


def test_a_header_only_differing_in_case_still_collides():
    out = contract.resolve_headers(["Price", "price"], aliases=ALIASES, known=KNOWN)
    assert out["collisions"], "case is not a distinguishing feature of a column"
    canonical, headers = out["collisions"][0]
    assert canonical == "base_price" and len(headers) == 2


def test_distinct_columns_do_not_collide():
    out = contract.resolve_headers(
        ["title", "company", "retail_price"], aliases=ALIASES, known=KNOWN
    )
    assert out["collisions"] == []


@pytest.mark.parametrize("header,field", [
    ("is_featured", "is_featured"),
    ("featured", "is_featured"),
    ("IS_FEATURED", "is_featured"),
    ("is_active", "is_active"),
    ("published", "is_active"),
    ("rating", "rating"),
    ("review_count", "review_count"),
])
def test_admin_only_columns_are_recognised_as_forbidden_not_as_unknown(header, field):
    """The difference matters: "unknown column, ignored" invites the brand to
    believe the value was accepted and merely unused. These are refused."""
    out = contract.resolve_headers([header], aliases=ALIASES, known=KNOWN)
    assert out["unknown"] == []
    assert [f for _, f, _ in out["forbidden"]] == [field]


def test_every_admin_only_field_states_why_it_is_refused():
    for field, reason in contract.ADMIN_ONLY_FIELDS.items():
        assert reason and len(reason) > 20, f"{field} needs a real explanation"
        # It must be a merchandising/accounts decision, never a moderation alias.
        assert "moderation" not in reason.lower() or field == "moderation_status"


def test_forbidden_field_errors_name_the_field_and_a_next_step():
    errs = contract.forbidden_field_errors(
        ["is_featured", "rating"],
        row_number=7,
        error_factory=lambda row, field, message, suggestion: {
            "row": row, "field": field, "message": message, "suggestion": suggestion,
        },
    )
    assert {e["field"] for e in errs} == {"is_featured", "rating"}
    assert all(e["row"] == 7 for e in errs)
    assert all(e["suggestion"] for e in errs)


def test_a_forbidden_column_named_twice_is_reported_once():
    errs = contract.forbidden_field_errors(
        ["featured", "is_featured"],
        row_number=2,
        error_factory=lambda row, field, message, suggestion: field,
    )
    assert errs == ["is_featured"]


# ─────────────────────────────────────────────────────────────────────────────
# Gender: the value AND where it came from
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("men", "mens"), ("MAN", "mens"), ("menswear", "mens"), ("male", "mens"),
    ("رجالي", "mens"),
    ("women", "womens"), ("Ladies", "womens"), ("female", "womens"),
    ("نسائي", "womens"),
    ("unisex", "unisex"), ("all", "unisex"), ("both", "unisex"),
    ("gender neutral", "unisex"),
])
def test_gender_synonyms_normalise_and_report_that_they_were_explicit(raw, expected):
    value, provenance = contract.normalize_gender(raw)
    assert (value, provenance) == (expected, contract.GENDER_EXPLICIT)


def test_surrounding_whitespace_does_not_change_the_meaning():
    assert contract.normalize_gender("  Women  ")[0] == "womens"


def test_an_unknown_gender_is_refused_instead_of_silently_becoming_unisex():
    """`womans` coerced to unisex publishes a garment the stylist can never
    recommend to anyone — a wrong answer that looks like a clean import."""
    with pytest.raises(ValueError) as exc:
        contract.normalize_gender("womans")
    assert "not recognised" in str(exc.value)
    assert "unisex" in str(exc.value), "the error must show what is accepted"


def test_an_empty_gender_is_not_a_gender():
    assert contract.normalize_gender("") == ("", "")
    assert contract.normalize_gender(None) == ("", "")


def test_the_three_gender_values_are_the_three_the_stylist_understands():
    """Kept in sync with services/styling/garment_gender by assertion, not import."""
    from backend.app.services.styling import garment_gender

    known = set(contract.VALID_GENDERS)
    for value in getattr(garment_gender, "GENDERS", ()) or known:
        assert str(value).lower() in known, f"stylist knows {value!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Style / occasion: stored wording must be matchable
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("office", "Work & Business"),
    ("work", "Work & Business"),
    ("business casual", "Work & Business"),
    ("smart casual", "Smart Casual"),
    ("weekend", "Casual"),
    ("gym", "Active"),
    ("athleisure", "Active"),
    ("wedding", "Formal"),
    ("party", "Cocktail"),
    ("black tie", "Black Tie"),
])
def test_occasion_aliases_become_the_vocabulary_the_filters_search_for(raw, expected):
    canonical, unrecognised = contract.canonical_tags([raw], "occasion")
    assert canonical == [expected]
    assert unrecognised == []


def test_a_longer_alias_wins_over_a_shorter_contained_one():
    """"smart casual" contains "casual"; picking the shorter alias would file a
    smart-casual garment under everyday wear."""
    canonical, _ = contract.canonical_tags(["smart casual"], "occasion")
    assert canonical == ["Smart Casual"]


def test_an_unrecognised_occasion_is_kept_but_named():
    canonical, unrecognised = contract.canonical_tags(["boho maxi"], "occasion")
    assert canonical == ["boho maxi"], "the brand's own data is not deleted"
    assert unrecognised == ["boho maxi"], "and the brand is told it will not match"


def test_occasion_canonicalisation_never_invents_an_occasion():
    """`normalize_occasions` defaults to ["Casual"]; an import must not."""
    canonical, _ = contract.canonical_tags(["zzzz qqqq"], "occasion")
    assert canonical == ["zzzz qqqq"]


def test_duplicate_tags_collapse_to_one():
    canonical, _ = contract.canonical_tags(["office", "work", "Office"], "occasion")
    assert canonical == ["Work & Business"]


def test_style_tags_keep_the_brands_wording_because_there_is_no_vocabulary():
    canonical, unrecognised = contract.canonical_tags(["Y2K", "minimalist"], "style")
    assert canonical == ["Y2K", "minimalist"]
    assert unrecognised == []


def test_style_tags_are_cleaned_of_markup_characters():
    canonical, _ = contract.canonical_tags(["<b>bold</b>"], "style")
    assert canonical == ["bboldb"], "tag-like characters are stripped, not rendered"


@pytest.mark.parametrize("cell,expected", [
    ("office, wedding", ["office", "wedding"]),
    ('["office", "wedding"]', ["office", "wedding"]),
    (["office"], ["office"]),
    ("", []),
    (None, []),
    ("office,", ["office"]),
])
def test_tag_cells_parse_from_the_shapes_real_exports_contain(cell, expected):
    assert contract.split_tag_cell(cell) == expected


@pytest.mark.parametrize("cell", ['{"office": true}', "[1, 2]", '["a", 3]'])
def test_tag_cells_that_would_lose_data_are_refused(cell):
    with pytest.raises(ValueError):
        contract.split_tag_cell(cell)


def test_an_oversized_tag_list_is_refused_rather_than_truncated():
    with pytest.raises(ValueError):
        contract.split_tag_cell([f"t{i}" for i in range(contract.MAX_TAGS + 1)])


# ─────────────────────────────────────────────────────────────────────────────
# Size chart schema — the shape, the limits, the legible failure
# ─────────────────────────────────────────────────────────────────────────────

def chart(**overrides):
    payload = {
        "schema_version": "1.0",
        "unit": "cm",
        "rows": [
            {"size": "S", "chest": [86, 94], "waist": [72, 80]},
            {"size": "M", "chest": [94, 102], "waist": [80, 88]},
        ],
    }
    payload.update(overrides)
    return payload


def test_a_valid_chart_is_stored_with_its_version_and_no_errors():
    result = charts.validate(chart())
    assert result.ok and result.has_chart
    stored = json.loads(result.normalised)
    assert stored["schema_version"] == "1.0"
    assert stored["unit"] == "cm"
    assert [row["size"] for row in stored["rows"]] == ["S", "M"]


def test_no_chart_and_an_invalid_chart_are_different_states():
    """`{}` means "we publish no chart" (the engine falls back to EN 13402).
    A malformed chart is a REJECTION, never quietly treated as absent."""
    empty = charts.validate("{}")
    assert empty.ok and not empty.has_chart

    broken = charts.validate("{not json")
    assert not broken.ok and broken.errors[0].code == "invalid_json"


def test_legacy_charts_without_a_version_are_read_and_the_version_recorded():
    result = charts.validate({"unit": "cm", "rows": [{"size": "S", "chest": [86, 94]}]})
    assert result.ok
    assert json.loads(result.normalised)["schema_version"] == "1.0"
    assert any(w.code == "schema_version_assumed" for w in result.warnings)


def test_a_chart_from_a_future_schema_version_is_refused_not_guessed():
    result = charts.validate(chart(schema_version="2.0"))
    assert not result.ok
    assert result.errors[0].code == "unsupported_version"


def test_inches_and_centimetres_are_not_interchangeable():
    """A chart with no unit read as cm is 2.54x wrong for someone."""
    result = charts.validate(chart(unit="in", rows=[{"size": "S", "chest": [34, 37]}]))
    assert result.ok
    assert json.loads(result.normalised)["unit"] == "in"

    no_unit = charts.validate({"rows": [{"size": "S", "chest": [86, 94]}]})
    assert no_unit.ok
    assert any(w.code == "unit_assumed" for w in no_unit.warnings)
    assert json.loads(no_unit.normalised)["unit"] == "cm"


@pytest.mark.parametrize("unit", ["CM", "in.", "inch", "metres"])
def test_an_unusable_unit_is_refused(unit):
    result = charts.validate(chart(unit=unit))
    if unit == "CM":
        assert result.ok, "case is normalised, not a rejection"
        assert json.loads(result.normalised)["unit"] == "cm"
    else:
        assert not result.ok and result.errors[0].code == "bad_unit"


def test_a_point_measurement_is_stored_as_a_range_and_flagged():
    result = charts.validate({"unit": "cm", "rows": [{"size": "S", "chest": 96}]})
    assert result.ok
    assert json.loads(result.normalised)["rows"][0]["chest"] == [96.0, 96.0]
    assert any(w.code == "point_value" for w in result.warnings)


@pytest.mark.parametrize("value,expected", [
    ("96-100", [96.0, 100.0]),
    ("96 – 100", [96.0, 100.0]),
    ("96 to 100", [96.0, 100.0]),
    ([96, 100], [96.0, 100.0]),
])
def test_the_range_forms_real_exports_contain_all_parse(value, expected):
    result = charts.validate({"unit": "cm", "rows": [{"size": "S", "chest": value}]})
    assert result.ok, result.as_dict()
    assert json.loads(result.normalised)["rows"][0]["chest"] == expected


def test_an_inverted_range_is_refused():
    result = charts.validate({"unit": "cm", "rows": [{"size": "S", "chest": [100, 96]}]})
    assert not result.ok
    assert result.errors[0].code == "range_inverted"


@pytest.mark.parametrize("value,code", [
    ("wide", "not_a_number"),
    (float("inf"), "not_finite"),
    (0, "non_positive"),
    (-5, "non_positive"),
    (400, "implausible"),
    (0.5, "implausible"),
    (96.25, "too_precise"),
])
def test_nonsense_measurements_are_refused_with_a_specific_code(value, code):
    result = charts.validate({"unit": "cm", "rows": [{"size": "S", "chest": value}]})
    assert not result.ok, f"{value!r} should not be a measurement"
    assert result.errors[0].code == code


def test_decimal_precision_is_bounded_because_finer_numbers_are_not_real():
    ok = charts.validate({"unit": "cm", "rows": [{"size": "S", "chest": [86.5, 94.5]}]})
    assert ok.ok
    assert json.loads(ok.normalised)["rows"][0]["chest"] == [86.5, 94.5]


def test_duplicate_size_labels_are_refused():
    result = charts.validate({
        "unit": "cm",
        "rows": [{"size": "S", "chest": [86, 94]}, {"size": "s", "chest": [90, 98]}],
    })
    assert not result.ok
    assert result.errors[0].code == "duplicate_size"


def test_both_chart_shapes_at_once_are_refused_as_ambiguous():
    result = charts.validate({
        "unit": "cm",
        "rows": [{"size": "S", "chest": [86, 94]}],
        "sizes": {"M": {"chest": [94, 102]}},
    })
    assert not result.ok
    assert result.errors[0].code == "ambiguous_shape"


def test_the_size_keyed_shape_is_accepted_and_converted_to_rows():
    result = charts.validate({
        "unit": "in",
        "sizes": {"S": {"chest": "35-37"}, "M": {"chest": "38-40"}},
    })
    assert result.ok, result.as_dict()
    stored = json.loads(result.normalised)
    assert [row["size"] for row in stored["rows"]] == ["S", "M"]
    assert stored["rows"][0]["chest"] == [35.0, 37.0]


def test_a_chart_with_no_usable_measurements_is_refused():
    result = charts.validate({"unit": "cm", "rows": []})
    assert not result.ok
    assert result.errors[0].code == "empty_chart"


@pytest.mark.parametrize("payload,code", [
    ({"unit": "cm", "rows": [{"chest": [86, 94]}]}, "missing_size"),
    ({"unit": "cm", "rows": ["S"]}, "bad_row"),
    ({"unit": "cm", "rows": "S,M"}, "bad_rows"),
    ({"unit": "cm", "sizes": ["S"]}, "bad_sizes"),
    ({"unit": "cm"}, "no_measurements"),
])
def test_structural_mistakes_name_the_offending_path(payload, code):
    result = charts.validate(payload)
    assert not result.ok
    assert result.errors[0].code == code
    assert result.errors[0].path is not None


def test_unknown_properties_are_dropped_and_reported():
    result = charts.validate(chart(favourite_colour="blue"))
    assert result.ok
    assert "favourite_colour" not in json.loads(result.normalised)
    assert any(w.code == "unknown_property" for w in result.warnings)


def test_unknown_dimensions_are_dropped_and_reported():
    """An extension must not smuggle data past the readers."""
    result = charts.validate({
        "unit": "cm", "rows": [{"size": "S", "chest": [86, 94], "taille": [70, 78]}],
    })
    assert result.ok
    assert "taille" not in json.loads(result.normalised)["rows"][0]
    assert any(w.code == "unknown_dimension" for w in result.warnings)


def test_limits_are_enforced_on_rows_sizes_and_payload():
    too_many_rows = charts.validate({
        "unit": "cm",
        "rows": [{"size": f"S{i}", "chest": [86, 94]}
                 for i in range(charts.MAX_ROWS + 1)],
    })
    assert not too_many_rows.ok
    assert too_many_rows.errors[0].code == "too_many_rows"

    too_many_sizes = charts.validate({
        "unit": "cm",
        "sizes": {f"S{i}": {"chest": [86, 94]} for i in range(charts.MAX_SIZES + 1)},
    })
    assert not too_many_sizes.ok
    assert too_many_sizes.errors[0].code == "too_many_sizes"

    oversized = charts.validate("x" * (charts.MAX_PAYLOAD_BYTES + 1))
    assert not oversized.ok
    assert oversized.errors[0].code == "payload_too_large"


def test_a_long_size_label_is_refused_rather_than_truncated():
    result = charts.validate({
        "unit": "cm",
        "rows": [{"size": "X" * (charts.MAX_SIZE_LABEL + 1), "chest": [86, 94]}],
    })
    assert not result.ok
    assert result.errors[0].code == "too_long"


# ── safety: the chart is data, and stays data ───────────────────────────────

@pytest.mark.parametrize("payload", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
])
def test_markup_in_a_size_label_is_refused(payload):
    result = charts.validate({
        "unit": "cm", "rows": [{"size": payload, "chest": [86, 94]}],
    })
    assert not result.ok
    assert result.errors[0].code == "markup_not_allowed"


def test_markup_in_a_note_is_refused():
    result = charts.validate(chart(notes=["<b>see chart</b>"]))
    assert not result.ok
    assert result.errors[0].code == "markup_not_allowed"


def test_control_characters_are_removed_from_stored_text():
    result = charts.validate({
        "unit": "cm",
        "rows": [{"size": "S\x00M\x07", "chest": [86, 94]}],
    })
    assert result.ok
    assert json.loads(result.normalised)["rows"][0]["size"] == "SM"


def test_an_event_handler_that_is_not_markup_is_still_only_text():
    """No angle brackets means no tag; the value must round-trip as inert text."""
    result = charts.validate({
        "unit": "cm",
        "rows": [{"size": "S onerror=alert(1)", "chest": [86, 94]}],
    })
    assert result.ok
    stored = json.loads(result.normalised)["rows"][0]["size"]
    assert "<" not in stored and ">" not in stored


def test_a_textarea_cannot_be_opened_through_a_size_label():
    result = charts.validate({
        "unit": "cm",
        "rows": [{"size": "</textarea><script>x</script>", "chest": [86, 94]}],
    })
    assert not result.ok


# ── provenance fields the readers already depend on ────────────────────────

def test_source_and_notes_survive_because_the_engine_reads_them():
    result = charts.validate(chart(
        source="EN 13402-3 (men's chest girth letter codes)",
        notes=["Derived from the standard.", "Demo catalogue: not brand-published."],
    ))
    assert result.ok
    stored = json.loads(result.normalised)
    assert stored["source"].startswith("EN 13402-3")
    assert stored["notes"] == [
        "Derived from the standard.", "Demo catalogue: not brand-published.",
    ]


def test_notes_are_always_stored_as_a_list_paragraphs_not_flattened():
    result = charts.validate(chart(note="Only one paragraph."))
    assert result.ok
    assert json.loads(result.normalised)["notes"] == ["Only one paragraph."]


def test_published_by_brand_is_a_boolean_or_nothing():
    assert json.loads(charts.validate(chart(published_by_brand=True)).normalised)[
        "published_by_brand"] is True
    assert not charts.validate(chart(published_by_brand="yes")).ok


def test_a_real_seeded_chart_passes_the_contract():
    """The contract must accept the data CONFIT already ships, or it would
    force a rewrite of published charts to satisfy a new rule."""
    from backend.app.seed_size_charts import SIZE_CHARTS_BY_SLUG

    assert SIZE_CHARTS_BY_SLUG
    for slug, payload in SIZE_CHARTS_BY_SLUG.items():
        result = charts.validate(payload)
        assert result.ok, f"{slug}: {result.as_dict()['errors']}"


def test_the_engine_dimensions_and_the_schema_dimensions_agree():
    from backend.app.services.fit.size_charts import DIMENSIONS

    assert tuple(sorted(DIMENSIONS)) == tuple(sorted(charts.KNOWN_DIMENSIONS))


def test_validate_or_raise_names_the_first_problem_for_an_operator():
    with pytest.raises(ValueError) as exc:
        charts.validate_or_raise(chart(unit="furlongs"))
    assert "bad_unit" in str(exc.value)
    assert "unit" in str(exc.value)


def test_the_error_shape_is_stable_for_the_api():
    result = charts.validate(chart(unit="furlongs"))
    payload = result.as_dict()
    assert set(payload) == {"ok", "has_chart", "schema_version", "errors", "warnings"}
    assert set(payload["errors"][0]) == {"code", "path", "message"}


# ─────────────────────────────────────────────────────────────────────────────
# Import-level behaviour (the paths a brand actually uses)
# ─────────────────────────────────────────────────────────────────────────────

def test_the_importer_rejects_a_row_that_sets_is_featured(db_session, brand_with_products):
    """A brand must not be able to grant itself featured placement — and must be
    told, rather than having the column silently ignored."""
    from backend.app.services.brand_catalog_service import BrandCatalogService

    service = BrandCatalogService(db_session)
    row = {
        "title": "Featured Probe Coat",
        "category_slug": "outerwear",
        "base_price": "100.00",
        "color_family": "Black",
        "thumbnail_url": "https://images.pexels.com/photos/1/x.jpg",
        "currency": "USD",
        "stock_level": "3",
        "size": "M",
        "title_ar": "معطف",
        "is_featured": "true",
    }
    result = service.process_json_import(
        [row], brand_with_products.id, send_notifications=False
    )
    assert result["accepted_rows"] == 0
    messages = " ".join(e.get("message", "") for e in result["errors"])
    assert "is_featured" in messages
    assert "admin" in messages.lower() or "CONFIT" in messages

    from backend.app.models.catalog import Product

    assert db_session.query(Product).filter(
        Product.title == "Featured Probe Coat"
    ).first() is None


def test_import_never_writes_publication_state(db_session, brand_with_products):
    """Publication is a platform action. The import path must not be able to set
    it — otherwise a brand could publish unreviewed content by importing."""
    from backend.app.services.brand_catalog_service import BrandCatalogService
    from backend.app.models.catalog import Product

    service = BrandCatalogService(db_session)
    result = service.process_json_import(
        [{
            "title": "Publication Probe Tee",
            "category_slug": "tops",
            "base_price": "40.00",
            "color_family": "White",
            "thumbnail_url": "https://images.pexels.com/photos/2/x.jpg",
            "currency": "USD",
            "stock_level": "2",
            "size": "M",
            "title_ar": "تيشيرت",
        }],
        brand_with_products.id,
        send_notifications=False,
    )
    assert result["accepted_rows"] == 1, result["errors"]
    product = db_session.query(Product).filter(
        Product.title == "Publication Probe Tee"
    ).one()
    # The flag is the model's own default (True) — the importer did not assert it,
    # and the only other writer of is_active is the admin service.
    source = __import__("inspect").getsource(BrandCatalogService)
    assert "is_active=" not in source
    assert product.is_featured is False


def test_the_importer_stores_the_occasion_vocabulary_not_the_brand_wording(
    db_session, brand_with_products
):
    """Stored verbatim, "office" could never match the catalogue's
    "Work & Business" filter — imported, live, and unfindable."""
    from backend.app.services.brand_catalog_service import BrandCatalogService
    from backend.app.models.catalog import Product

    service = BrandCatalogService(db_session)
    result = service.process_json_import(
        [{
            "title": "Occasion Probe Blazer",
            "category_slug": "outerwear",
            "base_price": "220.00",
            "color_family": "Navy",
            "thumbnail_url": "https://images.pexels.com/photos/3/x.jpg",
            "currency": "USD",
            "stock_level": "2",
            "size": "M",
            "gender": "women",
            "title_ar": "بليزر",
            "occasion_tags": "office, wedding",
            "style_tags": "minimalist",
        }],
        brand_with_products.id,
        send_notifications=False,
    )
    assert result["accepted_rows"] == 1, result["errors"]
    product = db_session.query(Product).filter(
        Product.title == "Occasion Probe Blazer"
    ).one()
    stored = json.loads(product.occasion_tags)
    assert "Work & Business" in stored and "Formal" in stored
    assert "office" not in stored
    assert json.loads(product.style_tags) == ["minimalist"]
    assert product.gender == "womens"


def test_a_csv_with_a_forbidden_column_is_reported_in_the_preview(
    db_session, brand_with_products, tmp_path
):
    from backend.app.services.brand_catalog_service import BrandCatalogService

    service = BrandCatalogService(db_session)
    buf = io.StringIO()
    buf.write(
        "title,category_slug,base_price,color_family,thumbnail_url,currency,"
        "stock_level,size,title_ar,is_featured\n"
        "Preview Probe Coat,outerwear,100.00,Black,"
        "https://images.pexels.com/photos/4/x.jpg,USD,2,M,معطف,true\n"
    )
    preview = service.preview_csv(buf.getvalue(), brand_with_products.id)
    messages = " ".join(e["message"] for e in preview["errors"])
    assert "is_featured" in messages
    assert preview["can_import"] is False


# ─────────────────────────────────────────────────────────────────────────────
# The write path: an invalid chart must never reach the column
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def brand_api(tmp_path, monkeypatch):
    """A real app with a real brand user, isolated SQLite and no network."""
    import os
    import uuid

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.app.core.database import Base, get_db
    from backend.app.core.security import create_access_token
    from backend.app.main import app
    from backend.app.models.catalog import Category, Product
    from backend.app.models.user import BrandProfile, User, UserRole

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        owner = User(email=f"chart-{uuid.uuid4().hex[:8]}@qa.example.com",
                     hashed_password="x", full_name="Chart Owner",
                     role=UserRole.BRAND_OWNER, preferred_language="en",
                     is_active=True, is_verified=True)
        other = User(email=f"other-{uuid.uuid4().hex[:8]}@qa.example.com",
                     hashed_password="x", full_name="Other Owner",
                     role=UserRole.BRAND_OWNER, preferred_language="en",
                     is_active=True, is_verified=True)
        db.add_all([owner, other])
        db.flush()
        brand = BrandProfile(user_id=owner.id, brand_name="Chart Atelier",
                             slug=f"chart-{uuid.uuid4().hex[:6]}", is_verified=True)
        rival = BrandProfile(user_id=other.id, brand_name="Rival Atelier",
                             slug=f"rival-{uuid.uuid4().hex[:6]}", is_verified=True)
        db.add_all([brand, rival])
        db.add(Category(name="Outerwear", name_ar="ملابس", slug="outerwear"))
        db.flush()
        product = Product(brand_id=brand.id, category_id=1, title="Chart Coat",
                          title_ar="معطف القياس", description="A coat.",
                          description_ar="معطف.",
                          slug=f"chart-coat-{uuid.uuid4().hex[:6]}", base_price=100,
                          currency="USD", color_family="Black",
                          thumbnail_url="https://images.pexels.com/photos/9/x.jpg",
                          images="[]", style_tags="[]",
                          occasion_tags="[]", size_chart_json="{}")
        rivals_product = Product(brand_id=rival.id, category_id=1, title="Rival Coat",
                                 title_ar="معطف منافس", description="A coat.",
                                 description_ar="معطف.",
                                 slug=f"rival-coat-{uuid.uuid4().hex[:6]}",
                                 base_price=100, currency="USD", color_family="Black",
                                 thumbnail_url="https://images.pexels.com/photos/8/x.jpg",
                                 images="[]", style_tags="[]",
                                 occasion_tags="[]", size_chart_json="{}")
        db.add_all([product, rivals_product])
        db.commit()
        token = create_access_token({"sub": str(owner.id)})
        ids = {"product": product.id, "rival": rivals_product.id, "brand": brand.id}

    def session():
        with factory() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = session
    client = TestClient(app)
    yield {
        "client": client,
        "headers": {"Authorization": f"Bearer {token}"},
        "ids": ids,
        "factory": factory,
    }
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)


def test_a_valid_chart_is_persisted_normalised(brand_api):
    response = brand_api["client"].put(
        f"/api/v1/partner/catalog/products/{brand_api['ids']['product']}/size-chart",
        headers=brand_api["headers"],
        json={"size_chart": chart()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_chart"] is True
    assert body["size_chart"]["schema_version"] == "1.0"

    from backend.app.models.catalog import Product

    with brand_api["factory"]() as db:
        stored = db.get(Product, brand_api["ids"]["product"]).size_chart_json
    assert json.loads(stored)["schema_version"] == "1.0"


def test_an_invalid_chart_is_rejected_and_nothing_is_written(brand_api):
    """Validation happens BEFORE persist: a bad chart must not replace a good one."""
    client, headers, ids = brand_api["client"], brand_api["headers"], brand_api["ids"]
    url = f"/api/v1/partner/catalog/products/{ids['product']}/size-chart"
    assert client.put(url, headers=headers, json={"size_chart": chart()}).status_code == 200

    before = None
    from backend.app.models.catalog import Product

    with brand_api["factory"]() as db:
        before = db.get(Product, ids["product"]).size_chart_json

    bad = client.put(url, headers=headers, json={"size_chart": chart(unit="furlongs")})
    assert bad.status_code == 422
    detail = bad.json()["detail"]
    assert detail["errors"][0]["code"] == "bad_unit"
    assert detail["errors"][0]["path"] == "unit"

    with brand_api["factory"]() as db:
        after = db.get(Product, ids["product"]).size_chart_json
    assert after == before, "a rejected chart must leave the stored chart untouched"


def test_no_chart_can_be_published_explicitly(brand_api):
    client, headers, ids = brand_api["client"], brand_api["headers"], brand_api["ids"]
    url = f"/api/v1/partner/catalog/products/{ids['product']}/size-chart"
    response = client.put(url, headers=headers, json={"size_chart": {}})
    assert response.status_code == 200
    assert response.json()["has_chart"] is False
    assert response.json()["size_chart"] == {}


def test_a_brand_cannot_write_another_brands_chart(brand_api):
    """Tenant isolation: the answer must not reveal that the other SKU exists."""
    response = brand_api["client"].put(
        f"/api/v1/partner/catalog/products/{brand_api['ids']['rival']}/size-chart",
        headers=brand_api["headers"],
        json={"size_chart": chart()},
    )
    assert response.status_code == 404

    from backend.app.models.catalog import Product

    with brand_api["factory"]() as db:
        assert db.get(Product, brand_api["ids"]["rival"]).size_chart_json == "{}"


def test_the_endpoint_is_closed_to_anonymous_callers(brand_api):
    response = brand_api["client"].put(
        f"/api/v1/partner/catalog/products/{brand_api['ids']['product']}/size-chart",
        json={"size_chart": chart()},
    )
    assert response.status_code in (401, 403)


# ===========================================================================
# Brand PATCH contract & Storefront Search / Filter canonical alignment
# ===========================================================================
def test_brand_patch_normalises_fields_persists_on_reload_and_warns_unrecognised_occasion(brand_api):
    client, headers, ids = brand_api["client"], brand_api["headers"], brand_api["ids"]
    r = client.patch(
        f"/api/v1/partner/catalog/products/{ids['product']}",
        headers=headers,
        json={
            "description": "Double-faced wool coat with horn buttons.",
            "description_ar": "معطف صوف مزدوج الوجه بأزرار طبيعية.",
            "material": "100% Virgin Wool",
            "care_instructions": "Dry clean only",
            "gender": "women's",
            "style_tags": ["Minimalist", "Tailored"],
            "occasion_tags": ["office", "rooftop_vernissage"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    prod = body["product"]
    assert prod["gender"] == "womens"
    assert prod["description"] == "Double-faced wool coat with horn buttons."
    assert prod["material"] == "100% Virgin Wool"
    assert prod["style_tags"] == ["Minimalist", "Tailored"]
    assert prod["occasion_tags"] == ["Work & Business", "rooftop_vernissage"]
    assert any(w["code"] == "occasion_unrecognised" for w in body["warnings"])

    # Reload via GET /partner/products confirms durable persistence
    listed = client.get("/api/v1/partner/products", headers=headers)
    assert listed.status_code == 200
    reloaded = next(item for item in listed.json() if item["id"] == ids["product"])
    assert reloaded["gender"] == "womens"
    assert reloaded["occasion_tags"] == ["Work & Business", "rooftop_vernissage"]


@pytest.mark.parametrize(
    "forbidden_payload",
    [
        {"is_featured": True},
        {"is_active": False},
        {"rating": 5.0},
        {"moderation_status": "approved"},
    ],
)
def test_brand_patch_refuses_system_managed_fields_and_cross_brand_writes(brand_api, forbidden_payload):
    client, headers, ids = brand_api["client"], brand_api["headers"], brand_api["ids"]
    r = client.patch(
        f"/api/v1/partner/catalog/products/{ids['product']}",
        headers=headers,
        json=forbidden_payload,
    )
    assert r.status_code == 422, r.text

    # Cross-brand product returns 404 (no existence leak)
    cross = client.patch(
        f"/api/v1/partner/catalog/products/{ids['rival']}",
        headers=headers,
        json={"description": "Attempted overwrite"},
    )
    assert cross.status_code == 404


def test_storefront_list_and_search_filter_by_canonical_gender_style_and_occasion(brand_api):
    from backend.app.models.catalog import ProductSKU

    client, headers, ids = brand_api["client"], brand_api["headers"], brand_api["ids"]
    db = brand_api["factory"]()
    try:
        db.add(ProductSKU(
            product_id=ids["product"], sku_code="COAT-W-M", size="M",
            color="Black", color_hex="#252729", stock_level=6, is_in_stock=True,
        ))
        db.add(ProductSKU(
            product_id=ids["rival"], sku_code="RIVAL-M-L", size="L",
            color="Black", color_hex="#252729", stock_level=4, is_in_stock=True,
        ))
        db.commit()
    finally:
        db.close()

    client.patch(
        f"/api/v1/partner/catalog/products/{ids['product']}",
        headers=headers,
        json={
            "gender": "womens",
            "style_tags": ["Architectural", "Minimalist"],
            "occasion_tags": ["office", "wedding"],
        },
    )

    # Filter list by canonical gender, style, and occasion (both canonical & shopper alias)
    by_gender = client.get("/api/v1/catalog/products", params={"gender": "women", "style": "Architectural", "occasion": "office"})
    assert by_gender.status_code == 200
    assert [p["id"] for p in by_gender.json()] == [ids["product"]]

    # Malformed gender returns empty list rather than 500 or unfiltered products
    malformed = client.get("/api/v1/catalog/products", params={"gender": "not-a-gender"})
    assert malformed.status_code == 200
    assert malformed.json() == []

    # Search endpoint honours gender + style + occasion filters identically
    sr = client.get("/api/v1/catalog/search", params={"q": "Coat", "gender": "womens", "occasion": "Work & Business"})
    assert sr.status_code == 200
    assert [p["id"] for p in sr.json()["results"]] == [ids["product"]]
