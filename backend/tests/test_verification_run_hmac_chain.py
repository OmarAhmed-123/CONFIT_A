"""0023: authenticity/integrity gates for audit_verification_runs.

0022 proved UPDATE/DELETE/TRUNCATE are DB-blocked in PostgreSQL. These tests
cover the remaining INSERT/provenance threat: a runtime credential can INSERT,
so raw/forged rows must be detectable and real runs must be HMAC chained.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.audit_chain import active_key_version
from backend.app.core.audit_verification_chain import (
    RUN_GENESIS_HASH,
    canonical_run,
    hash_run,
    verify_verification_runs,
)
from backend.app.core.config import settings
from backend.app.core.database import Base
from backend.app.main import app
from backend.app.models.user import AuditVerificationRun
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.audit_service import AuditTrailService
from backend.tests.conftest import new_test_engine

PG_ENGINE = new_test_engine()


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/run_chain.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _run(db, *, verdict="ok", request_id=None) -> AuditVerificationRun:
    row = AuditVerificationRun(
        window_days=30,
        checked_rows=7,
        sampled_rows=7,
        chained_rows=7,
        unchained_rows=0,
        break_count=0,
        verdict=verdict,
        tamper_evident=True,
        head_hash="a" * 64,
        head_row_id=7,
        key_version=active_key_version(),
        canonical_version=1,
        triggered_by_user_id=None,
        request_id=request_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _rows(db):
    return db.query(AuditVerificationRun).order_by(AuditVerificationRun.id.asc()).all()


class TestRunWritePath:
    def test_mapper_insert_is_domain_separated_and_chained(self, db):
        first = _run(db, request_id="run-1")
        second = _run(db, request_id="run-2")
        assert first.run_prev_hash == RUN_GENESIS_HASH
        assert first.run_hash
        assert second.run_prev_hash == first.run_hash
        assert second.run_hash != first.run_hash
        assert second.run_hmac_key_version == active_key_version()
        result = verify_verification_runs(_rows(db), expected_prev=RUN_GENESIS_HASH)
        assert result["intact"], result["breaks"]
        # Domain separation: same root key/canonical text is not the audit-log
        # HMAC domain; the run helper must reproduce its own hash exactly.
        assert second.run_hash == hash_run(
            second, second.run_prev_hash, second.run_hmac_key_version
        )

    def test_canonical_run_is_deterministic_and_meaningful_changes_differ(self, db):
        row = _run(db)
        a = canonical_run(row, row.run_prev_hash)
        assert a == canonical_run(row, row.run_prev_hash)
        row.checked_rows += 1
        assert canonical_run(row, row.run_prev_hash) != a

    def test_separator_injection_is_normalised_before_hashing(self, db):
        row = _run(db, request_id="left\x1fright")
        assert "\x1f" not in row.request_id
        assert row.request_id == "left\\u001fright"
        assert verify_verification_runs(_rows(db), expected_prev=RUN_GENESIS_HASH)["intact"]


class TestRunTampering:
    def test_modified_run_hash_fails(self, db):
        row = _run(db)
        db.execute(text(
            "UPDATE audit_verification_runs SET verdict='forged' WHERE id=:id"
        ), {"id": row.id})
        db.commit()
        result = verify_verification_runs(_rows(db), expected_prev=RUN_GENESIS_HASH)
        assert not result["intact"]
        assert "verification_run_hash_mismatch" in {b["issue"] for b in result["breaks"]}

    def test_deleted_middle_run_breaks_successor_link(self, db):
        first = _run(db, request_id="first")
        middle = _run(db, request_id="middle")
        last = _run(db, request_id="last")
        assert last.run_prev_hash == middle.run_hash
        db.execute(text("DELETE FROM audit_verification_runs WHERE id=:id"), {"id": middle.id})
        db.commit()
        result = verify_verification_runs(_rows(db), expected_prev=RUN_GENESIS_HASH)
        assert not result["intact"]
        assert "verification_run_link_mismatch" in {b["issue"] for b in result["breaks"]}
        assert first.run_hash != last.run_prev_hash

    def test_reordered_runs_break_linkage(self, db):
        first = _run(db, request_id="ordered-1")
        second = _run(db, request_id="ordered-2")
        third = _run(db, request_id="ordered-3")
        result = verify_verification_runs(
            [first, third, second], expected_prev=RUN_GENESIS_HASH
        )
        assert not result["intact"]
        assert "verification_run_link_mismatch" in {b["issue"] for b in result["breaks"]}

    def test_raw_forged_insert_is_reported_by_real_integrity_service(self, db):
        UserRepository(db).log_audit(action="CHAIN_ORIGIN", resource_type="RunForgeryTest")
        _run(db, request_id="signed-before-forgery")
        # Core insert bypasses mapper event exactly like direct SQL/runtime DB
        # credential. All business fields look plausible; only provenance is
        # missing, which is the property 0023 adds.
        db.execute(AuditVerificationRun.__table__.insert().values(
            run_at=datetime.now(timezone.utc).replace(tzinfo=None),
            window_days=30, checked_rows=1, sampled_rows=1,
            chained_rows=1, unchained_rows=0, break_count=0,
            verdict="ok", tamper_evident=True, head_hash="a" * 64,
            head_row_id=1, key_version=1, canonical_version=1,
            request_id="raw-forgery",
        ))
        db.commit()
        report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        issues = {v["issue"] for v in report["violations"]}
        assert "verification_run_forgery_suspected" in issues
        assert report["verification_runs"]["forgery_suspected_rows"] == 1
        assert report["verification_runs"]["intact"] is False
        assert report["tamper_evident"] is False

    def test_wrong_run_key_version_fails_closed(self, db):
        row = _run(db)
        db.execute(text(
            "UPDATE audit_verification_runs SET run_hmac_key_version=999 WHERE id=:id"
        ), {"id": row.id})
        db.commit()
        result = verify_verification_runs(_rows(db), expected_prev=RUN_GENESIS_HASH)
        assert not result["intact"]
        assert result["breaks"][0]["issue"] == "verification_run_key_unavailable"

    def test_deleted_tail_is_detected_through_independent_audit_crosslink(self, db):
        UserRepository(db).log_audit(
            action="CHAIN_ORIGIN", resource_type="RunTailDeletionTest"
        )
        first = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        UserRepository(db).log_audit(
            action="ADMIN_AUDIT_INTEGRITY_CHECK",
            resource_type="AuditLog",
            after={"verification_run": first["verification_run"]},
        )
        deleted_id = first["verification_run"]["id"]
        db.execute(
            text("DELETE FROM audit_verification_runs WHERE id=:id"),
            {"id": deleted_id},
        )
        db.commit()

        report = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
        assert report["verification_runs"]["anchor"]["verdict"] == "tail_deletion_detected"
        assert any(
            violation["issue"] == "verification_run_tail_deletion_detected"
            for violation in report["violations"]
        )
        assert report["verification_runs"]["intact"] is False
        assert report["tamper_evident"] is False


class TestRunKeyRotation:
    def test_k1_to_k2_mixed_run_chain_verifies(self, db, monkeypatch):
        old = "verification-run-old-key-material-long-enough-v1"
        new = "verification-run-new-key-material-long-enough-v2"
        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", old)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 1)
        _run(db, request_id="v1")

        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", new)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 2)
        monkeypatch.setenv("AUDIT_HMAC_KEY_V1", old)
        _run(db, request_id="v2")

        rows = _rows(db)
        assert [r.run_hmac_key_version for r in rows] == [1, 2]
        assert verify_verification_runs(rows, expected_prev=RUN_GENESIS_HASH)["intact"]

    def test_missing_retired_k1_fails_explicitly(self, db, monkeypatch):
        old = "verification-run-retired-key-material-long-enough"
        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", old)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 1)
        _run(db, request_id="signed-with-retired-k1")

        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", "active-k2-material-long-enough")
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 2)
        monkeypatch.delenv("AUDIT_HMAC_KEY_V1", raising=False)
        result = verify_verification_runs(_rows(db), expected_prev=RUN_GENESIS_HASH)
        assert not result["intact"]
        assert result["breaks"][0]["issue"] == "verification_run_key_unavailable"

    def test_wrong_retired_k1_fails_hash_verification(self, db, monkeypatch):
        old = "verification-run-correct-retired-key-material"
        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", old)
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 1)
        _run(db, request_id="signed-with-correct-k1")

        monkeypatch.setattr(settings, "AUDIT_HMAC_KEY", "active-k2-material-long-enough")
        monkeypatch.setattr(settings, "AUDIT_CHAIN_KEY_VERSION", 2)
        monkeypatch.setenv("AUDIT_HMAC_KEY_V1", "wrong-retired-k1-material")
        result = verify_verification_runs(_rows(db), expected_prev=RUN_GENESIS_HASH)
        assert not result["intact"]
        assert result["breaks"][0]["issue"] == "verification_run_hash_mismatch"


@pytest.mark.skipif(
    PG_ENGINE.dialect.name != "postgresql",
    reason="transaction advisory-lock concurrency is PostgreSQL-specific",
)
class TestRunConcurrencyPostgres:
    def test_two_concurrent_appends_form_one_linear_run_chain(self):
        import threading
        import uuid

        Session = sessionmaker(bind=PG_ENGINE, autocommit=False, autoflush=False)
        barrier = threading.Barrier(2)
        request_ids = [f"run-concurrent-{uuid.uuid4()}" for _ in range(2)]
        errors = []

        def writer(request_id: str) -> None:
            session = Session()
            try:
                row = AuditVerificationRun(
                    window_days=30, checked_rows=1, sampled_rows=1,
                    chained_rows=1, unchained_rows=0, break_count=0,
                    verdict="ok", tamper_evident=True, head_hash="b" * 64,
                    head_row_id=1, key_version=active_key_version(),
                    canonical_version=1, request_id=request_id,
                )
                session.add(row)
                barrier.wait(timeout=5)
                session.commit()
            except Exception as exc:  # captured in caller thread for assertion
                session.rollback()
                errors.append(exc)
            finally:
                session.close()

        threads = [threading.Thread(target=writer, args=(rid,)) for rid in request_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert not errors, errors
        assert all(not thread.is_alive() for thread in threads)

        session = Session()
        try:
            rows = (
                session.query(AuditVerificationRun)
                .filter(AuditVerificationRun.request_id.in_(request_ids))
                .order_by(AuditVerificationRun.id.asc())
                .all()
            )
            assert len(rows) == 2
            assert rows[1].run_prev_hash == rows[0].run_hash, (
                "concurrent appends forked instead of serialising"
            )
            assert verify_verification_runs(rows)["intact"]
        finally:
            session.close()


def test_offline_verifier_checks_both_chains_and_run_tail_anchor(db):
    from backend.scripts.verify_audit_chain import run as offline_verify

    UserRepository(db).log_audit(
        action="CHAIN_ORIGIN", resource_type="OfflineVerifierTest"
    )
    online = AuditTrailService(db).integrity(window_days=30, sample_limit=10)
    UserRepository(db).log_audit(
        action="ADMIN_AUDIT_INTEGRITY_CHECK",
        resource_type="AuditLog",
        after={"verification_run": online["verification_run"]},
    )
    url = str(db.get_bind().url)
    intact = offline_verify(url)
    assert intact["coverage"]["mode"] == "full_history"
    assert intact["verification_runs"]["coverage"] == "full_history"
    assert intact["verification_runs"]["tail_anchor"]["verdict"] == "anchored"
    assert intact["intact"] is True

    db.execute(
        text("DELETE FROM audit_verification_runs WHERE id=:id"),
        {"id": online["verification_run"]["id"]},
    )
    db.commit()
    broken = offline_verify(url)
    assert broken["verification_runs"]["tail_anchor"]["verdict"] == "tail_deletion_detected"
    assert "verification_run_tail_deletion_detected" in {
        finding["issue"] for finding in broken["breaks"]
    }
    assert broken["intact"] is False


def test_no_production_code_bypasses_verification_run_mapper_listener():
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for needle in (
            "bulk_save_objects", "bulk_insert_mappings",
            "AuditVerificationRun.__table__.insert", "insert(AuditVerificationRun",
        ):
            if needle in source:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, offenders


class TestIntegrityHttpContract:
    def test_coverage_and_verification_run_integrity_survive_response_model(self):
        """Regression: #201 built coverage in the service but Pydantic stripped
        it at HTTP because AuditIntegrityOut omitted the field."""
        client = TestClient(app)
        login = client.post("/api/v1/auth/login", json={
            "email": "admin@confit.io", "password": "Password123!",
        })
        assert login.status_code == 200
        response = client.get(
            "/api/v1/admin/audit/integrity?window_days=30",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["coverage"]["mode"] == "window_sample"
        assert body["coverage"]["full_history"] is False
        assert "bypass_suspected_rows" in body["chain"]
        assert body["verification_runs"]["coverage_mode"] == "tail_window"
        assert body["verification_run"]["run_hash"]
        assert body["verification_run"]["hmac_key_version"] >= 1

        # The controller cross-links the first signed run into the independent
        # audit chain. The next real HTTP call must consume that on-wire event
        # as its run-tail anchor rather than trusting a service-only property.
        second = client.get(
            "/api/v1/admin/audit/integrity?window_days=30",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["verification_runs"]["anchor"]["verdict"] == "anchored"
        assert (
            second_body["verification_runs"]["anchor"]["run_id"]
            == body["verification_run"]["id"]
        )
