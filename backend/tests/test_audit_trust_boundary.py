"""Behavioural gates for the audit trust boundary (2026-09-24 re-audit).

The re-audit of PRs #187-#189 verified the chain works, then attacked what it
does NOT cover. Every test here proves a specific finding is closed by
BEHAVING, not by asserting configuration:

* key rotation K1→K2: old rows verify with the retired key, mixed-version
  chains verify, a wrong retired key is caught, a MISSING retired key fails
  closed (key_unavailable) instead of quietly passing;
* canonical-separator injection: a field containing the \\x1f separator can
  no longer be used to craft two different rows with identical canonical
  bytes — the single write path sanitises it;
* window verification anchors against the row's ACTUAL database predecessor,
  so deleting rows just before the window (or the whole earlier chain) is
  detected — previously invisible;
* an unchained row written AFTER chaining began is flagged as
  chain_bypass_suspected, never excused as "legacy";
* no production code path can insert AuditLog rows around the mapper
  listener (static completeness gate + the behavioural detection above);
* on PostgreSQL, the 0022 append-only guard actually rejects
  UPDATE/DELETE/TRUNCATE (skipped on SQLite — documented parity limit).
"""

from __future__ import annotations

import os
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.tests.conftest import new_test_engine
from backend.app.core.config import settings
from backend.app.core.audit_chain import (
    GENESIS_HASH,
    AuditKeyUnavailableError,
    canonical_string,
    compute_entry_hash,
    resolve_key,
    verify_chain,
)
from backend.app.models.user import AuditLog
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.audit_service import AuditTrailService

engine = new_test_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

OLD_KEY = "old-rotation-key-material-with-plenty-of-entropy-v1"
NEW_KEY = "new-rotation-key-material-with-plenty-of-entropy-v2"


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        # Tests share one database: leave no audit rows behind.
        cleanup = SessionLocal()
        try:
            cleanup.execute(text("DELETE FROM audit_verification_runs"))
            cleanup.execute(text("DELETE FROM audit_logs"))
            cleanup.commit()
        finally:
            cleanup.close()
        session.close()


def _write(db, action: str, **kwargs) -> None:
    UserRepository(db).log_audit(action=action, resource_type="governance_test", **kwargs)


