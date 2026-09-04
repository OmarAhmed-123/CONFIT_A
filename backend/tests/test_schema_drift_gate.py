"""Schema-drift gate (release brief §22, regression tests T1, T2).

Production truth that motivated this file: Neon production sat at alembic
0007 while the deployed code expected 0013; four endpoints served 500 for
weeks and /health said "healthy". These tests prove the gate now catches that
state — using REAL alembic migrations on a real database, never by mocking
the inspector.

Database under test: SQLite file by default (alembic upgrade head runs the
same scripts); set CONFIT_TEST_PG_URL=postgresql://... to run every test in
this file against a real PostgreSQL (the URL must point at a scratch database
the tests may drop tables in).
"""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.app.core import schema_gate
from backend.app.core.schema_gate import (
    REQUIRED_COLUMNS,
    REQUIRED_TABLES,
    SchemaDriftError,
    enforce_at_startup,
    evaluate,
    expected_head_revision,
    migration_chain,
    revision_ordinal,
)

PG_URL = os.environ.get("CONFIT_TEST_PG_URL")


def _alembic(url: str, direction: str, target: str):
    from alembic import command
    from alembic.config import Config

    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        (command.upgrade if direction == "up" else command.downgrade)(cfg, target)
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


def _drop_everything(engine):
    insp = inspect(engine)
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        else:
            for t in insp.get_table_names():
                conn.execute(text(f'DROP TABLE IF EXISTS "{t}"'))


@pytest.fixture
def scratch_db():
    """A fresh database URL + engine; migrated by the test itself."""
    if PG_URL:
        engine = create_engine(PG_URL)
        _drop_everything(engine)
        yield PG_URL, engine
        _drop_everything(engine)
        engine.dispose()
    else:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        url = f"sqlite:///{path}"
        engine = create_engine(url)
        yield url, engine
        engine.dispose()
        os.unlink(path)


class TestChainAndHead:
    def test_chain_is_linear_with_single_head(self):
        chain = migration_chain()
        assert len(chain) >= 13
        downs = {d for d in chain.values() if d}
        heads = [r for r in chain if r not in downs]
        assert heads == [expected_head_revision()]

    def test_expected_head_is_latest_script(self):
        assert expected_head_revision().startswith("00")
        assert revision_ordinal(expected_head_revision()) == len(migration_chain()) - 1

    def test_required_objects_exist_in_orm_metadata(self):
        """The gate list must never drift from the models it protects."""
        import backend.app.models  # noqa: F401
        from backend.app.core.database import Base

        for t in REQUIRED_TABLES:
            if t in schema_gate.MIGRATION_ONLY_TABLES:
                continue  # created by migration 0013 only (no ORM model)
            assert t in Base.metadata.tables, t
        for t, cols in REQUIRED_COLUMNS.items():
            for c in cols:
                assert c in Base.metadata.tables[t].columns, f"{t}.{c}"


