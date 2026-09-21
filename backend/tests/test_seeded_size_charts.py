"""The seeded size charts must be real, parseable, and actually used.

Before this, every seeded product carried ``size_chart_json = "{}"``, so the
brand-chart code path was never exercised by the running application — the
engine fell back to the EN 13402-3 standard for all nine products. A chart that
is authored but silently unparseable is worse than no chart, because the
provenance card would keep claiming "brand chart" while the numbers came from
the fallback. These tests close that gap.
"""

from __future__ import annotations

import json

import pytest

from backend.app.seed_size_charts import SIZE_CHARTS_BY_SLUG, size_chart_json_for_slug
from backend.app.services.fit.size_charts import parse_size_chart_json

# Slugs that must NOT carry a chart: shoe length and one-size accessories are
# not body-girth problems, and the engine is expected to refuse for them.
UNCHARTED_SLUGS = [
    "goodyear-welted-leather-oxford-shoes",
    "strappy-metallic-leather-heeled-sandals",
    "silk-jacquard-evening-necktie",
    "structured-metallic-evening-box-clutch",
]


@pytest.mark.parametrize("slug", sorted(SIZE_CHARTS_BY_SLUG))
def test_every_seeded_chart_parses_without_warnings(slug):
    chart = parse_size_chart_json(size_chart_json_for_slug(slug))
    assert chart.rows, f"{slug}: chart produced no usable rows"
    assert not chart.parse_warnings, f"{slug}: {chart.parse_warnings}"


@pytest.mark.parametrize("slug", sorted(SIZE_CHARTS_BY_SLUG))
def test_every_seeded_chart_declares_its_provenance(slug):
    raw = json.loads(size_chart_json_for_slug(slug))
    assert raw.get("source"), f"{slug}: a chart with no source is an unverifiable claim"
    assert raw.get("updated_at"), f"{slug}: charts must carry a review date"
    assert raw.get("notes"), f"{slug}: charts must state how they were derived"
    # The demo catalogue must never imply the real brand published these.
    joined = " ".join(raw["notes"]).lower()
    assert "demo catalogue" in joined or "not published by the brand" in joined


@pytest.mark.parametrize("slug", sorted(SIZE_CHARTS_BY_SLUG))
def test_chart_rows_are_ordered_and_non_degenerate(slug):
    """Ranges must be ascending, and consecutive sizes must actually differ.

    A chart whose sizes all share the same range scores every size identically
    and sends the recommendation into the tie-break — the exact defect the
    acceptance suite caught in the scorer.
    """
    chart = parse_size_chart_json(size_chart_json_for_slug(slug))
    for row in chart.rows:
        for dim, (lo, hi) in row.ranges.items():
            assert lo < hi, f"{slug}/{row.size}/{dim}: empty or inverted range {lo}-{hi}"

    for prev, curr in zip(chart.rows, chart.rows[1:]):
        shared = set(prev.ranges) & set(curr.ranges)
        assert shared, f"{slug}: {prev.size} and {curr.size} share no dimension"
        assert any(
            curr.ranges[d][0] > prev.ranges[d][0] for d in shared
        ), f"{slug}: {curr.size} is not larger than {prev.size} in any dimension"


@pytest.mark.parametrize("slug", UNCHARTED_SLUGS)
def test_footwear_and_accessories_carry_no_fabricated_chart(slug):
    assert size_chart_json_for_slug(slug) == "{}"


def test_unknown_slug_falls_back_to_empty_rather_than_guessing():
    assert size_chart_json_for_slug("a-product-that-does-not-exist") == "{}"


def test_inch_charts_convert_to_plausible_centimetres():
    """The tuxedo chart is authored in inches; a '40' must mean a 40in chest."""
    chart = parse_size_chart_json(size_chart_json_for_slug("tuxedo-peak-lapel-evening-dinner-jacket"))
    row = next(r for r in chart.rows if r.size == "40")
    lo, hi = row.ranges["chest"]
    # 39-41 in == 99.1-104.1 cm
    assert 98 < lo < 100, lo
    assert 103 < hi < 105, hi


def test_trouser_sizes_are_waist_inches_not_letters():
    chart = parse_size_chart_json(size_chart_json_for_slug("pleated-tapered-virgin-wool-trousers"))
    row = next(r for r in chart.rows if r.size == "32")
    lo, hi = row.ranges["waist"]
    # 31.5-32.5 in == 80.0-82.6 cm
    assert 79 < lo < 81, lo
    assert 82 < hi < 84, hi
    assert "hip" in row.ranges, "a tapered trouser must be scored at the hip too"
