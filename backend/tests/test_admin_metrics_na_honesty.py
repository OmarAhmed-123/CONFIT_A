"""P1 closure (2026-09-22 admin audit): N/A instead of fabricated zeros.

The finding: "فرض minimum sample sizes وN/A بدل أرقام صفرية توحي بدقة غير
موجودة" — a rate whose denominator is zero used to publish 0.0, which reads
as a *measured* zero ("nobody adopted try-on", "no returns happen") when in
fact nothing was measured at all.

Contract pinned here: zero denominator -> None on the wire (JSON null),
rendered N/A by the UI. A real measured zero (denominator > 0, numerator 0)
still publishes 0.0 — the two facts stay distinguishable.

These tests run against an EMPTY isolated database — the exact world where
the fabricated zeros used to appear.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.repositories.brand_repository import BrandRepository


@pytest.fixture()
def empty_db(tmp_path):
    """A schema-complete but data-empty database: zero orders, zero outfits,
    zero brands — every denominator in the analytics payload is zero."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/empty_metrics.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestZeroDenominatorPublishesNull:
    def test_platform_analytics_rates_are_none_not_zero(self, empty_db):
        data = BrandRepository(empty_db).get_platform_admin_analytics()
        assert data["total_orders"] == 0
        # Nothing was measured — the payload must say "unmeasured", not "0%".
        assert data["tryon_adoption_rate"] is None
        assert data["stylist_conversion_ratio"] is None
        assert data["platform_avg_return_rate"] is None
        assert data["return_rate_tryon_users"] is None
        assert data["return_rate_non_tryon_users"] is None
        assert data["outfit_to_purchase_ratio"] is None

    def test_outfit_to_purchase_ratio_is_none_without_saved_outfits(self, empty_db):
        data = BrandRepository(empty_db).get_outfit_to_purchase_ratio()
        assert data["total_saved_outfits"] == 0
        assert data["outfit_to_purchase_ratio"] is None
        # The methodology must explain the null so no consumer guesses.
        assert "null" in data["methodology"]

    def test_return_reduction_metrics_are_none_without_cohorts(self, empty_db):
        data = BrandRepository(empty_db).get_return_reduction_metrics()
        assert data["total_orders"] == 0
        assert data["platform_avg_return_rate"] is None
        assert data["return_rate_tryon_users"] is None
        assert data["return_rate_non_tryon_users"] is None
        # The headline reduction claim requires BOTH cohorts measured.
        assert data["return_reduction_percentage"] is None


class TestFinancialSemanticsSeparation:
    """P1: attribution figures are operational metrics, not a billing ledger.
    The separation must be ON THE WIRE, not just in a docstring."""

    def test_revenue_attribution_declares_itself_non_ledger(self, empty_db):
        data = BrandRepository(empty_db).get_revenue_attribution()
        assert "financial_semantics" in data
        assert "NOT a verified billing ledger" in data["financial_semantics"]

    def test_admin_analytics_schema_declares_semantics(self):
        from backend.app.schemas.brand import AdminPlatformAnalyticsOut

        field = AdminPlatformAnalyticsOut.model_fields["financial_semantics"]
        assert "operational_metrics" in str(field.default)