class TestGateAgainstRealMigrations:
    def test_head_database_passes(self, scratch_db):
        url, engine = scratch_db
        _alembic(url, "up", "head")
        report = evaluate(engine)
        assert report.ok, report.findings
        assert report.database_revision == expected_head_revision()
        assert report.missing_tables == [] and report.missing_columns == {}

    def test_T1_database_at_0007_is_flagged_as_behind(self, scratch_db):
        """The exact production state: DB 0007, code head 0013+."""
        url, engine = scratch_db
        _alembic(url, "up", "0007_reconcile_recently_viewed")
        report = evaluate(engine)
        assert report.verdict == "drift"
        assert report.database_revision == "0007_reconcile_recently_viewed"
        assert any("BEHIND" in f for f in report.findings), report.findings
        # the concrete objects whose absence produced the production 500s
        for t in ("brand_analytics_events", "order_events", "migration_audit_log"):
            assert t in report.missing_tables, report.missing_tables
        assert any("alembic upgrade head" in f for f in report.findings)

    def test_T1_production_startup_refuses_a_0007_database(self, scratch_db):
        url, engine = scratch_db
        _alembic(url, "up", "0007_reconcile_recently_viewed")
        with pytest.raises(SchemaDriftError) as exc:
            enforce_at_startup(engine, "production")
        assert "0007" in str(exc.value)

    def test_non_production_logs_but_does_not_raise(self, scratch_db):
        url, engine = scratch_db
        _alembic(url, "up", "0007_reconcile_recently_viewed")
        report = enforce_at_startup(engine, "development")
        assert report.verdict == "drift"

    def test_T2_required_table_missing_is_detected_even_at_head_revision(self, scratch_db):
        """alembic_version says head but a required table is gone: still drift."""
        url, engine = scratch_db
        _alembic(url, "up", "head")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE migration_audit_log"))
        report = evaluate(engine)
        assert report.verdict == "drift"
        assert report.database_revision == expected_head_revision()
        assert report.missing_tables == ["migration_audit_log"]
        with pytest.raises(SchemaDriftError):
            enforce_at_startup(engine, "production")

    def test_T2_required_column_missing_is_detected(self, scratch_db):
        url, engine = scratch_db
        _alembic(url, "up", "head")
        if engine.dialect.name != "postgresql":
            pytest.skip("column drop exercised on PostgreSQL (CONFIT_TEST_PG_URL)")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE orders DROP COLUMN payment_mode"))
        report = evaluate(engine)
        assert report.verdict == "drift"
        assert report.missing_columns == {"orders": ["payment_mode"]}

    def test_never_migrated_empty_database_is_drift(self, scratch_db):
        url, engine = scratch_db
        report = evaluate(engine)
        assert report.verdict == "drift"
        assert report.database_revision is None
        assert any("never migrated" in f for f in report.findings)
        with pytest.raises(SchemaDriftError):
            enforce_at_startup(engine, "production")

    def test_create_all_database_is_unmanaged_and_rejected_in_production(self, scratch_db):
        """A complete create_all schema (dev/test) is fine outside production,
        but production must be Alembic-managed — no exceptions."""
        import backend.app.models  # noqa: F401
        from backend.app.core.database import Base

        url, engine = scratch_db
        Base.metadata.create_all(bind=engine)
        report = evaluate(engine)
        assert report.verdict == "unmanaged", report.findings
        assert report.missing_columns == {}
        assert set(report.missing_tables) <= {"migration_audit_log"}
        assert schema_gate.acceptable(report, "development") is True
        assert schema_gate.acceptable(report, "production") is False
        with pytest.raises(SchemaDriftError):
            enforce_at_startup(engine, "production")
        enforce_at_startup(engine, "test")  # no raise

    def test_unknown_future_revision_is_drift(self, scratch_db):
        url, engine = scratch_db
        _alembic(url, "up", "head")
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = '9999_from_the_future'"))
        report = evaluate(engine)
        assert report.verdict == "drift"
        assert any("unknown to this code" in f for f in report.findings)

    def test_emergency_override_is_explicit_and_logged(self, scratch_db, monkeypatch):
        url, engine = scratch_db
        _alembic(url, "up", "0007_reconcile_recently_viewed")
        monkeypatch.setenv("CONFIT_SCHEMA_GATE", "warn")
        report = enforce_at_startup(engine, "production")
        assert report.verdict == "drift"  # still reported, only enforcement relaxed


