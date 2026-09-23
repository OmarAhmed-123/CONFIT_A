"""Behavioural gates for the tamper-evident audit chain (P0 closure).

The 2026-09-22 admin audit found ``tamper_evident: false``: audit_logs had no
persisted hash chain, so direct-DB edits of history were undetectable. These
tests prove the closure BEHAVES — they write real rows through the real write
path, then tamper with the database directly and assert the verifier catches
every class of attack it claims to catch:

* row content modified after write        -> entry_hash_mismatch
* row deleted from the middle             -> chain_link_mismatch
* rows written before the migration       -> reported as unchained, not signed
* every insert path is chained            -> repository, partner-lead, mapper
* the integrity endpoint reports it all   -> tamper_evident computed, not asserted

No ``inspect.getsource`` assertions, no docstring checks — that is exactly the
test style that let the original gap survive review (G-16).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.audit_chain import (
    GENESIS_HASH,
    active_key_version,
    entry_hash_for_row,
    resolve_key,
    verify_chain,
)
from backend.app.models.user import AuditLog
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.audit_service import AuditTrailService

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _write(db, action: str, **kwargs) -> None:
    UserRepository(db).log_audit(
        action=action, resource_type=kwargs.pop("resource_type", "ChainTest"), **kwargs
    )


def _rows(db, actions):
    return (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(actions))
        .order_by(AuditLog.id.asc())
        .all()
    )


class TestChainWritePath:
    def test_every_repository_write_is_chained(self, db):
        _write(db, "CHAIN_T1_A", details="first")
        _write(db, "CHAIN_T1_B", details="second")
        rows = _rows(db, ["CHAIN_T1_A", "CHAIN_T1_B"])
        assert len(rows) == 2
        for row in rows:
            assert row.entry_hash and len(row.entry_hash) == 64
            assert row.prev_hash and len(row.prev_hash) == 64
            assert row.chain_key_version == active_key_version()
        # Second row must link to the first (they were written back-to-back
        # on the same session; no other writer runs inside this test).
        assert rows[1].prev_hash == rows[0].entry_hash

    def test_hmac_recomputes_from_row_content(self, db):
        _write(db, "CHAIN_T2", details="content-bound")
        row = _rows(db, ["CHAIN_T2"])[0]
        key = resolve_key(row.chain_key_version)
        assert entry_hash_for_row(row, row.prev_hash, key) == row.entry_hash

    def test_direct_orm_add_is_also_chained(self, db):
        """The listener lives on the mapper, not in the repository — an
        AuditLog added directly (partner-lead / catalog-import style) must be
        chained too. This is the DRY guarantee: no unchained write path."""
        db.add(AuditLog(action="CHAIN_T3_DIRECT", resource_type="ChainTest"))
        db.commit()
        row = _rows(db, ["CHAIN_T3_DIRECT"])[0]
        assert row.entry_hash and row.prev_hash

    def test_batch_flush_does_not_fork_the_chain(self, db):
        """Multiple rows flushed in ONE commit must still chain linearly —
        the in-flight head cache, not a stale SELECT, links them."""
        db.add(AuditLog(action="CHAIN_T4_BATCH", resource_type="ChainTest", details_json="1"))
        db.add(AuditLog(action="CHAIN_T4_BATCH", resource_type="ChainTest", details_json="2"))
        db.add(AuditLog(action="CHAIN_T4_BATCH", resource_type="ChainTest", details_json="3"))
        db.commit()
        rows = _rows(db, ["CHAIN_T4_BATCH"])
        assert len(rows) == 3
        assert rows[1].prev_hash == rows[0].entry_hash
        assert rows[2].prev_hash == rows[1].entry_hash


class TestTamperDetection:
    def test_modified_row_fails_its_hmac(self, db):
        _write(db, "CHAIN_T5_A", details="original")
        _write(db, "CHAIN_T5_B", details="witness")
        victim = _rows(db, ["CHAIN_T5_A"])[0]
        # Attacker with direct DB access rewrites history, bypassing the ORM.
        db.execute(
            text("UPDATE audit_logs SET details_json='forged' WHERE id=:id"),
            {"id": victim.id},
        )
        db.commit()
        db.expire_all()
        report = verify_chain(_rows(db, ["CHAIN_T5_A", "CHAIN_T5_B"]))
        assert not report["intact"]
        issues = {b["issue"] for b in report["breaks"]}
        assert "entry_hash_mismatch" in issues
        assert any(b["row_id"] == victim.id for b in report["breaks"])

    def test_deleted_row_breaks_the_link(self, db):
        _write(db, "CHAIN_T6_A", details="1")
        _write(db, "CHAIN_T6_B", details="2")
        _write(db, "CHAIN_T6_C", details="3")
        rows = _rows(db, ["CHAIN_T6_A", "CHAIN_T6_B", "CHAIN_T6_C"])
        db.execute(text("DELETE FROM audit_logs WHERE id=:id"), {"id": rows[1].id})
        db.commit()
        db.expire_all()
        survivors = _rows(db, ["CHAIN_T6_A", "CHAIN_T6_C"])
        # Anchor on the first survivor's own prev link; the gap must surface.
        report = verify_chain(survivors, expected_prev=survivors[0].prev_hash)
        assert not report["intact"]
        assert any(b["issue"] == "chain_link_mismatch" for b in report["breaks"])

    def test_untampered_chain_verifies(self, db):
        for i in range(5):
            _write(db, "CHAIN_T7", details=f"row-{i}")
        report = verify_chain(_rows(db, ["CHAIN_T7"]))
        assert report["intact"]
        assert report["rows_verified"] == 5
        assert report["breaks"] == []

    def test_pre_migration_rows_are_reported_not_resigned(self, db):
        _write(db, "CHAIN_T8_LEGACY", details="then nulled")
        row = _rows(db, ["CHAIN_T8_LEGACY"])[0]
        db.execute(
            text(
                "UPDATE audit_logs SET entry_hash=NULL, prev_hash=NULL, "
                "chain_key_version=NULL WHERE id=:id"
            ),
            {"id": row.id},
        )
        db.commit()
        db.expire_all()
        report = verify_chain(_rows(db, ["CHAIN_T8_LEGACY"]))
        assert report["unchained_rows"] == 1
        assert report["rows_verified"] == 0
        # Legacy rows are an honest gap, never a fabricated verification.
        assert report["intact"]  # no *breaks* — but nothing was claimed either


class TestIntegrityEndpointBehaviour:
    def test_service_reports_chain_and_tamper_evident(self, db):
        _write(db, "CHAIN_T9", details="for endpoint")
        result = AuditTrailService(db).integrity(window_days=30)
        assert "chain" in result
        assert result["chain"]["chained_rows"] >= 1
        # tamper_evident is COMPUTED: chained rows exist and verified.
        if not result["chain"]["breaks"] and not result["violations"]:
            assert result["tamper_evident"] is True
        assert isinstance(result["limitations"], list) and result["limitations"]

    def test_service_flags_tampering_in_violations(self, db):
        _write(db, "CHAIN_T10", details="pristine")
        row = _rows(db, ["CHAIN_T10"])[0]
        db.execute(
            text("UPDATE audit_logs SET details_json='rewritten' WHERE id=:id"),
            {"id": row.id},
        )
        db.commit()
        db.expire_all()
        result = AuditTrailService(db).integrity(window_days=30)
        assert result["tamper_evident"] is False
        assert result["verdict"] == "violations_found"
        assert any(
            v.get("issue") in {"entry_hash_mismatch", "chain_link_mismatch"}
            for v in result["violations"]
        )

    def test_key_separation_from_jwt_secret(self):
        """The chain key must never equal the JWT signing key — a JWT key
        leak alone must not allow re-forging the audit chain."""
        from backend.app.core.config import settings

        assert resolve_key(1) != settings.SECRET_KEY.encode("utf-8")
