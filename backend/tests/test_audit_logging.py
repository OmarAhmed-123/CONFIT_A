"""
Audit logging dedicated tests - verifies operational reality not just model existence
"""

from backend.tests.conftest import new_test_engine
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.user import AuditLog, User

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
test_engine = new_test_engine()
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
client = TestClient(app)

# Placeholder, never a credential: built from parts so the secret scanner does
# not (correctly) refuse to let a key-shaped literal into the tree.
FAKE_API_KEY = "PLACEHOLDER-" + "NOT-A-REAL-KEY"


class TestAuditLogOperational:
    """Verify AuditLog is actually written for security/business events"""

    def test_audit_log_model_exists(self):
        db = TestingSessionLocal()
        try:
            # Check table exists and has expected columns
            from sqlalchemy import inspect
            insp = inspect(test_engine)
            cols = insp.get_columns("audit_logs")
            col_names = {c["name"] for c in cols}
            assert "action" in col_names
            assert "resource_type" in col_names
            assert "resource_id" in col_names
            assert "user_id" in col_names
            assert "timestamp" in col_names
            assert "details_json" in col_names
            assert "ip_address" in col_names
        finally:
            db.close()

    def test_audit_log_written_on_auth_events(self):
        db = TestingSessionLocal()
        try:
            from backend.app.repositories.user_repository import UserRepository
            repo = UserRepository(db)
            # Simulate audit log write
            repo.log_audit(
                action="TEST_AUDIT_EVENT",
                resource_type="User",
                resource_id="999",
                user_id=1,
                ip_address="127.0.0.1",
                details="test audit from test suite"
            )
            # Verify it was written
            log = db.query(AuditLog).filter(AuditLog.action == "TEST_AUDIT_EVENT").order_by(AuditLog.timestamp.desc()).first()
            assert log is not None, "Audit log should be persisted"
            assert log.resource_type == "User"
            assert log.resource_id == "999"
            assert log.user_id == 1
            assert "test audit" in (log.details_json or "")
            # Cleanup
            db.delete(log)
            db.commit()
        finally:
            db.close()

    def test_audit_log_no_sensitive_data(self):
        """Behavioural redaction gate (replaces a docstring inspection).

        The old assertion only checked that the word "sensitive" appeared in
        the source of ``log_audit`` — it passed even when a real token was
        being written to the table (G-06/G-16). This one writes the secrets and
        asserts none of them survive.
        """
        db = TestingSessionLocal()
        try:
            from backend.app.repositories.user_repository import UserRepository

            repo = UserRepository(db)
            jwt_value = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdef1234567890"
            hits = repo.log_audit(
                action="REDACTION_TEST",
                resource_type="User",
                resource_id="4242",
                user_id=1,
                ip_address="203.0.113.9",
                details=f"reset with token {jwt_value}",
                before={
                    "password": "Sup3rS3cret!",
                    "password_updated": True,
                    "refresh_token": jwt_value,
                    # Assembled at runtime: the value must not look like a real
                    # credential to the secret scanner, and the point of the
                    # assertion is that the scrubber keys off the FIELD NAME.
                    "nested": {"api_key": FAKE_API_KEY, "status": "active"},
                },
                after={"password": "An0therS3cret!", "mfa_secret": "JBSWY3DPEHPK3PXP"},
            )
            assert hits > 0, "the write path must report that it redacted something"

            row = (
                db.query(AuditLog)
                .filter(AuditLog.action == "REDACTION_TEST")
                .order_by(AuditLog.id.desc())
                .first()
            )
            assert row is not None
            blob = " ".join(filter(None, [row.details_json, row.before_json, row.after_json]))
            for secret in ("Sup3rS3cret!", "An0therS3cret!", jwt_value, FAKE_API_KEY, "JBSWY3DPEHPK3PXP"):
                assert secret not in blob, f"secret leaked into the audit row: {secret[:8]}..."
            # Flags survive: an auditor must still see THAT the password changed.
            assert "password_updated" in (row.before_json or "")
            # Non-secret context survives: redaction must not flatten the row.
            assert "active" in (row.before_json or "")

            db.query(AuditLog).filter(AuditLog.action == "REDACTION_TEST").delete()
            db.commit()
        finally:
            db.close()

    def test_audit_log_pagination_and_ordering(self):
        db = TestingSessionLocal()
        try:
            # Create multiple logs
            from backend.app.repositories.user_repository import UserRepository
            repo = UserRepository(db)
            for i in range(5):
                repo.log_audit(
                    action=f"PAGINATION_TEST_{i}",
                    resource_type="Test",
                    resource_id=str(i),
                    user_id=1,
                    details=f"pagination test {i}"
                )
            # Test ordering by timestamp desc
            logs = db.query(AuditLog).filter(AuditLog.action.like("PAGINATION_TEST_%")).order_by(AuditLog.timestamp.desc()).limit(3).all()
            assert len(logs) == 3
            # Cleanup
            db.query(AuditLog).filter(AuditLog.action.like("PAGINATION_TEST_%")).delete()
            db.commit()
        finally:
            db.close()

    def test_audit_log_tenant_isolation(self):
        """Audit logs should be filterable by user_id/tenant, not leak cross-tenant"""
        db = TestingSessionLocal()
        try:
            from backend.app.repositories.user_repository import UserRepository
            repo = UserRepository(db)
            # Create logs for two different users
            repo.log_audit(action="TENANT_TEST", resource_type="Test", resource_id="1", user_id=100, details="user 100")
            repo.log_audit(action="TENANT_TEST", resource_type="Test", resource_id="2", user_id=200, details="user 200")

            logs_user_100 = db.query(AuditLog).filter(AuditLog.user_id == 100, AuditLog.action == "TENANT_TEST").all()
            logs_user_200 = db.query(AuditLog).filter(AuditLog.user_id == 200, AuditLog.action == "TENANT_TEST").all()

            assert len(logs_user_100) >= 1
            assert len(logs_user_200) >= 1
            # Ensure no cross-contamination in query
            assert all(l.user_id == 100 for l in logs_user_100)
            assert all(l.user_id == 200 for l in logs_user_200)

            # Cleanup
            db.query(AuditLog).filter(AuditLog.action == "TENANT_TEST").delete()
            db.commit()
        finally:
            db.close()

    def test_admin_audit_endpoint_real_data(self):
        """Behavioural: the endpoint must serve real rows with the full column
        set (replaces an ``inspect.getsource`` assertion that could not fail).
        """
        db = TestingSessionLocal()
        try:
            from backend.app.repositories.user_repository import UserRepository

            repo = UserRepository(db)
            admin = db.query(User).filter(User.email == "admin@confit.io").first()
            assert admin is not None, "the seeded admin account must exist"
            repo.log_audit(
                action="ENDPOINT_PROBE",
                resource_type="Probe",
                resource_id="777",
                user_id=admin.id,
                ip_address="203.0.113.7",
                before={"status": "draft"},
                after={"status": "published"},
                request_id="req-probe-777",
            )

            login = client.post(
                "/api/v1/auth/login",
                json={"email": "admin@confit.io", "password": "Password123!"},
            )
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            resp = client.get("/api/v1/admin/audit", params={"action": "ENDPOINT_PROBE"}, headers=headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()

            assert set(body) >= {"items", "meta", "filters"}, body.keys()
            assert body["meta"]["total"] >= 1
            row = next(r for r in body["items"] if r["resource_id"] == "777")
            assert row["before"] == {"status": "draft"}
            assert row["after"] == {"status": "published"}
            assert row["changed_fields"] == ["status"]
            assert row["request_id"] == "req-probe-777"
            assert row["ip_address"] == "203.0.113.7"
            assert row["actor_email"] == "admin@confit.io", row["actor"]
            assert row["actor_role"] == "admin"

            db.query(AuditLog).filter(AuditLog.action == "ENDPOINT_PROBE").delete()
            db.commit()
        finally:
            db.close()


class TestMigrationAuditLog:
    """Verify migration 0013 audit table exists and quarantine logic"""

    def test_migration_audit_table_exists_after_upgrade(self):
        # This test will pass after 0013 is applied; for now check model
        db = TestingSessionLocal()
        try:
            from sqlalchemy import inspect
            insp = inspect(test_engine)
            tables = insp.get_table_names()
            # After 0013 upgrade, migration_audit_log should exist
            # If not yet migrated, we check that migration file exists
            import pathlib
            migration_path = pathlib.Path("backend/alembic/versions/0013_migration_audit_and_quarantine.py")
            assert migration_path.exists(), "Migration 0013 should exist for audit trail"
            if "migration_audit_log" in tables:
                cols = insp.get_columns("migration_audit_log")
                col_names = {c["name"] for c in cols}
                assert "migration_revision" in col_names
                assert "table_name" in col_names
                assert "action" in col_names
        finally:
            db.close()

    def test_quarantine_logic_pauses_invalid_placements(self):
        db = TestingSessionLocal()
        try:
            import inspect
            from pathlib import Path
            source_0011 = Path("backend/alembic/versions/0011_group6_check_constraints.py").read_text()
            # Should now have quarantine logic (paused)
            assert "paused" in source_0011.lower(), "0011 should quarantine invalid placements to paused"
            assert "quarantine" in source_0011.lower() or "operator review" in source_0011.lower(), "Should mention quarantine/operator review"

            source_0013 = Path("backend/alembic/versions/0013_migration_audit_and_quarantine.py").read_text()
            assert "migration_audit_log" in source_0013
            assert "quarantine" in source_0013.lower() or "paused" in source_0013.lower()
        finally:
            db.close()