def _rows(db):
    return (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "governance_test")
        .order_by(AuditLog.id.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Key lifecycle: rotation K1 → K2
# ---------------------------------------------------------------------------

class TestKeyRotation:
    def test_rotation_keeps_old_rows_verifiable(self, db, monkeypatch):
        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", OLD_KEY)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 1)
        _write(db, "ROTATION_ROW_1")
        _write(db, "ROTATION_ROW_2")

        # Rotate: new active key v2, retired v1 published as env var.
        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", NEW_KEY)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 2)
        monkeypatch.setenv("AUDIT_HMAC_KEY_V1", OLD_KEY)
        _write(db, "ROTATION_ROW_3")  # written under v2

        rows = _rows(db)
        assert [r.chain_key_version for r in rows] == [1, 1, 2]
        # expected_prev=None: window semantics — other suite modules may have
        # written earlier audit rows, so GENESIS is not this row's anchor.
        result = verify_chain(rows, expected_prev=None)
        assert result["intact"], result["breaks"]
        assert result["rows_verified"] == 3

    def test_wrong_retired_key_is_caught(self, db, monkeypatch):
        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", OLD_KEY)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 1)
        _write(db, "ROTATION_ROW_1")

        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", NEW_KEY)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 2)
        monkeypatch.setenv("AUDIT_HMAC_KEY_V1", "not-the-key-that-signed-those-rows")

        result = verify_chain(_rows(db), expected_prev=None)
        assert not result["intact"]
        assert {b["issue"] for b in result["breaks"]} == {"entry_hash_mismatch"}

    def test_missing_retired_key_fails_closed(self, db, monkeypatch):
        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", OLD_KEY)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 1)
        _write(db, "ROTATION_ROW_1")

        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", NEW_KEY)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 2)
        monkeypatch.delenv("AUDIT_HMAC_KEY_V1", raising=False)

        with pytest.raises(AuditKeyUnavailableError):
            resolve_key(1)
        result = verify_chain(_rows(db), expected_prev=None)
        assert not result["intact"]
        assert result["breaks"][0]["issue"] == "key_unavailable"


# ---------------------------------------------------------------------------
# Canonicalisation: determinism + separator injection
# ---------------------------------------------------------------------------

class TestCanonicalisation:
    KWARGS = dict(
        user_id=7, action="X", resource_type="user", resource_id="9",
        ip_address="10.0.0.1", details_json='{"a": 1}', before_json=None,
        after_json=None, request_id="req-1", timestamp=None,
        prev_hash=GENESIS_HASH,
    )

    def test_identical_data_identical_bytes(self):
        a = canonical_string(**self.KWARGS)
        b = canonical_string(**self.KWARGS)
        assert a == b
        key = b"k" * 32
        assert compute_entry_hash(a, key) == compute_entry_hash(b, key)

    def test_meaningful_change_changes_digest(self):
        base = canonical_string(**self.KWARGS)
        for field, value in [("action", "Y"), ("details_json", '{"a": 2}'),
                             ("user_id", 8), ("prev_hash", "f" * 64)]:
            changed = canonical_string(**{**self.KWARGS, field: value})
            assert changed != base, field

    def test_field_shift_produces_different_bytes(self):
        # Moving content across a field boundary must never collide.
        a = canonical_string(**{**self.KWARGS, "action": "A", "resource_type": "B C"})
        b = canonical_string(**{**self.KWARGS, "action": "A B", "resource_type": "C"})
        assert a != b

    def test_separator_injection_is_sanitised_at_the_write_path(self, db):
        # Attacker-influenced field (ip_address via X-Forwarded-For) tries to
        # smuggle the \x1f separator to forge a canonical-bytes collision.
        db.add(AuditLog(user_id=None, action="SEP_INJECT", resource_type="governance_test",
                        ip_address="1.2.3.4\x1fEVIL"))
        db.commit()
        row = _rows(db)[-1]
        assert "\x1f" not in (row.ip_address or ""), "raw separator must never be stored"
        # The stored row's own HMAC verifies (the sanitised value was hashed).
        assert verify_chain([row])["intact"]

    def test_crafted_collision_pair_hashes_differently(self, db):
        db.add(AuditLog(user_id=None, action="P1", resource_type="governance_test",
                        resource_id="a\x1fb", ip_address=""))
        db.commit()
        db.add(AuditLog(user_id=None, action="P1", resource_type="governance_test",
                        resource_id="a", ip_address="b"))
        db.commit()
        r1, r2 = _rows(db)[-2:]
        assert r1.entry_hash != r2.entry_hash


# ---------------------------------------------------------------------------
# Verification coverage: predecessor anchoring + bypass classification
# ---------------------------------------------------------------------------

class TestVerificationCoverage:
    def test_coverage_semantics_are_explicit_on_the_wire(self, db):
        _write(db, "COV_1")
        report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        cov = report["coverage"]
        assert cov["mode"] == "window_sample"
        assert cov["full_history"] is False
        assert cov["sample_limit"] == 10
        assert "verify_audit_chain" in cov["full_history_procedure"]

    def test_deletion_just_before_the_window_is_detected(self, db):
        for i in range(6):
            _write(db, f"ANCHOR_{i}")
        rows = _rows(db)
        # Delete the row immediately preceding the newest 3 (the "window").
        victim = rows[2]
        db.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": victim.id})
        db.commit()

        report = AuditTrailService(db).integrity(window_days=30, sample_limit=3)
        issues = {v["issue"] for v in report["violations"]}
        assert "chain_link_mismatch" in issues, report["violations"]
        assert report["tamper_evident"] is False

    def test_deleting_the_entire_earlier_chain_is_detected(self, db):
        for i in range(5):
            _write(db, f"GENESIS_{i}")
        rows = _rows(db)
        db.execute(text("DELETE FROM audit_logs WHERE id <= :id"), {"id": rows[1].id})
        db.commit()

        # The surviving first chained row claims a predecessor that is gone;
        # with no chained predecessor left, it must anchor to GENESIS — and
        # does not.
        report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        issues = {v["issue"] for v in report["violations"]}
        assert "chain_link_mismatch" in issues

    def test_bypass_row_is_flagged_not_excused_as_legacy(self, db):
        _write(db, "CHAINED_1")
        # Core-table insert skips the mapper listener — exactly how a bypass
        # would look in production.
        db.execute(AuditLog.__table__.insert().values(
            action="BYPASS", resource_type="governance_test"))
        db.commit()

        report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        issues = {v["issue"] for v in report["violations"]}
        assert "chain_bypass_suspected" in issues
        assert report["chain"]["bypass_suspected_rows"] == 1
        assert report["tamper_evident"] is False

    def test_true_legacy_rows_are_not_flagged_as_bypass(self, db):
        # Unchained row BEFORE any chained row = legacy, not bypass.
        db.execute(AuditLog.__table__.insert().values(
            action="LEGACY", resource_type="governance_test"))
        db.commit()
        _write(db, "CHAINED_AFTER_LEGACY")

        report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        issues = {v["issue"] for v in report["violations"]}
        assert "chain_bypass_suspected" not in issues
        assert report["chain"]["bypass_suspected_rows"] == 0


# ---------------------------------------------------------------------------
# Write-path completeness: no production path may skip the listener
# ---------------------------------------------------------------------------

def test_no_production_code_bulk_inserts_audit_rows():
    """Static completeness gate: the mapper listener only fires for ORM
    ``session.add`` flushes. Any bulk/Core insert of AuditLog in production
    code would silently write unchained rows (the behavioural tests above
    prove such rows are at least DETECTED; this gate keeps them from being
    written at all)."""
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for needle in ("bulk_save_objects", "bulk_insert_mappings",
                       "AuditLog.__table__.insert", "insert(AuditLog"):
            if needle in source:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# PostgreSQL append-only guard (migration 0022)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(engine.dialect.name != "postgresql",
                    reason="0022 guard is PostgreSQL-only (documented parity "
                           "limitation; SQLite has no privilege system)")
class TestAppendOnlyGuardPostgres:
    @pytest.fixture(autouse=True)
    def guard(self, db):
        from backend.app.core.audit_db_guard import guard_install_sql, guard_remove_sql
        for stmt in guard_install_sql():
            db.execute(text(stmt))
        db.commit()
        yield
        for stmt in guard_remove_sql():
            db.execute(text(stmt))
        db.commit()

    def test_update_delete_truncate_are_rejected(self, db):
        _write(db, "GUARDED")
        row_id = _rows(db)[-1].id
        for stmt in (
            "UPDATE audit_logs SET action = 'FORGED' WHERE id = :id",
            "DELETE FROM audit_logs WHERE id = :id",
        ):
            with pytest.raises(Exception) as excinfo:
                db.execute(text(stmt), {"id": row_id})
                db.commit()
            db.rollback()
            assert "append-only" in str(excinfo.value)
        with pytest.raises(Exception) as excinfo:
            db.execute(text("TRUNCATE audit_logs"))
            db.commit()
        db.rollback()
        assert "append-only" in str(excinfo.value)

    def test_insert_still_works_under_guard(self, db):
        _write(db, "GUARDED_INSERT_OK")
        assert _rows(db)[-1].entry_hash is not None
