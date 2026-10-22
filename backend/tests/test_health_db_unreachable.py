"""Regression suite for DEF-28: /api/v1/health must never return HTTP 500 when
PostgreSQL is unreachable (e.g. SQLSTATE 53000 quota exhaustion on Neon), while
check_release_schema_parity MUST still fail closed (exit code 2 / INDETERMINATE).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

from backend.app.core.database import get_db
from backend.app.core.schema_gate import SchemaGateReport
from backend.app.main import app
from backend.app.services.capability_service import capability_probes
from backend.scripts.check_release_schema_parity import evaluate as evaluate_release_parity


def _make_quota_exceeded_session() -> MagicMock:
    quota_err = ProgrammingError(
        "SELECT 1",
        {},
        Exception(
            "{'S': 'ERROR', 'C': '53000', "
            "'M': 'Your account or project has exceeded the quota. Upgrade your plan to increase limits.'}"
        ),
    )
    broken_db = MagicMock()
    broken_db.execute.side_effect = quota_err
    broken_db.query.side_effect = quota_err
    return broken_db


def test_capability_probes_skips_store_count_query_when_database_down():
    broken_db = _make_quota_exceeded_session()
    caps = capability_probes(broken_db, database_ok=False)
    by_name = {c.name: c for c in caps}

    broken_db.query.assert_not_called()
    assert by_name["database"].state == "blocked"
    assert by_name["click_and_collect"].state == "blocked"
    assert "unreachable" in by_name["click_and_collect"].detail


def test_capability_probes_catches_mid_request_store_query_failure():
    broken_db = _make_quota_exceeded_session()
    caps = capability_probes(broken_db, database_ok=True)
    by_name = {c.name: c for c in caps}

    assert by_name["database"].state == "ready"
    assert by_name["click_and_collect"].state == "blocked"


def test_health_check_returns_structured_unhealthy_when_postgres_quota_exceeded():
    broken_db = _make_quota_exceeded_session()
    unreachable_report = SchemaGateReport(
        verdict="unreachable",
        expected_head="0046_user_wishlist_items",
        database_revision=None,
        findings=[
            "database inspection failed: ProgrammingError: SQLSTATE 53000 quota exceeded"
        ],
        dialect="postgresql",
    )

    prev_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: broken_db
    try:
        with patch(
            "backend.app.controllers.telemetry_controller.schema_gate.cached_report",
            return_value=unreachable_report,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/health")
    finally:
        if prev_override is not None:
            app.dependency_overrides[get_db] = prev_override
        else:
            app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "unhealthy"
    assert payload["ready"] is False
    assert "database" in payload["blocking_capabilities"]
    assert payload["checks"]["database"] == "unhealthy"
    assert payload["checks"]["schema"]["verdict"] == "unreachable"
    assert payload["checks"]["schema"]["database_revision"] is None

    # Release gate contract: unreachable database_revision=None MUST still fail closed (code 2).
    code, detail = evaluate_release_parity("0046_user_wishlist_items", payload["checks"]["schema"])
    assert code == 2, detail
