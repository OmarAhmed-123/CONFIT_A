"""Tests for cloud Modal catalog-worker dispatch, failover, retries, and health."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.models.catalog_import import CatalogImportJob
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.workers import tasks as worker_tasks


def test_serverless_modal_dispatch_when_no_external_redis(monkeypatch):
    captured = {}

    def _fake_post(url, *, json=None, headers=None, timeout=None, follow_redirects=False):
        captured["url"] = url
        captured["json"] = json
        captured["token"] = headers.get("X-Catalog-Worker-Token")
        return httpx.Response(202, json={"accepted": True, "job_id": json["job_id"], "call_id": "fc-test-99"})

    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "CATALOG_WORKER_DISPATCH_URL", "https://example.modal.run/dispatch")
    monkeypatch.setattr(settings, "CATALOG_WORKER_ADMIN_TOKEN", "worker-test-token-placeholder")
    monkeypatch.setattr(httpx, "post", _fake_post)

    res = worker_tasks.dispatch_catalog_import_job(42)
    assert res.id == "fc-test-99"
    assert captured == {
        "url": "https://example.modal.run/dispatch",
        "json": {"job_id": 42},
        "token": "worker-test-token-placeholder",
    }


def test_external_redis_fails_over_cleanly_to_modal_dispatch(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "rediss://broker.example.invalid:6379/0")
    monkeypatch.setattr(settings, "CATALOG_WORKER_DISPATCH_URL", "https://example.modal.run/dispatch")
    monkeypatch.setattr(settings, "CATALOG_WORKER_ADMIN_TOKEN", "worker-test-token-placeholder")

    def _redis_down(_job_id):
        raise ConnectionError("broker connection refused")

    def _modal_ok(url, *, json=None, headers=None, timeout=None, follow_redirects=False):
        return httpx.Response(202, json={"accepted": True, "job_id": json["job_id"], "call_id": "fc-failover-7"})

    monkeypatch.setattr(worker_tasks, "_publish_via_celery", _redis_down)
    monkeypatch.setattr(httpx, "post", _modal_ok)
    res = worker_tasks.dispatch_catalog_import_job(7)
    assert res.id == "fc-failover-7"


def test_execute_catalog_import_with_retries_recovers_and_marks_exhausted(client, tmp_path, monkeypatch):
    from PIL import Image
    import io as _io
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.user import BrandProfile
    from backend.app.services import media_materialization_service as mms, storage_service

    buf = _io.BytesIO()
    Image.new("RGB", (600, 800), color=(40, 60, 80)).save(buf, format="JPEG")
    jpg_bytes = buf.getvalue()
    monkeypatch.setattr(settings, "STORAGE_LOCAL_DIR", str(tmp_path / "uploads"), raising=False)
    storage_service.reset_storage()
    monkeypatch.setattr(
        mms,
        "_default_fetch",
        lambda url, **_kw: jpg_bytes,
        raising=False,
    )
    monkeypatch.setattr(worker_tasks, "SessionLocal", TestingSessionLocal)

    db = TestingSessionLocal()
    try:
        bp = db.query(BrandProfile).first()
        csv_body = (
            "product_name,sku,description,category,price,currency,color,size,stock_quantity,image_url,gender,title_ar\n"
            f"Test Cotton Shirt,RETRY-001,Crisp shirt,tops,30.00,{settings.PRICING_CURRENCY},Black,M,5,https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg,unisex,قميص\n"
        )
        job = BrandCatalogService(db).enqueue_csv_import(csv_body, bp.id, "retry.csv")
        job_id = job.id
    finally:
        db.close()

    calls = {"n": 0}
    orig_exec = BrandCatalogService.execute_import_job

    def _flaky_once(self, jid):
        calls["n"] += 1
        if calls["n"] == 1:
            row = self.db.query(CatalogImportJob).filter_by(id=jid).one()
            row.status = "processing"
            row.attempts = 1
            row.heartbeat_at = datetime.now(timezone.utc)
            self.db.commit()
            raise RuntimeError("transient S3 socket timeout")
        return orig_exec(self, jid)

    monkeypatch.setattr(BrandCatalogService, "execute_import_job", _flaky_once)
    out = worker_tasks.execute_catalog_import_with_retries(job_id, max_attempts=3, retry_sleep_fn=lambda _s: None)
    assert out["status"] == "completed"
    assert calls["n"] == 2

    # Now verify exhaustion marks terminal status='failed' with heartbeat cleared
    db = TestingSessionLocal()
    try:
        bp = db.query(BrandProfile).first()
        job2 = BrandCatalogService(db).enqueue_csv_import(csv_body, bp.id, "exhaust.csv")
        job2_id = job2.id
    finally:
        db.close()

    def _always_boom(self, jid):
        row = self.db.query(CatalogImportJob).filter_by(id=jid).one()
        row.status = "processing"
        row.attempts = (row.attempts or 0) + 1
        row.heartbeat_at = datetime.now(timezone.utc)
        self.db.commit()
        raise RuntimeError("persistent upstream failure")

    monkeypatch.setattr(BrandCatalogService, "execute_import_job", _always_boom)
    out2 = worker_tasks.execute_catalog_import_with_retries(job2_id, max_attempts=3, retry_sleep_fn=lambda _s: None)
    assert out2["status"] == "failed"
    assert out2["retries_exhausted"] is True

    db = TestingSessionLocal()
    try:
        final_job = db.query(CatalogImportJob).filter_by(id=job2_id).one()
        assert final_job.status == "failed"
        assert final_job.attempts == 3
        assert final_job.heartbeat_at is None
        assert "persistent upstream failure" in (final_job.last_error or "")
    finally:
        db.close()