class TestGateIsWired:
    def test_startup_calls_enforce_in_lifespan(self):
        src = open("backend/app/main.py").read()
        assert "enforce_at_startup(engine, settings.ENVIRONMENT" in src

    def test_health_exposes_schema_verdict(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert "schema" in body["checks"]
        assert {"verdict", "expected_head", "database_revision", "findings", "acceptable"} <= set(body["checks"]["schema"])
        assert body["checks"]["schema"]["expected_head"] == expected_head_revision()
        # the test DB is a create_all database: honest verdict, acceptable outside production
        assert body["checks"]["schema"]["verdict"] in ("ok", "unmanaged")
        assert body["checks"]["schema"]["acceptable"] is True
        assert body["status"] == "healthy"

    def test_health_status_is_not_healthy_when_schema_drifts(self, client, monkeypatch):
        drift = schema_gate.SchemaGateReport(
            verdict="drift", expected_head="x", database_revision="0007", findings=["database is BEHIND the code"])
        schema_gate.reset_cache()
        monkeypatch.setattr(schema_gate, "evaluate", lambda _engine, **kw: drift)
        try:
            r = client.get("/api/v1/health")
            assert r.json()["status"] == "degraded"
            assert r.json()["checks"]["schema"]["verdict"] == "drift"
        finally:
            schema_gate.reset_cache()

    def test_request_guard_refuses_api_in_production_on_drift(self, client, monkeypatch):
        """Serverless-safe guard: explicit 503 SCHEMA_DRIFT, never an opaque 500."""
        from backend.app.core.config import settings

        drift = schema_gate.SchemaGateReport(
            verdict="drift", expected_head="0013_x", database_revision="0007_reconcile_recently_viewed",
            findings=["database is BEHIND the code", "required table missing: brand_analytics_events"])
        schema_gate.reset_cache()
        monkeypatch.setattr(schema_gate, "evaluate", lambda _engine, **kw: drift)
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.delenv("CONFIT_SCHEMA_GATE", raising=False)
        try:
            r = client.get("/api/v1/catalog/products")
            assert r.status_code == 503, r.text
            body = r.json()["error"]
            assert body["code"] == "SCHEMA_DRIFT"
            assert body["details"]["database_revision"] == "0007_reconcile_recently_viewed"
            assert body["details"]["expected_head"] == "0013_x"
            # health stays reachable and reports the drift
            h = client.get("/api/v1/health")
            assert h.status_code == 200 and h.json()["status"] == "degraded"
        finally:
            schema_gate.reset_cache()

    def test_request_guard_is_inactive_outside_production(self, client, monkeypatch):
        drift = schema_gate.SchemaGateReport(verdict="drift", expected_head="x", database_revision=None, findings=["never migrated"])
        schema_gate.reset_cache()
        monkeypatch.setattr(schema_gate, "evaluate", lambda _engine, **kw: drift)
        try:
            r = client.get("/api/v1/catalog/products")
            assert r.status_code != 503
        finally:
            schema_gate.reset_cache()

    def test_request_guard_passes_when_schema_ok(self, client, monkeypatch):
        from backend.app.core.config import settings

        ok = schema_gate.SchemaGateReport(verdict="ok", expected_head="h", database_revision="h", findings=[])
        schema_gate.reset_cache()
        monkeypatch.setattr(schema_gate, "evaluate", lambda _engine, **kw: ok)
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        try:
            r = client.get("/api/v1/catalog/products")
            assert r.status_code == 200, r.text
        finally:
            schema_gate.reset_cache()

    def test_health_vton_status_is_honest_about_missing_token(self, client, monkeypatch):
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://example.invalid--worker.modal.run")
        monkeypatch.setattr(settings, "VTON_WORKER_ADMIN_TOKEN", None)
        monkeypatch.setattr(settings, "CONFIT_WORKER_ADMIN_TOKEN", None)
        monkeypatch.delenv("VTON_WORKER_ADMIN_TOKEN", raising=False)
        monkeypatch.delenv("CONFIT_WORKER_ADMIN_TOKEN", raising=False)
        r = client.get("/api/v1/health")
        assert r.json()["checks"]["vton_pipeline"].startswith("misconfigured")
        assert "operational" not in r.json()["checks"]["vton_pipeline"]

    def test_health_never_claims_vton_operational(self, client):
        r = client.get("/api/v1/health")
        assert r.json()["checks"]["vton_pipeline"] != "operational"
