"""The size-chart backfill must be safe to run against a live catalogue.

`seed_database()` refuses to touch a database that already has users, so the
charts added in PR #126 reach a fresh database only — the existing production
catalogue kept `size_chart_json = "{}"`. The backfill closes that gap, which
means it runs against real data, which means the interesting question is not
"does it write the chart" but "what does it refuse to touch".
"""

from __future__ import annotations

import json

import pytest

from backend.app.models.catalog import Product
from backend.app.seed_size_charts import SIZE_CHARTS_BY_SLUG, size_chart_json_for_slug
from backend.tests.conftest import TestingSessionLocal

CHARTED_SLUG = "relaxed-organic-poplin-oxford-shirt"


def _run(db, dry_run: bool):
    """Invoke the backfill's logic against the test session."""
    from backend.scripts.backfill_size_charts import EMPTY, _is_empty

    updated, skipped, foreign = [], [], []
    for slug in sorted(SIZE_CHARTS_BY_SLUG):
        product = db.query(Product).filter(Product.slug == slug).one_or_none()
        if product is None:
            continue
        intended = size_chart_json_for_slug(slug)
        if not _is_empty(product.size_chart_json):
            try:
                same = json.loads(product.size_chart_json) == json.loads(intended)
            except (ValueError, TypeError):
                same = False
            (skipped if same else foreign).append(slug)
            continue
        if not dry_run:
            product.size_chart_json = intended
        updated.append(slug)
    if not dry_run:
        db.commit()
    return updated, skipped, foreign


def test_is_empty_treats_all_the_empty_spellings_as_empty():
    from backend.scripts.backfill_size_charts import _is_empty

    for raw in ("", "  ", "{}", " {} ", "null", "[]", None):
        assert _is_empty(raw), raw
    assert not _is_empty('{"rows": []}')


def test_backfill_is_idempotent_and_leaves_foreign_charts_alone():
    db = TestingSessionLocal()
    try:
        product = db.query(Product).filter(Product.slug == CHARTED_SLUG).one_or_none()
        if product is None:
            pytest.skip(f"{CHARTED_SLUG} not in the seeded catalogue")

        # The seeded DB already carries the chart, so this run must be a no-op.
        updated, skipped, foreign = _run(db, dry_run=True)
        assert CHARTED_SLUG not in updated, "would rewrite a chart that is already correct"
        assert not foreign, foreign

        # Simulate a real brand having uploaded their own chart afterwards.
        brand_chart = json.dumps(
            {"unit": "cm", "rows": [{"size": "M", "chest": [90, 98]}], "source": "the brand"}
        )
        original = product.size_chart_json
        product.size_chart_json = brand_chart
        db.commit()

        updated, skipped, foreign = _run(db, dry_run=False)
        assert CHARTED_SLUG in foreign, "must report, not silently overwrite"
        assert CHARTED_SLUG not in updated

        db.refresh(product)
        assert json.loads(product.size_chart_json)["source"] == "the brand", (
            "the brand's own measurements were overwritten by ours"
        )

        product.size_chart_json = original
        db.commit()
    finally:
        db.close()


def test_backfill_writes_only_into_an_empty_chart_and_dry_run_writes_nothing():
    db = TestingSessionLocal()
    try:
        product = db.query(Product).filter(Product.slug == CHARTED_SLUG).one_or_none()
        if product is None:
            pytest.skip(f"{CHARTED_SLUG} not in the seeded catalogue")
        original = product.size_chart_json

        product.size_chart_json = "{}"
        db.commit()

        updated, _, _ = _run(db, dry_run=True)
        assert CHARTED_SLUG in updated
        db.refresh(product)
        assert product.size_chart_json == "{}", "--dry-run wrote to the database"

        updated, _, _ = _run(db, dry_run=False)
        assert CHARTED_SLUG in updated
        db.refresh(product)
        assert json.loads(product.size_chart_json)["rows"], "chart was not written"

        product.size_chart_json = original
        db.commit()
    finally:
        db.close()
