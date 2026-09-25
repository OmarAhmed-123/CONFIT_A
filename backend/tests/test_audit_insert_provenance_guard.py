"""0024 database enforcement for low-id/raw audit INSERT forgery.

The HMAC verifiers cannot infer insertion time from attacker-controlled row
fields. A raw caller could previously insert an unsigned row with an explicit
id below the first signed id and have it classified as legacy. These tests use
real Alembic migrations and real database triggers rather than inspecting SQL
strings.
"""
from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.core.audit_chain import GENESIS_HASH, active_key_version, verify_chain
from backend.app.core.audit_insert_guard import (
    AUDIT_LOG_TRIGGER,
    VERIFICATION_RUN_TRIGGER,
)
from backend.app.core.audit_verification_chain import (
    RUN_GENESIS_HASH,
    verify_verification_runs,
)
from backend.app.models.user import AuditLog, AuditVerificationRun


def _alembic_config(url: str) -> Config:
    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def migrated_sqlite(tmp_path, monkeypatch):
    # env has priority over Config in env.py; a developer's migration override
    # must never redirect this destructive fixture away from its temp file.
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    url = f"sqlite:///{tmp_path / 'insert-guard.db'}"
    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        yield engine, cfg
    finally:
        engine.dispose()


def _legitimate_run() -> AuditVerificationRun:
    return AuditVerificationRun(
        window_days=30,
        checked_rows=1,
        sampled_rows=1,
        chained_rows=1,
        unchained_rows=0,
        break_count=0,
        verdict="ok",
        tamper_evident=True,
        head_hash="a" * 64,
        head_row_id=1,
        key_version=active_key_version(),
        canonical_version=1,
        triggered_by_user_id=None,
        request_id="0024-legitimate-run",
    )


def test_migrated_sqlite_installs_both_insert_guards(migrated_sqlite):
    engine, _ = migrated_sqlite
    # SQLAlchemy's SQLite inspector does not expose triggers; query the real
    # catalogue and assert both executable objects exist.
    with engine.connect() as conn:
        triggers = {
            row[0] for row in conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ))
        }
    assert {AUDIT_LOG_TRIGGER, VERIFICATION_RUN_TRIGGER} <= triggers


def test_legitimate_mapper_inserts_still_work(migrated_sqlite):
    engine, _ = migrated_sqlite
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        audit = AuditLog(action="0024_LEGITIMATE", resource_type="guard_test")
        db.add(audit)
        db.commit()
        db.refresh(audit)
        assert audit.prev_hash and audit.entry_hash and audit.chain_key_version

        run = _legitimate_run()
        db.add(run)
        db.commit()
        db.refresh(run)
        assert run.run_prev_hash and run.run_hash and run.run_hmac_key_version
    finally:
        db.close()


@pytest.mark.parametrize(
    "statement",
    [
        """
        INSERT INTO audit_logs
            (id, action, resource_type, timestamp)
        VALUES
            (-900001, 'RAW_LOW_ID', 'guard_test', CURRENT_TIMESTAMP)
        """,
        """
        INSERT INTO audit_verification_runs
            (id, run_at, window_days, checked_rows, sampled_rows, chained_rows,
             unchained_rows, break_count, verdict, tamper_evident, key_version,
             canonical_version)
        VALUES
            (-900001, CURRENT_TIMESTAMP, 30, 1, 1, 1, 0, 0, 'ok', 1, 1, 1)
        """,
    ],
)
def test_unsigned_explicit_low_id_insert_is_rejected(migrated_sqlite, statement):
    engine, _ = migrated_sqlite
    with pytest.raises(IntegrityError, match="requires signed chain provenance"):
        with engine.begin() as conn:
            conn.execute(text(statement))


def test_non_null_forgery_is_accepted_for_verification_and_then_detected(migrated_sqlite):
    """The DB checks provenance presence; HMAC verification checks truth.

    PostgreSQL cannot validate an app-held HMAC secret. A runtime attacker can
    submit non-NULL garbage, but choosing a low id no longer hides it as legacy:
    both verifiers report the invalid HMAC/link.
    """
    engine, _ = migrated_sqlite
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_logs
                (id, action, resource_type, timestamp, prev_hash, entry_hash,
                 chain_key_version)
            VALUES
                (-800001, 'FORGED_LOW_ID', 'guard_test', CURRENT_TIMESTAMP,
                 :prev, :bad_hash, 1)
        """), {"prev": GENESIS_HASH, "bad_hash": "f" * 64})
        conn.execute(text("""
            INSERT INTO audit_verification_runs
                (id, run_at, window_days, checked_rows, sampled_rows,
                 chained_rows, unchained_rows, break_count, verdict,
                 tamper_evident, key_version, canonical_version, run_prev_hash,
                 run_hash, run_hmac_key_version)
            VALUES
                (-800001, CURRENT_TIMESTAMP, 30, 1, 1, 1, 0, 0, 'ok', 1,
                 1, 1, :prev, :bad_hash, 1)
        """), {"prev": RUN_GENESIS_HASH, "bad_hash": "e" * 64})

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        audit_rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
        run_rows = db.query(AuditVerificationRun).order_by(AuditVerificationRun.id.asc()).all()
        audit_result = verify_chain(audit_rows, expected_prev=GENESIS_HASH)
        run_result = verify_verification_runs(run_rows, expected_prev=RUN_GENESIS_HASH)
        assert not audit_result["intact"]
        assert "entry_hash_mismatch" in {item["issue"] for item in audit_result["breaks"]}
        assert not run_result["intact"]
        assert "verification_run_hash_mismatch" in {
            item["issue"] for item in run_result["breaks"]
        }
    finally:
        db.close()


def test_downgrade_then_upgrade_preserves_legacy_but_reenforces_new_rows(migrated_sqlite):
    engine, cfg = migrated_sqlite
    command.downgrade(cfg, "0023_verification_run_hmac_chain")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_logs
                (id, action, resource_type, timestamp)
            VALUES
                (-700001, 'LEGACY_WHILE_GUARD_ABSENT', 'guard_test', CURRENT_TIMESTAMP)
        """))
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        legacy = conn.execute(text(
            "SELECT entry_hash FROM audit_logs WHERE id=-700001"
        )).scalar_one()
    assert legacy is None, "upgrade must not rewrite or falsely sign legacy evidence"

    with pytest.raises(IntegrityError, match="requires signed chain provenance"):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO audit_logs
                    (id, action, resource_type, timestamp)
                VALUES
                    (-700002, 'NEW_UNSIGNED_AFTER_REUPGRADE', 'guard_test', CURRENT_TIMESTAMP)
            """))
