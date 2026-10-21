"""The HTTP contract of a background import: accept fast, or refuse honestly.

The endpoint used to declare ``202`` and then do the work inline. These tests
drive the real route (real router, real auth dependency, real DB) and assert the
two things a 202 promises:

  * it returns before the catalogue is imported, and
  * it only says "accepted" when a worker was actually handed the job.

They also pin the failure direction that matters most: when the queue is down the
response is a 503 and the job row says failed — never a cheerful "queued" for
work nothing will ever run.
"""
from __future__ import annotations

import csv
import io

import pytest

from backend.app.core.config import settings
from backend.app.models.catalog import Product
from backend.app.models.catalog_import import CatalogImportJob
from backend.app.services.brand_catalog_service import BrandCatalogService

APPROVED_IMAGE = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"


def _csv_text(titles):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["product_name", "sku", "description", "category", "price",
                     "currency", "color", "size", "stock_quantity", "image_url",
                     "gender", "title_ar"])
    for i, title in enumerate(titles, start=1):
        writer.writerow([title, f"ASYNC-{i:03d}", "A shirt", "tops", "25.00",
                         settings.PRICING_CURRENCY, "Navy", "M", "4",
                         APPROVED_IMAGE, "unisex", "قميص"])
    return buf.getvalue()


def _auth(headers):
    """Only the Authorization header may reach the transport; the fixture also
    carries the brand id for assertions, and an int is not a header value."""
    return {"Authorization": headers["Authorization"]}


def _upload(client, headers, text):
    return client.post(
        "/api/v1/partner/catalog/confirm-import",
        files={"file": ("catalog.csv", text.encode("utf-8"), "text/csv")},
        headers=_auth(headers),
    )


PASSWORD = "Password123!"


@pytest.fixture()
def brand_headers(client):
    """A real brand-owner session for a seeded brand that owns products."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.user import BrandProfile, User

    db = TestingSessionLocal()
    try:
        row = (
            db.query(BrandProfile, User)
            .join(User, User.id == BrandProfile.user_id)
            .filter(BrandProfile.id.in_(db.query(Product.brand_id)))
            .first()
        )
        if not row:
            pytest.skip("no brand with products seeded")
        ctx = {"email": row[1].email, "brand_id": row[0].id}
    finally:
        db.close()

    response = client.post("/api/v1/auth/login",
                           json={"email": ctx["email"], "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {response.json()['access_token']}",
            "brand_id": ctx["brand_id"]}


def test_the_endpoint_accepts_rather_than_imports(client, brand_headers, monkeypatch):
    dispatched = []

    from backend.app.workers import tasks as worker_tasks

    def _capture(job_id):
        dispatched.append(job_id)
        return type("R", (), {"id": "task-" + str(job_id)})()

    monkeypatch.setattr(worker_tasks.bulk_catalog_import_task, "delay", _capture)

    response = _upload(client, brand_headers, _csv_text(["Async Coat", "Async Shirt"]))

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["accepted_rows"] == 0 and body["total_rows"] == 0, (
        "a 202 must not carry results — the import has not run yet"
    )
    assert body["status_url"].endswith(f"/imports/{body['job_id']}")
    assert dispatched == [body["job_id"]], "the job was never handed to the worker"

    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        job = db.query(CatalogImportJob).filter_by(id=body["job_id"]).one()
        assert job.status == "queued"
        assert job.payload_text and "Async Coat" in job.payload_text
        assert db.query(Product).filter_by(title="Async Coat").count() == 0, (
            "the request imported the catalogue synchronously"
        )
    finally:
        db.close()


def test_a_dead_queue_answers_503_and_leaves_a_failed_job(client, brand_headers, monkeypatch):
    from backend.app.workers import tasks as worker_tasks

    def _boom(job_id):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(worker_tasks.bulk_catalog_import_task, "delay", _boom)

    response = _upload(client, brand_headers, _csv_text(["Queue Down Coat"]))

    assert response.status_code == 503, (
        "reporting 202 for a job nothing will run is the defect this replaces"
    )
    assert "queue is unavailable" in response.json()["detail"]

    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        job = (db.query(CatalogImportJob)
                 .order_by(CatalogImportJob.id.desc()).first())
        assert job.status == "failed"
        assert job.last_error and "dispatch_failed" in job.last_error
        assert job.payload_text, "the file must survive so the import can be retried"
        assert db.query(Product).filter_by(title="Queue Down Coat").count() == 0
    finally:
        db.close()


def test_retry_refuses_a_finished_job(client, brand_headers):
    """Retrying a completed import would import it twice."""
    from backend.tests.conftest import TestingSessionLocal

    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        job = BrandCatalogService(db).enqueue_csv_import(
            _csv_text(["Done Coat"]), brand_headers["brand_id"], "done.csv")
        job.status, job.accepted_rows, job.payload_text = "completed", 1, None
        db.commit()
        job_id = job.id
    finally:
        db.close()

    response = client.post(f"/api/v1/partner/catalog/imports/{job_id}/retry",
                           headers=_auth(brand_headers))
    assert response.status_code == 409, response.text
    assert "only a failed import can be retried" in response.json()["detail"]


def test_another_brand_cannot_retry_your_job(client, brand_headers):
    """Job access is brand-scoped, and a retry is job access."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.user import BrandProfile, User

    db = TestingSessionLocal()
    try:
        job = BrandCatalogService(db).enqueue_csv_import(
            _csv_text(["Private Coat"]), brand_headers["brand_id"], "mine.csv")
        job.status, job.last_error = "failed", "boom"
        db.commit()
        job_id = job.id
        other = (
            db.query(BrandProfile, User)
            .join(User, User.id == BrandProfile.user_id)
            .filter(BrandProfile.id != brand_headers["brand_id"])
            .first()
        )
        if not other:
            pytest.skip("only one brand is seeded")
        other_email = other[1].email
    finally:
        db.close()

    login = client.post("/api/v1/auth/login",
                        json={"email": other_email, "password": PASSWORD})
    if login.status_code != 200:
        pytest.skip("the second brand's seeded account cannot authenticate")
    intruder = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(f"/api/v1/partner/catalog/imports/{job_id}/retry",
                           headers=intruder)
    assert response.status_code == 404, (
        "one brand reached another brand's import job"
    )
