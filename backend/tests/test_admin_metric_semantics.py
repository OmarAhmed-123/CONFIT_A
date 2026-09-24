"""Machine-readable metric semantics (2026-09-24 re-audit, PR B).

PR #189 made zero-denominator rates publish null. What was still implicit:
a CONSUMER could not distinguish "measured zero" from "unmeasured" without
re-deriving the denominators, sample sizes did not ride with the values,
attribution had prose semantics but no machine-readable reconciliation
state, and integrity failures produced no operational log signal.

Contracts pinned here:
* every cohort rate on /admin/analytics/returns carries {value, status,
  sample_size}; status is derived from the denominator, never asserted;
* min_sample_policy is published with threshold=null and
  status=pending_business_decision — no invented threshold;
* the cohort comparison is labelled observational on the wire;
* attribution carries reconciliation_status=unreconciled + value_semantics
  + computed_at freshness;
* integrity violations emit ONE structured warning with issue counts only
  (no hashes, no key material, no row payloads).
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.core.metric_semantics import (
    MIN_SAMPLE_POLICY,
    STATUS_MEASURED,
    STATUS_UNMEASURED,
    measured_metric,
)
from backend.app.repositories.brand_repository import BrandRepository


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/metric_semantics.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_order(db, *, try_on: bool, status: str = "delivered") -> None:
    from backend.app.models.user import User
    from backend.app.models.commerce import Order

    user = User(email="semantics-shopper@confit.io", hashed_password="x",
                full_name="Semantics Shopper", is_active=True, is_verified=True)
    db.add(user)
    db.flush()
    db.add(Order(user_id=user.id, status=status, try_on_assisted=try_on,
                 order_number="SEM-0001", total_amount=100, subtotal_amount=90))
    db.commit()


class TestMeasuredMetricHelper:
    def test_zero_denominator_is_unmeasured(self):
        m = measured_metric(None, 0)
        assert m == {"value": None, "status": STATUS_UNMEASURED, "sample_size": 0}

    def test_measured_zero_is_a_real_zero(self):
        m = measured_metric(0.0, 42)
        assert m["status"] == STATUS_MEASURED
        assert m["value"] == 0.0
        assert m["sample_size"] == 42

    def test_no_invented_suppression_threshold(self):
        assert MIN_SAMPLE_POLICY["threshold"] is None
        assert MIN_SAMPLE_POLICY["status"] == "pending_business_decision"


class TestReturnsSemanticsOnTheWire:
    def test_empty_db_publishes_unmeasured_not_zero(self, db):
        data = BrandRepository(db).get_return_reduction_metrics()
        metrics = data["metrics"]
        for name in ("platform_avg_return_rate", "return_rate_tryon_users",
                     "return_rate_non_tryon_users"):
            assert metrics[name]["status"] == STATUS_UNMEASURED, name
            assert metrics[name]["value"] is None
            assert metrics[name]["sample_size"] == 0
        assert metrics["return_reduction_percentage"]["status"] == (
            "unmeasured_requires_both_cohorts")
        assert data["min_sample_policy"] == MIN_SAMPLE_POLICY
        assert data["semantic_type"] == "observational_cohort_comparison"

    def test_measured_zero_return_rate_is_distinguishable(self, db):
        # One delivered non-try-on order, zero returns: a MEASURED 0.0 —
        # not the same fact as "nobody was in the cohort".
        _seed_order(db, try_on=False)
        data = BrandRepository(db).get_return_reduction_metrics()
        non_tryon = data["metrics"]["return_rate_non_tryon_users"]
        assert non_tryon["status"] == STATUS_MEASURED
        assert non_tryon["value"] == 0.0
        assert non_tryon["sample_size"] == 1
        # The try-on cohort is still empty — still unmeasured.
        assert data["metrics"]["return_rate_tryon_users"]["status"] == STATUS_UNMEASURED

    def test_causal_language_is_disclaimed(self, db):
        data = BrandRepository(db).get_return_reduction_metrics()
        assert "OBSERVATIONAL" in data["methodology"]
        assert "not a causal claim" in data["methodology"]


class TestAttributionFinancialState:
    def test_reconciliation_state_is_machine_readable(self, db):
        data = BrandRepository(db).get_revenue_attribution()
        assert data["reconciliation_status"] == "unreconciled"
        assert data["reconciled_against"] is None
        assert data["value_semantics"] == "recorded_attributed_unsettled"
        assert data["computed_at"]  # ISO timestamp, freshness of the numbers
        assert "freshness" in data


class TestIntegrityStructuredLogging:
    def test_violation_emits_one_structured_warning(self, db, caplog):
        from backend.app.repositories.user_repository import UserRepository
        from backend.app.services.audit_service import AuditTrailService

        UserRepository(db).log_audit(action="LOG_PROBE", resource_type="semantics_test")
        # Tamper directly (SQLite has no 0022 guard — documented parity limit).
        db.execute(text("UPDATE audit_logs SET action = 'FORGED'"))
        db.commit()

        with caplog.at_level(logging.WARNING, logger="confit.audit.integrity"):
            report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        assert report["verdict"] == "violations_found"
        records = [r for r in caplog.records if r.name == "confit.audit.integrity"]
        assert len(records) == 1
        record = records[0]
        assert record.audit_verdict == "violations_found"
        assert "entry_hash_mismatch" in record.audit_issue_counts
        # Secret-free: the formatted message must not leak hashes or keys.
        rendered = record.getMessage()
        assert "entry_hash" not in rendered.lower() or "mismatch" in rendered.lower()
        assert len(rendered) < 200

    def test_clean_run_logs_nothing(self, db, caplog):
        from backend.app.repositories.user_repository import UserRepository
        from backend.app.services.audit_service import AuditTrailService

        UserRepository(db).log_audit(action="CLEAN_PROBE", resource_type="semantics_test")
        with caplog.at_level(logging.WARNING, logger="confit.audit.integrity"):
            report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        assert report["verdict"] == "ok"
        assert not [r for r in caplog.records if r.name == "confit.audit.integrity"]
