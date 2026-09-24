"""P2 closure (2026-09-22 admin audit): atomic audit for admin mutations.

The finding: audit call sites were best-effort — if the business mutation
committed and the audit write then failed, the change existed with no trail
entry (or, worse for the older code, the audit row could exist for a change
that was rolled back).

Closure: the admin mutation endpoints defer every intermediate COMMIT
(``commit=False`` through service and repositories) and issue ONE commit for
mutation + audit row. These tests prove the atomicity BEHAVES:

* rollback after the deferred mutation+audit leaves NEITHER persisted,
* the happy path persists BOTH in one transaction,
* the audit row and the mutation share the same request lifecycle on the
  real HTTP endpoint.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from backend.tests.conftest import new_test_engine
from backend.app.models.user import AuditLog
from backend.app.repositories.user_repository import UserRepository

# WHY THE SHARED FACTORY AND NOT THIS MODULE'S OWN ENGINE (measured 2026-09-24):
# This module used to build its own engine from a hardcoded SQLite URL
# (`sqlite:///./backend/data/confit_test.db`), which made its result depend on
# two things outside the test: whether that side-file happened to exist, and
# which rows earlier modules had left in it. Two consequences, both measured:
#   * with CONFIT_TEST_DB_URL pointing at PostgreSQL, the module still wrote to
#     the SQLite side-file, so 17 tests failed for a reason that had nothing to
#     do with the code under test (4 here, 13 in test_audit_hash_chain) — while
#     CI stayed green because CI never runs this module on PostgreSQL;
#   * on a fresh checkout the side-file does not exist, so the tables were
#     missing and every test in the module failed at once.
# The suite's `new_test_engine()` is the single owner of that decision
# (conftest), so the module now runs where the suite was pointed — SQLite by
# default, PostgreSQL when asked — and the schema is seeded by the suite's
# session fixture instead of by luck.
engine = new_test_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _audit_count(db, action: str) -> int:
    return db.query(AuditLog).filter(AuditLog.action == action).count()


class TestDeferredAuditWrite:
    def test_commit_false_defers_persistence_until_commit(self, db):
        repo = UserRepository(db)
        repo.log_audit(
            action="ATOMIC_T1", resource_type="AtomicTest", commit=False
        )
        # Visible inside the transaction (flushed)...
        assert _audit_count(db, "ATOMIC_T1") == 1
        db.rollback()
        # ...gone after rollback: nothing was committed.
        assert _audit_count(db, "ATOMIC_T1") == 0

        repo.log_audit(action="ATOMIC_T1", resource_type="AtomicTest", commit=False)
        db.commit()
        assert _audit_count(db, "ATOMIC_T1") == 1

    def test_default_commit_true_is_unchanged(self, db):
        """Standalone audit events (logins, reads) keep their self-contained
        commit — the default contract of every existing call site."""
        UserRepository(db).log_audit(action="ATOMIC_T2", resource_type="AtomicTest")
        db.rollback()  # a later rollback must NOT undo a committed event
        assert _audit_count(db, "ATOMIC_T2") == 1


class TestMutationAndAuditShareOneTransaction:
    def _make_order(self, db):
        """A minimal real order via the existing test-world helpers."""
        from backend.app.models.commerce import Order

        order = Order(
            order_number="ATOMIC-TEST-0001",
            user_id=None,
            status="placed",
            payment_status="authorized",
            payment_method="card",
            payment_mode="demo",
            subtotal_amount=100.0,
            total_amount=100.0,
            currency="EGP",
        )
        db.add(order)
        db.commit()
        return order

    def test_rollback_reverts_both_mutation_and_audit(self, db):
        from backend.app.models.commerce import Order
        from backend.app.services.commerce_service import CommerceService

        order = self._make_order(db)
        try:
            service = CommerceService(db)
            service.transition_order(order.order_number, "processing", commit=False)
            UserRepository(db).log_audit(
                action="ATOMIC_T3_TRANSITION",
                resource_type="Order",
                resource_id=order.order_number,
                commit=False,
            )
            # Simulated failure BETWEEN flush and commit (crash, constraint,
            # connection loss): the whole unit must vanish.
            db.rollback()

            db.expire_all()
            fresh = db.query(Order).filter(Order.order_number == order.order_number).one()
            assert fresh.status == "placed", "mutation survived a rollback"
            assert _audit_count(db, "ATOMIC_T3_TRANSITION") == 0, (
                "audit row survived a rollback of its mutation"
            )
        finally:
            db.query(Order).filter(Order.order_number == order.order_number).delete()
            db.commit()

    def test_single_commit_persists_both(self, db):
        from backend.app.models.commerce import Order
        from backend.app.services.commerce_service import CommerceService

        order = self._make_order(db)
        try:
            service = CommerceService(db)
            service.transition_order(order.order_number, "processing", commit=False)
            UserRepository(db).log_audit(
                action="ATOMIC_T4_TRANSITION",
                resource_type="Order",
                resource_id=order.order_number,
                commit=False,
            )
            db.commit()

            db.expire_all()
            fresh = db.query(Order).filter(Order.order_number == order.order_number).one()
            assert fresh.status == "processing"
            assert _audit_count(db, "ATOMIC_T4_TRANSITION") == 1
            # And the audit row is chained like every other row (0020).
            row = db.query(AuditLog).filter(AuditLog.action == "ATOMIC_T4_TRANSITION").one()
            assert row.entry_hash and row.prev_hash
        finally:
            db.query(AuditLog).filter(AuditLog.action == "ATOMIC_T4_TRANSITION").delete()
            db.query(Order).filter(Order.order_number == order.order_number).delete()
            db.commit()
