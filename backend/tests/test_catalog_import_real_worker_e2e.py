"""A REAL broker and a REAL worker process, end to end.

The rest of the import suite runs the task in-process (Celery eager mode). That
proves the task body works, but it does not prove the thing this section is
about: that a job survives the request, is picked up by a *separate* process
consuming the `catalog_ingest` queue, and writes its result back to the row the
API returned.

So this test starts an actual `celery worker` subprocess against an actual broker
and an actual database file, publishes the job from the test process, and then
asserts on the database — not on a mock, and not on a return value from the
publishing side. The only substitutions are the two genuinely external
dependencies:

* broker = Kombu's filesystem transport (a real message queue on disk; there is
  no Redis service in this environment and a fake in-memory broker would defeat
  the point);
* object storage / image fetching = not exercised, because this CSV carries no
  image column, so the worker never needs either. (Image materialisation is
  covered, with in-memory doubles, in test_catalog_import_background_job.py.)

Skipped when the `celery` executable is unavailable.
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.catalog import Category, Product
from backend.app.models.catalog_import import CatalogImportJob
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services.brand_catalog_service import BrandCatalogService
from celery import Celery
from backend.app.workers.celery_app import celery_app

REPO = Path(__file__).resolve().parents[2]
CELERY_BIN = REPO / ".venv" / "bin" / "celery"
# An approved stock source (the importer refuses unapproved hosts outright), so
# the row is valid; the worker's fetch and object storage are replaced below.
APPROVED_IMAGE = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"

pytestmark = pytest.mark.skipif(
    not CELERY_BIN.exists(),
    reason="the celery executable is required for a real worker process",
)


def _csv_text(titles):
    buf = io.StringIO()
    writer = csv.writer(buf)
    # The canonical header (see BrandCatalogService.REQUIRED_FIELDS). The image
    # column is present but EMPTY, so the worker never needs the network or
    # object storage — this test is about the queue and the process, not media.
    writer.writerow(["title", "sku_code", "description", "category_slug",
                     "base_price", "color_family", "thumbnail_url", "size",
                     "stock_level", "gender", "title_ar"])
    for i, title in enumerate(titles, start=1):
        writer.writerow([title, f"EW-{i:03d}", "Wool coat", "tops", "410.00",
                         "Charcoal", APPROVED_IMAGE, "M", "7", "unisex", "معطف"])
    return buf.getvalue()


@pytest.fixture()
def worker_env(tmp_path):
    """A broker directory, a database file, and a worker that consumes both."""
    db_path = tmp_path / "worker.db"
    broker_in = tmp_path / "broker" / "in"
    broker_out = tmp_path / "broker" / "out"
    broker_done = tmp_path / "broker" / "processed"
    # Kombu's filesystem transport also writes queue/exchange "control" files.
    # Left unset they land in the process CWD — which for this test is the repo.
    control = tmp_path / "broker" / "control"
    for path in (broker_in, broker_out, broker_done, control):
        path.mkdir(parents=True)

    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        for slug in BrandCatalogService.SEEDED_CATEGORY_SLUGS:
            db.add(Category(name=slug.title(), name_ar=slug, slug=slug))
        owner = User(email="real-worker@qa.example.com", hashed_password="x",
                     full_name="Worker QA", role=UserRole.BRAND_OWNER,
                     preferred_language="en", is_active=True, is_verified=True)
        db.add(owner)
        db.flush()
        brand = BrandProfile(user_id=owner.id, brand_name="Real Worker Atelier",
                             slug="real-worker-atelier", is_verified=True)
        db.add(brand)
        db.commit()
        brand_id = brand.id

    # A dedicated publisher app, NOT a mutation of the shared `celery_app`: other
    # tests in the suite use `.delay()` against it, and Celery caches the resolved
    # broker/backend per app, so re-pointing the shared one mid-run would leak
    # into them (measured: the full suite failed here with the redis result
    # backend still cached from an earlier test).
    #
    # The task NAME and the QUEUE are read from the production app's routing
    # config below, so this test still fails if the task is renamed or re-routed.
    publisher = Celery("confit_e2e_publisher", broker="filesystem://localhost/",
                       backend=None)
    publisher.conf.update(
        task_serializer="json",
        accept_content=["json"],
        broker_transport_options={
            "data_folder_in": str(broker_in),
            "data_folder_out": str(broker_in),
            "data_folder_processed": str(broker_done),
            "control_folder": str(control),
        },
    )

    # The worker process must consume the SAME broker the test publishes to. The
    # app reads its broker from settings (Redis in production), so the bootstrap
    # below points that one app instance at the filesystem queue and nothing else:
    # the task, the routing (`catalog_ingest`) and the database session are the
    # production ones.
    bootstrap = tmp_path / "worker_bootstrap.py"
    bootstrap.write_text(
        "import os\n"
        "from backend.app.workers.celery_app import celery_app\n"
        "celery_app.conf.broker_url = 'filesystem://localhost/'\n"
        "celery_app.conf.broker_transport_options = {\n"
        "    'data_folder_in': os.environ['BROKER_IN'],\n"
        "    'data_folder_out': os.environ['BROKER_IN'],\n"
        "    'data_folder_processed': os.environ['BROKER_DONE'],\n"
        "    'control_folder': os.environ['BROKER_CONTROL'],\n"
        "}\n"
        "celery_app.conf.result_backend = None\n"
        # The two genuinely external dependencies, replaced inside the worker
        # process itself: image download and object storage. Everything else —
        # the broker, the queue, the task, the service, the database — is real.
        "import io\n"
        "from PIL import Image\n"
        "from backend.app.services.media_materialization_service import MediaMaterializationService\n"
        "_store = {}\n"
        "class _Storage:\n"
        "    def store(self, key, data):\n"
        "        _store[key] = data\n"
        "        return key\n"
        "    def exists(self, key):\n"
        "        return key in _store\n"
        "    def read(self, key):\n"
        "        return _store.get(key)\n"
        "def _image_bytes():\n"
        "    buf = io.BytesIO()\n"
        "    Image.new('RGB', (320, 400), (40, 40, 80)).save(buf, format='JPEG')\n"
        "    return buf.getvalue()\n"
        "MediaMaterializationService._get_storage = lambda self: _Storage()\n"
        "MediaMaterializationService._get_fetch = lambda self: (lambda url: _image_bytes())\n"
        "celery_app.worker_main(['worker', '--pool=solo', '-Q', 'catalog_ingest',\n"
        "                        '--loglevel=info', '--without-heartbeat',\n"
        "                        '--without-gossip', '--without-mingle'])\n"
    )
    env = {
        **os.environ,
        "DATABASE_URL": db_url,
        "CONFIT_IGNORE_DOTENV": "1",
        "PYTHONPATH": str(REPO),
        "BROKER_IN": str(broker_in),
        "BROKER_DONE": str(broker_done),
        "BROKER_CONTROL": str(control),
    }
    worker = subprocess.Popen(
        [sys.executable, str(bootstrap)],
        # cwd is the temp dir, not the repo: a worker that drops files where it
        # happens to stand must not be able to dirty the checkout. PYTHONPATH
        # points it back at the repository for imports.
        cwd=str(tmp_path), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True,
    )
    try:
        # Wait for "ready" rather than sleeping a fixed amount.
        ready = False
        deadline = time.time() + 60
        log: list[str] = []
        while time.time() < deadline:
            line = worker.stdout.readline()
            if not line:
                if worker.poll() is not None:
                    break
                continue
            log.append(line)
            if "ready" in line.lower() or "celery@" in line.lower():
                ready = True
                break
        if not ready:
            worker.kill()
            pytest.fail("worker never became ready:\n" + "".join(log[-30:]))
        yield {"db_url": db_url, "brand_id": brand_id, "Session": Session,
               "worker": worker, "log": log, "publisher": publisher}
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=20)
        except subprocess.TimeoutExpired:
            worker.kill()


def test_a_separate_worker_process_completes_the_queued_import(worker_env):
    Session = worker_env["Session"]
    with Session() as db:
        svc = BrandCatalogService(db)
        job = svc.enqueue_csv_import(
            _csv_text(["Broker Coat", "Broker Trench"]),
            worker_env["brand_id"], "broker.csv",
        )
        job_id = job.id
        assert job.status == "queued"
        assert db.query(Product).count() == 0

    # Publish. This is a real message to a real broker, consumed by a real
    # process — exactly what the HTTP endpoint does after it commits the job.
    task_name = "backend.app.workers.tasks.bulk_catalog_import_task"
    queue = celery_app.conf.task_routes[task_name]["queue"]
    worker_env["publisher"].send_task(task_name, args=[job_id], queue=queue)

    deadline = time.time() + 120
    status = None
    while time.time() < deadline:
        with Session() as db:
            db.expire_all()
            stored = db.query(CatalogImportJob).filter_by(id=job_id).one()
            status = stored.status
            if status in ("completed", "partially_completed", "failed"):
                break
        time.sleep(1)

    with Session() as db:
        stored = db.query(CatalogImportJob).filter_by(id=job_id).one()
        assert stored.status in ("completed", "partially_completed"), (
            f"worker finished with {stored.status}: {stored.last_error}\n"
            f"stored errors: {stored.errors_json}\n"
            f"worker log:\n{''.join(worker_env['log'])[-4000:]}"
        )
        assert stored.attempts == 1
        assert stored.processed_rows == 2
        assert stored.accepted_rows == 2
        assert stored.payload_text is None
        titles = {p.title for p in db.query(Product).all()}
        assert {"Broker Coat", "Broker Trench"} <= titles
