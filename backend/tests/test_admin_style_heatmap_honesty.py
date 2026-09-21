"""Honesty gates for the style-signal heatmap (gap register G-01, G-02, G-03, G-04).

The regression this file exists to kill: ``get_platform_admin_analytics`` shipped
four hardcoded aesthetics (``"Quiet Luxury / Old Money": 38%`` …) and four
hardcoded colour chips whenever the real aggregation came back empty, inside a
dashboard titled *"Real Data"* that states *"No fake numbers"*. It sat there from
the first commit because the only test touching it asserted
``"top_aesthetics" in data or "top_colors" in data`` — which the fake rows
satisfy.

Isolation
---------
The session fixture seeds its own outfits, so a "now" window would include them.
Every row this file writes is stamped 30 days in the FUTURE and every assertion
reads a window around that stamp, which no seeded data can occupy.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import List, Sequence, Tuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.models.catalog import Product
from backend.app.models.stylist import Outfit
from backend.app.models.user import User
from backend.app.repositories.brand_repository import BrandRepository

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

MARKER = "HEATMAP_HONESTY_TEST"
FABRICATED_AESTHETICS = {
    "Quiet Luxury / Old Money",
    "Modern Minimalist",
    "Elevated Streetwear",
    "Smart Tailored",
}
FABRICATED_COLORS = {"#1B1F3B (Navy)", "#C5A059 (Gold/Beige)", "#2D4A3E (Forest)", "#F5F5DC (Ivory)"}

Row = Tuple[Sequence[str], Sequence[str], str]


def _stamp() -> datetime:
    """A fixed future stamp no seeded row can share."""
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=30)).replace(microsecond=0)


STAMP = _stamp()


def _admin_headers(client: TestClient) -> dict:
    login = client.post(
        "/api/v1/auth/login", json={"email": "admin@confit.io", "password": "Password123!"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed(rows: List[Row], created_at: datetime) -> int:
    db = TestingSessionLocal()
    try:
        for index, (tags, colors, occasion) in enumerate(rows):
            db.add(
                Outfit(
                    user_id=None,
                    title=f"{MARKER}-{index}",
                    occasion=occasion,
                    style_tags=json.dumps(list(tags)),
                    color_palette=json.dumps(list(colors)),
                    is_saved=True,
                    created_at=created_at,
                )
            )
        db.commit()
    finally:
        db.close()
    return len(rows)


def _purge() -> None:
    db = TestingSessionLocal()
    try:
        db.query(Outfit).filter(Outfit.title.like(f"{MARKER}%")).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _heatmap(**kwargs) -> dict:
    """Heatmap over the isolated future window unless a window is given."""
    db = TestingSessionLocal()
    try:
        if "date_from" not in kwargs:
            kwargs["date_from"] = STAMP - timedelta(hours=12)
        if "date_to" not in kwargs:
            kwargs["date_to"] = STAMP + timedelta(hours=12)
        return BrandRepository(db).get_style_heatmap(**kwargs)
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolated():
    _purge()
    yield
    _purge()


# ---------------------------------------------------------------------------
# G-01 — nothing is fabricated
# ---------------------------------------------------------------------------
class TestNothingIsFabricated:
    def test_empty_window_publishes_nothing(self) -> None:
        """The exact condition that used to trigger the hardcoded fallback."""
        heatmap = _heatmap()
        assert heatmap["data_available"] is False
        assert heatmap["top_aesthetics"] == []
        assert heatmap["trending_colors"] == []
        assert heatmap["top_occasions"] == []
        assert heatmap["sample_size"] == 0
        assert heatmap["limitations"], "an empty aggregate must explain itself"

    def test_the_hardcoded_rows_never_appear(self) -> None:
        payload = json.dumps(_heatmap())
        for fake in FABRICATED_AESTHETICS | FABRICATED_COLORS:
            assert fake not in payload, f"fabricated row resurfaced: {fake}"

    def test_the_fabricated_literals_are_gone_from_the_source(self) -> None:
        """Mutation gate: reintroducing the fallback block fails here."""
        import pathlib

        source = pathlib.Path("backend/app/repositories/brand_repository.py").read_text()
        for fake in ('"Quiet Luxury / Old Money"', '"#1B1F3B (Navy)"', "Fallback if no data"):
            assert fake not in source, f"fabricated heatmap literal is back: {fake}"

    def test_catalogue_tags_are_not_substituted_for_shopper_signals(self) -> None:
        """The old code fell back to ``Product.style_tags`` when outfits were thin
        and presented catalogue attributes as shopper preferences."""
        db = TestingSessionLocal()
        try:
            assert db.query(Product).filter(Product.style_tags.isnot(None)).count() > 0, (
                "the seeded catalogue carries style tags, so this is a real check"
            )
        finally:
            db.close()

        heatmap = _heatmap()
        assert heatmap["top_aesthetics"] == [], "catalogue tags leaked into a shopper-preference metric"
        assert heatmap["data_available"] is False


# ---------------------------------------------------------------------------
# G-02 — the k-anonymity floor is a floor
# ---------------------------------------------------------------------------
class TestKAnonymity:
    def test_rare_cells_are_suppressed_common_cells_published(self) -> None:
        floor = BrandRepository.HEATMAP_K_FLOOR
        rows: List[Row] = [(["common_aesthetic"], ["#111111"], "Formal")] * floor
        rows.append((["rare_aesthetic"], ["#222222"], "OneOffOccasion"))
        while len(rows) < BrandRepository.HEATMAP_MIN_SAMPLE:
            rows.append((["common_aesthetic"], ["#111111"], "Formal"))
        _seed(rows, STAMP)

        heatmap = _heatmap()
        assert heatmap["data_available"] is True
        assert "common_aesthetic" in {c["raw_name"] for c in heatmap["top_aesthetics"]}
        assert "rare_aesthetic" not in {c["raw_name"] for c in heatmap["top_aesthetics"]}
        assert "OneOffOccasion" not in {c["raw_name"] for c in heatmap["top_occasions"]}
        assert "#222222" not in {c["raw_name"] for c in heatmap["trending_colors"]}
        assert heatmap["suppressed_cells"] >= 3

    def test_no_large_sample_bypass(self) -> None:
        """The old guard was ``count >= 3 or sample_size >= 50``: a single
        occurrence went straight through once the dataset was big."""
        rows: List[Row] = [(["popular"], ["#333333"], "Casual")] * 60
        rows.append((["singleton_tag"], ["#444444"], "SingletonOccasion"))
        _seed(rows, STAMP)

        heatmap = _heatmap()
        assert heatmap["sample_size"] == 61
        assert "singleton_tag" not in {c["raw_name"] for c in heatmap["top_aesthetics"]}
        assert "SingletonOccasion" not in {c["raw_name"] for c in heatmap["top_occasions"]}
        assert "#444444" not in {c["raw_name"] for c in heatmap["trending_colors"]}

    def test_sample_size_is_the_outfits_aggregated_not_the_user_count(self) -> None:
        """``sample_size`` was inflated to ``total_users`` under ten outfits,
        which made the published privacy statement false."""
        _seed([(["tag_a"], ["#555555"], "Casual")] * 3, STAMP)

        heatmap = _heatmap()
        db = TestingSessionLocal()
        try:
            total_users = db.query(User).count()
        finally:
            db.close()

        assert total_users > 3, "this assertion needs a populated users table to mean anything"
        assert heatmap["sample_size"] == 3
        assert heatmap["data_available"] is False


# ---------------------------------------------------------------------------
# G-03 — the window is real; region is refused, not ignored
# ---------------------------------------------------------------------------
class TestFilters:
    def test_date_window_restricts_the_sample(self) -> None:
        _seed([(["recent_tag"], ["#666666"], "Casual")] * 4, STAMP)
        _seed([(["ancient_tag"], ["#777777"], "Casual")] * 4, STAMP - timedelta(days=400))

        assert _heatmap()["sample_size"] == 4
        db = TestingSessionLocal()
        try:
            everything = BrandRepository(db).get_style_heatmap()
        finally:
            db.close()
        assert everything["sample_size"] >= 8
        assert _heatmap()["period"]["from"] is not None

    def test_a_requested_region_is_reported_as_not_applied(self) -> None:
        """Same convention as the partner endpoint: accept the parameter, apply
        nothing, and say so in the payload rather than labelling platform-wide
        numbers with the caller's region."""
        db = TestingSessionLocal()
        try:
            heatmap = BrandRepository(db).get_user_preference_heatmaps(region="EU")
            assert heatmap["requested_region"] == "EU"
            assert heatmap["region_filter_applied"] is False
            assert heatmap["region_scope"] == "platform_wide"
            assert "EU" in heatmap["limitations"][0]
            assert heatmap["region"] != "EU", "the label must not claim a filter that never ran"
        finally:
            db.close()

    def test_admin_endpoint_reports_the_unapplied_region(self, client: TestClient) -> None:
        headers = _admin_headers(client)
        response = client.get("/api/v1/admin/analytics/heatmaps?region=MENA", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["requested_region"] == "MENA"
        assert body["region_filter_applied"] is False
        assert body["region"] != "MENA"

    def test_admin_endpoint_serves_the_platform_wide_aggregate(self, client: TestClient) -> None:
        headers = _admin_headers(client)
        response = client.get("/api/v1/admin/analytics/heatmaps", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["region_filter_applied"] is False
        assert body["region_scope"] == "platform_wide"
        assert body["region"] == "Platform-wide"


# ---------------------------------------------------------------------------
# G-04 — one contract everywhere
# ---------------------------------------------------------------------------
class TestSingleContract:
    def test_dashboard_and_standalone_endpoint_agree(self, client: TestClient) -> None:
        _seed([(["contract_tag"], ["#888888"], "Casual")] * 12, STAMP)

        headers = _admin_headers(client)
        dashboard = client.get("/api/v1/admin/analytics", headers=headers).json()
        standalone = client.get("/api/v1/admin/analytics/heatmaps", headers=headers).json()

        embedded = dashboard["style_preference_heatmap"]
        for key in ("sample_size", "k_anonymity_floor", "data_available", "privacy_threshold"):
            assert embedded[key] == standalone[key], key
        assert embedded["top_aesthetics"] == standalone["top_aesthetics"]
        assert embedded["trending_colors"] == standalone["trending_colors"]
        assert embedded["top_occasions"] == standalone["top_occasions"]

    def test_every_dimension_uses_one_cell_shape(self, client: TestClient) -> None:
        """The dashboard emitted ``{name, share}``, the standalone endpoint
        ``{name, weight, count}``, and colours were ``string[]`` in one and
        ``{color, weight, count}[]`` in the other — the view rendered
        ``undefined%`` bars and then threw on ``trending_colors.map``."""
        _seed([(["shape_tag"], ["#999999"], "Casual")] * 12, STAMP)

        headers = _admin_headers(client)
        body = client.get("/api/v1/admin/analytics/heatmaps", headers=headers).json()
        for dimension in ("top_aesthetics", "trending_colors", "top_occasions"):
            cells = body[dimension]
            assert isinstance(cells, list)
            for cell in cells:
                assert isinstance(cell, dict), f"{dimension} must be objects, not bare strings"
                assert set(cell) >= {"name", "share", "count"}, cell
                assert isinstance(cell["share"], (int, float))
                assert isinstance(cell["count"], int)

    def test_the_partner_heatmap_uses_the_same_cell_shape(self) -> None:
        """The brand-scoped endpoint was the last fork of the contract: it
        emitted `weight` and a `top_colors` key the shared builder never
        produced, so a partner UI reading `share` / `trending_colors` got
        nothing. One shape everywhere now."""
        db = TestingSessionLocal()
        try:
            from backend.app.models.catalog import Product

            brand_id = db.query(Product.brand_id).filter(Product.brand_id.isnot(None)).first()[0]
            heatmap = BrandRepository(db).get_brand_preference_heatmaps(brand_id, region="MENA")
        finally:
            db.close()

        assert heatmap["region_filter_applied"] is False
        assert heatmap["requested_region"] == "MENA"
        assert heatmap["region"] != "MENA"
        assert "top_colors" not in heatmap, "the forked key name must not come back"
        for dimension in ("top_aesthetics", "trending_colors", "top_occasions"):
            for cell in heatmap[dimension]:
                assert set(cell) >= {"name", "share", "count"}, cell
                assert "weight" not in cell, cell

    def test_shares_are_a_share_of_the_whole_distribution(self) -> None:
        rows: List[Row] = [(["a"], ["#AAAAAA"], "Casual")] * 8 + [(["b"], ["#BBBBBB"], "Casual")] * 5
        _seed(rows, STAMP)

        cells = {c["raw_name"]: c for c in _heatmap()["top_aesthetics"]}
        assert cells["a"]["count"] == 8 and cells["a"]["share"] == round(8 / 13 * 100, 1)
        assert cells["b"]["count"] == 5 and cells["b"]["share"] == round(5 / 13 * 100, 1)
        assert abs(cells["a"]["share"] + cells["b"]["share"] - 100.0) < 0.2
