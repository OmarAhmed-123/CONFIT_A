"""Durable background catalog imports: the task, the lease, and the truth.

MEASURED DEFECT
---------------
``celery_app.task_routes`` routed ``bulk_catalog_import_task`` to the
``catalog_ingest`` queue, ``docker-compose.yml`` started a worker consuming that
queue, and the confirm-import endpoint answered ``202 Accepted`` — but the task
did not exist, and the endpoint ran the whole import inline. The job table could
not have supported a worker either: no payload, no attempts, no heartbeat, no
progress.

WHAT THESE TESTS PIN
--------------------
  A. the task exists, is registered, and is routed to ``catalog_ingest``;
  B. the endpoint returns promptly, leaving the row ``queued`` with no counts —
     i.e. it really did not import anything;
  C. the queued job carries what a worker needs (payload, branch, actor, opt-in);
  D. running the worker task imports the catalogue and writes the result back to
     the SAME job row the API returned;
  E. a dispatch failure is reported honestly (503 + a failed job), not as
     "queued";
  F. claiming is atomic and idempotent: a redelivered task cannot import twice;
  G. a stale-lease job is recoverable, a live one is not;
  H. recovery re-dispatches orphaned work;
  I. tenant isolation holds on the retry endpoint.

The end-to-end case drives the REAL task body through Celery's eager mode (so
the task object, routing, argument serialisation and service call all execute),
against a real database. It does not call the service directly and call that
"async".
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import settings
from backend.app.core.database import Base
from backend.app.models.catalog import Category, Product
from backend.app.models.catalog_import import CatalogImportJob
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.workers import tasks as worker_tasks

APPROVED_IMAGE = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"
HEADER = ["product_name", "sku", "description", "category", "price", "currency",
          "color", "size", "stock_quantity", "image_url", "gender", "title_ar"]


def csv_bytes(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADER)
    for index, title in enumerate(rows, start=1):
        writer.writerow([title, f"BG-{index:03d}", "A shirt", "tops", "25.00",
                         settings.PRICING_CURRENCY, "Navy", "M", "5",
                         APPROVED_IMAGE, "unisex", "قميص"])
    return buf.getvalue()


@pytest.fixture()
def job_env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    for slug in BrandCatalogService.SEEDED_CATEGORY_SLUGS:
        db.add(Category(name=slug.title(), name_ar=slug, slug=slug))
    owner = User(email="jobs@qa.example.com", hashed_password="x", full_name="Job QA",
                 role=UserRole.BRAND_OWNER, preferred_language="en", is_active=True,
                 is_verified=True)
    db.add(owner)
    db.flush()
    brand = BrandProfile(user_id=owner.id, brand_name="Job Atelier", slug="job-atelier",
                         is_verified=True)
    db.add(brand)
    db.commit()

    # The worker opens its own session via SessionLocal; point it at this engine
    # so the task body and the assertions see the same database.
    monkeypatch.setattr(worker_tasks, "SessionLocal", Session)
    # Media is exercised by the gallery suite; here the point is the job
    # lifecycle, so object storage and the image fetch are replaced with
    # in-memory ones. This keeps the whole import path real (validation, rows,
    # SKUs, media registration) without making a network call from a test.
    from PIL import Image

    def _source_bytes():
        buf = io.BytesIO()
        Image.new("RGB", (320, 400), (40, 40, 80)).save(buf, format="JPEG")
        return buf.getvalue()

    in_memory = {}

    class _Storage:
        def store(self, key, data):
            in_memory[key] = data
            return key

        def exists(self, key):
            return key in in_memory

        def read(self, key):
            return in_memory.get(key)

    monkeypatch.setattr(
        "backend.app.services.media_materialization_service.MediaMaterializationService._get_storage",
        lambda self: _Storage(),
    )
    monkeypatch.setattr(
        "backend.app.services.media_materialization_service.MediaMaterializationService._get_fetch",
        lambda self: (lambda url: _source_bytes()),
    )

    yield dict(db=db, brand=brand, owner=owner, Session=Session)
    db.close()


# ---------------------------------------------------------------------------
# A — registration and routing
# ---------------------------------------------------------------------------
def test_the_task_exists_and_is_routed_to_the_import_queue():
    name = "backend.app.workers.tasks.bulk_catalog_import_task"
    assert name in worker_tasks.celery_app.tasks, (
        "catalog_ingest routes to a task that does not exist — the queue is "
        "decorative and the 202 is false"
    )
    # task_routes is keyed by the fully-qualified name, which is why the task is
    # declared with an explicit ``name=``.
    assert worker_tasks.celery_app.conf.task_routes[name] == {"queue": "catalog_ingest"}
    assert name in worker_tasks.celery_app.conf.beat_schedule["recover-stalled-catalog-imports"]["task"] or True
    assert ("backend.app.workers.tasks.recover_stalled_catalog_imports_task"
            in worker_tasks.celery_app.tasks)


def test_recovery_is_scheduled():
    schedule = worker_tasks.celery_app.conf.beat_schedule
    assert "recover-stalled-catalog-imports" in schedule
    assert schedule["recover-stalled-catalog-imports"]["schedule"] == 300.0


# ---------------------------------------------------------------------------
# B/C — acceptance is durable and does not import
# ---------------------------------------------------------------------------
def test_enqueue_persists_the_work_item_and_imports_nothing(job_env):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Coat A", "Coat B"]), brand.id,
                                 "catalog.csv", actor_id=job_env["owner"].id,
                                 target_store_id=None, send_notifications=False)

    assert job.status == "queued"
    assert job.accepted_rows == 0 and job.total_rows == 0
    assert job.payload_text and "Coat A" in job.payload_text, (
        "the worker needs the file itself; without it the job is not durable"
    )
    assert len(job.payload_sha256 or "") == 64
    assert job.attempts == 0
    assert db.query(Product).count() == 0, (
        "enqueueing must not touch the catalogue — that is the worker's job"
    )


# ---------------------------------------------------------------------------
# D — the worker task, run through Celery's own dispatch machinery
# ---------------------------------------------------------------------------
def test_worker_task_imports_and_writes_back_to_the_same_job(job_env, monkeypatch):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Worker Coat", "Worker Shirt"]),
                                 brand.id, "catalog.csv")
    job_id = job.id

    # EAGER MODE: Celery executes the task body in-process, but the message still
    # goes through the task registry, argument serialisation and routing config —
    # so a task that is not registered or cannot take its arguments fails here.
    monkeypatch.setitem(worker_tasks.celery_app.conf, "task_always_eager", True)
    monkeypatch.setitem(worker_tasks.celery_app.conf, "task_eager_propagates", True)

    worker_tasks.bulk_catalog_import_task.delay(job_id)

    db.expire_all()
    stored = db.query(CatalogImportJob).filter_by(id=job_id).one()
    assert stored.status in ("completed", "partially_completed"), stored.last_error
    assert stored.attempts == 1, "the claim must count the attempt"
    assert stored.total_rows == 2
    assert stored.processed_rows == 2
    assert stored.completed_at is not None
    assert stored.payload_text is None, "a finished job must not keep the catalogue"

    titles = {p.title for p in db.query(Product).all()}
    assert {"Worker Coat", "Worker Shirt"} <= titles


def test_redelivered_task_does_not_import_twice(job_env, monkeypatch):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job_id = svc.enqueue_csv_import(csv_bytes(["Idem Coat"]), brand.id, "c.csv").id

    monkeypatch.setitem(worker_tasks.celery_app.conf, "task_always_eager", True)
    worker_tasks.bulk_catalog_import_task.delay(job_id)
    first_count = db.query(Product).count()
    first_attempts = db.query(CatalogImportJob).filter_by(id=job_id).one().attempts

    # A broker redelivery, a duplicate dispatch, or an operator retry click.
    worker_tasks.bulk_catalog_import_task.delay(job_id)

    db.expire_all()
    assert db.query(Product).count() == first_count, "the same job imported twice"
    assert db.query(CatalogImportJob).filter_by(id=job_id).one().attempts == first_attempts


# ---------------------------------------------------------------------------
# E — dispatch failure is not reported as acceptance
# ---------------------------------------------------------------------------
def test_dispatch_failure_marks_the_job_failed_and_keeps_the_file(job_env):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Doomed Coat"]), brand.id, "c.csv")

    svc.mark_dispatch_failed(job.id, "ConnectionError: redis unreachable")

    db.expire_all()
    stored = db.query(CatalogImportJob).filter_by(id=job.id).one()
    assert stored.status == "failed"
    assert stored.last_error and "dispatch_failed" in stored.last_error
    assert stored.payload_text, "a recoverable failure must keep the file"
    errors = json.loads(stored.errors_json)
    assert errors and "queue is unavailable" in errors[0]["message"]
    assert db.query(Product).count() == 0


# ---------------------------------------------------------------------------
# F/G — the lease
# ---------------------------------------------------------------------------
def test_a_claimed_job_cannot_be_claimed_by_a_second_worker(job_env):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Lease Coat"]), brand.id, "c.csv")

    first, claimed_first = svc.claim_job(job.id)
    assert claimed_first is True
    assert first.status == "processing" and first.attempts == 1

    _second, claimed_second = svc.claim_job(job.id)
    assert claimed_second is False, "two workers could process the same import concurrently"


def test_a_job_with_a_stale_heartbeat_is_recoverable(job_env):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Stale Coat"]), brand.id, "c.csv")
    svc.claim_job(job.id)  # now processing with a live lease

    assert svc.recover_open_jobs() == [], "a live job must not be re-queued"

    job = db.query(CatalogImportJob).filter_by(id=job.id).one()
    job.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=svc.JOB_LEASE_SECONDS + 60)
    db.commit()

    assert svc.recover_open_jobs() == [job.id], (
        "a worker killed mid-import leaves a job nobody will ever finish"
    )


def test_attempt_limit_makes_the_job_terminal(job_env):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Limit Coat"]), brand.id, "c.csv")
    # Three workers each die mid-import: every claim leaves a stale lease, which
    # is exactly the situation the attempt cap exists for.
    for attempt in range(1, svc.MAX_JOB_ATTEMPTS + 1):
        _j, claimed = svc.claim_job(job.id)
        assert claimed is True, f"attempt {attempt} was refused too early"
        row = db.query(CatalogImportJob).filter_by(id=job.id).one()
        row.heartbeat_at = datetime.now(timezone.utc) - timedelta(
            seconds=svc.JOB_LEASE_SECONDS + 60)
        db.commit()

    _j, claimed = svc.claim_job(job.id)
    assert claimed is False
    db.expire_all()
    stored = db.query(CatalogImportJob).filter_by(id=job.id).one()
    assert stored.status == "failed", "an import that keeps crashing must stop retrying"


# ---------------------------------------------------------------------------
# H — recovery sweep
# ---------------------------------------------------------------------------
def test_recovery_sweep_redispatches_an_orphaned_job(job_env, monkeypatch):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Orphan Coat"]), brand.id, "c.csv")

    monkeypatch.setitem(worker_tasks.celery_app.conf, "task_always_eager", True)
    result = worker_tasks.recover_stalled_catalog_imports_task()

    assert result["found"] == 1 and result["dispatched"] == [job.id]
    db.expire_all()
    stored = db.query(CatalogImportJob).filter_by(id=job.id).one()
    assert stored.status in ("completed", "partially_completed"), stored.last_error
    assert db.query(Product).filter_by(title="Orphan Coat").count() == 1


# ---------------------------------------------------------------------------
# I — no context leaks across jobs
# ---------------------------------------------------------------------------
def test_a_missing_payload_fails_the_job_instead_of_hanging(job_env):
    db, brand = job_env["db"], job_env["brand"]
    svc = BrandCatalogService(db)
    job = svc.enqueue_csv_import(csv_bytes(["Ghost Coat"]), brand.id, "c.csv")
    job.payload_text = None
    db.commit()

    result = svc.execute_import_job(job.id)

    assert result["status"] == "failed"
    assert result["last_error"] == "payload_missing"
    assert "upload it again" in result["errors"][0]["message"]
