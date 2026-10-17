"""GDPR Art. 17 retention lifecycle on tryon_jobs rows (port of PR #119).

tryon_jobs stores the uploaded person photo (data URL) on the row. The
2026-09-19 gap audit found the purge daemon could only reach session rows;
this suite pins the closed loop: job rows carry the retention clock, the
read-time purge helper honours it, and the migration chain reaches 0038.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


def _row(**kw):
    base = dict(input_person_image_url="data:image/png;base64,AAAA",
                rendered_result_url=None, consent_retained=False)
    base.update(kw)
    return SimpleNamespace(**base)


class TestPurgeHelper:
    def test_expired_unconsented_row_is_purged(self):
        from backend.app.services.tryon_service import _purge_vton_row_if_expired
        row = _row(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        assert _purge_vton_row_if_expired(row) is True
        assert row.input_person_image_url == "[PURGED_FOR_PRIVACY]"

    def test_unexpired_row_untouched(self):
        from backend.app.services.tryon_service import _purge_vton_row_if_expired
        row = _row(expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        assert _purge_vton_row_if_expired(row) is False
        assert row.input_person_image_url.startswith("data:image/")

    def test_consent_retained_row_never_purged(self):
        from backend.app.services.tryon_service import _purge_vton_row_if_expired
        row = _row(consent_retained=True,
                   expires_at=datetime.now(timezone.utc) - timedelta(days=3))
        assert _purge_vton_row_if_expired(row) is False
        assert row.input_person_image_url.startswith("data:image/")

    def test_missing_expiry_is_not_purged(self):
        from backend.app.services.tryon_service import _purge_vton_row_if_expired
        row = _row(expires_at=None)
        assert _purge_vton_row_if_expired(row) is False

    def test_naive_datetime_treated_as_utc(self):
        from backend.app.services.tryon_service import _purge_vton_row_if_expired
        naive = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
        row = _row(expires_at=naive)
        assert _purge_vton_row_if_expired(row) is True


class TestModelAndChain:
    def test_job_model_carries_retention_columns(self):
        from backend.app.models.tryon import TryOnJob
        cols = {c.name for c in TryOnJob.__table__.columns}
        assert {"expires_at", "consent_retained"} <= cols

    def test_migration_chain_head_is_job_retention(self):
        from backend.app.core.schema_gate import expected_head_revision, migration_chain
        chain = migration_chain()
        downs = {d for d in chain.values() if d}
        heads = [r for r in chain if r not in downs]
        assert heads == ["0038_vton_job_retention"] == [expected_head_revision()]
        assert chain["0038_vton_job_retention"] == "0037_recently_viewed_unique"


class TestPurgeTaskCoversJobs:
    def test_task_queries_tryon_jobs(self):
        # Source-text contract (celery is not importable in every test env;
        # CI installs it, this gate is about the code shipped in the file).
        from pathlib import Path
        src = Path(__file__).resolve().parents[1].joinpath(
            "app/workers/tasks.py").read_text(encoding="utf-8")
        task_src = src.split("def purge_expired_sessions_task", 1)[1].split("@celery_app.task", 1)[0]
        assert "TryOnJob" in task_src
        assert 'j.input_person_image_url = "[PURGED_FOR_PRIVACY]"' in task_src
        assert "purged_job_count" in task_src
        assert "from backend.app.models.tryon import TryOnSession, TryOnJob" in src
