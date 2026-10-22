"""Modal cloud deployment for CONFIT's production Catalog Import & Maintenance Worker.

Supports BOTH cloud execution transports seamlessly:
  1. Authenticated asynchronous HTTPS dispatch (`dispatch_import` -> `process_catalog_import_job.spawn`):
     - Zero single point of failure on Redis across global serverless Vercel regions.
     - Enforces constant-time `X-Catalog-Worker-Token` authentication (`CATALOG_WORKER_ADMIN_TOKEN`).
     - Executes `execute_catalog_import_with_retries(job_id)` against Neon PostgreSQL + S3 (`confit-a-media`).
  2. Real-time / scheduled Celery + durable queue recovery (`recover_and_drain` every 5 minutes,
     plus `run_worker_window` for persistent Redis Celery streaming when `REDIS_URL` is configured):
     - Reclaims orphaned `queued` and stalled `processing` jobs via `BrandCatalogService.recover_open_jobs()`.
     - Drains all open jobs directly when no external Redis broker is configured, or runs real Celery drain when configured.
     - Releases expired checkout `inventory_reservations` and purges expired VTON sessions.
  3. Authenticated operational health & queue telemetry endpoint (`worker_health`):
     - Measures live Neon DB connectivity, queue counts (`queued`, `processing`, `stalled`, `completed`, `failed`),
       S3 bucket readiness, and external Redis status without exposing secrets.
"""

import hmac
import os
import signal
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import modal
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

_RESOLVED_FILE = Path(__file__).resolve()
REPO_ROOT = _RESOLVED_FILE.parents[2] if len(_RESOLVED_FILE.parents) > 2 else Path("/root/project")
SECRET_NAME = os.environ.get("CONFIT_CATALOG_WORKER_SECRET", "confit-catalog-worker")
QUEUES = ("catalog_ingest", "wardrobe_jobs", "analytics_rollups", "maintenance")

if modal.is_local():
    image = (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install_from_requirements(str(REPO_ROOT / "backend" / "requirements.txt"))
        .env({
            "PYTHONPATH": "/root/project",
            "STORAGE_PROVIDER": "s3",
            "CATALOG_IMPORT_ALLOW_OWN_IMAGES": "true",
        })
        .add_local_dir(str(REPO_ROOT / "backend"), remote_path="/root/project/backend")
        .add_local_file(str(_RESOLVED_FILE), remote_path="/root/project/modal_app.py")
    )
else:
    image = modal.Image.debian_slim(python_version="3.12")

app = modal.App("confit-catalog-worker", image=image)


def _normalize_worker_env() -> None:
    """Bridge `S3_ENDPOINT_URL` <-> `AWS_ENDPOINT_URL_S3` and `STORAGE_PROVIDER` cleanly."""
    s3_ep = os.environ.get("S3_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL_S3")
    if s3_ep:
        os.environ.setdefault("S3_ENDPOINT_URL", s3_ep)
        os.environ.setdefault("AWS_ENDPOINT_URL_S3", s3_ep)
    if os.environ.get("S3_BUCKET") or os.environ.get("AWS_S3_BUCKET"):
        os.environ.setdefault("STORAGE_PROVIDER", "s3")


def _require_worker_token(request: Request) -> None:
    expected = (os.environ.get("CATALOG_WORKER_ADMIN_TOKEN") or "").strip()
    provided = (request.headers.get("x-catalog-worker-token") or "").strip()
    if not provided:
        auth_hdr = (request.headers.get("authorization") or "").strip()
        if auth_hdr.lower().startswith("bearer "):
            provided = auth_hdr[7:].strip()
    if not expected or not provided or not hmac.compare_digest(expected.encode(), provided.encode()):
        raise HTTPException(
            status_code=401,
            detail=f"Unauthorized catalog worker request (env_present={bool(expected)}, hdr_present={bool(provided)})",
        )


def _celery_cmd(*extra_args: str) -> list[str]:
    return [
        "celery",
        "-A",
        "backend.app.workers.celery_app",
        "worker",
        "-Q",
        ",".join(QUEUES),
        "--loglevel=info",
        "--concurrency=2",
        *extra_args,
    ]


@app.function(
    timeout=900,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
)
def process_catalog_import_job(job_id: int) -> Dict[str, Any]:
    """Execute one durable catalog-import job with retries, heartbeats, and S3 materialization."""
    _normalize_worker_env()
    from backend.app.workers.tasks import execute_catalog_import_with_retries

    return execute_catalog_import_with_retries(int(job_id), max_attempts=3)


def build_worker_fastapi_app() -> FastAPI:
    """Construct the authenticated FastAPI control plane (`/dispatch` + `/health`)."""
    _normalize_worker_env()
    api = FastAPI(title="CONFIT Catalog Worker Control Plane", docs_url=None, redoc_url=None)

    @api.post("/dispatch", status_code=202)
    async def post_dispatch(request: Request):
        _require_worker_token(request)
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Invalid JSON payload") from exc
        raw_job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if not isinstance(raw_job_id, int) or isinstance(raw_job_id, bool) or raw_job_id <= 0:
            raise HTTPException(status_code=422, detail="job_id must be a positive integer")
        call = process_catalog_import_job.spawn(int(raw_job_id))
        return JSONResponse(
            status_code=202,
            content={
                "accepted": True,
                "job_id": int(raw_job_id),
                "call_id": getattr(call, "object_id", f"modal-{raw_job_id}"),
            },
        )

    @api.get("/health")
    def get_health(request: Request):
        _require_worker_token(request)
        from sqlalchemy import func
        from backend.app.core.config import settings
        from backend.app.core.database import SessionLocal
        from backend.app.models.catalog_import import CatalogImportJob
        from backend.app.services.brand_catalog_service import BrandCatalogService
        from backend.app.services.storage_service import storage_status

        db = SessionLocal()
        try:
            counts_raw = dict(
                db.query(CatalogImportJob.status, func.count(CatalogImportJob.id))
                .group_by(CatalogImportJob.status)
                .all()
            )
            stale_cutoff = datetime.now(timezone.utc) - timedelta(
                seconds=int(getattr(BrandCatalogService, "HEARTBEAT_STALE_SECONDS", 600))
            )
            stalled_count = (
                db.query(func.count(CatalogImportJob.id))
                .filter(CatalogImportJob.status == "processing")
                .filter(
                    (CatalogImportJob.heartbeat_at.is_(None))
                    | (CatalogImportJob.heartbeat_at < stale_cutoff)
                )
                .scalar()
                or 0
            )
            latest_completed = (
                db.query(CatalogImportJob.id, CatalogImportJob.completed_at)
                .filter(CatalogImportJob.status == "completed")
                .order_by(CatalogImportJob.completed_at.desc())
                .first()
            )
        finally:
            db.close()

        redis_state = "not_configured"
        if settings.has_external_redis and not str(settings.REDIS_URL or "").startswith("memory://"):
            try:
                import redis as redis_lib

                rc = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
                rc.ping()
                redis_state = "healthy"
            except Exception as exc:
                redis_state = f"unreachable:{type(exc).__name__}"

        storage = storage_status()
        storage_ok = bool(storage.get("production_grade"))
        return {
            "status": "healthy",
            "ready": True,
            "storage_ready": storage_ok,
            "worker_app": "confit-catalog-worker",
            "environment": settings.ENVIRONMENT,
            "database": "healthy",
            "storage": {
                "provider": storage.get("provider"),
                "production_grade": storage_ok,
                "bucket": settings.s3_bucket,
            },
            "redis_broker": redis_state,
            "queue_counts": {
                "queued": int(counts_raw.get("queued", 0)),
                "processing": int(counts_raw.get("processing", 0)),
                "completed": int(counts_raw.get("completed", 0)),
                "partially_completed": int(counts_raw.get("partially_completed", 0)),
                "failed": int(counts_raw.get("failed", 0)),
                "stalled": int(stalled_count),
            },
            "last_completed_job": (
                {
                    "job_id": latest_completed[0],
                    "completed_at": latest_completed[1].isoformat() if latest_completed[1] else None,
                }
                if latest_completed
                else None
            ),
        }

    return api


@app.function(
    timeout=60,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
)
@modal.asgi_app(label="confit-catalog-worker-http")
def worker_http_app():
    return build_worker_fastapi_app()


@app.function(
    timeout=900,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    schedule=modal.Period(minutes=5),
)
def recover_and_drain() -> dict:
    """Periodic 5-minute recovery sweep + durable Postgres/Celery queue drain."""
    _normalize_worker_env()
    from backend.app.core.config import settings
    from backend.app.core.database import SessionLocal
    from backend.app.services.brand_catalog_service import BrandCatalogService
    from backend.app.workers.tasks import (
        execute_catalog_import_with_retries,
        purge_expired_sessions_task,
        recover_stalled_catalog_imports_task,
        release_expired_inventory_reservations_task,
    )

    reservation_summary = release_expired_inventory_reservations_task.apply().get()
    privacy_summary = purge_expired_sessions_task.apply().get()

    if settings.has_external_redis:
        import redis as redis_lib

        recovery_summary = recover_stalled_catalog_imports_task.apply().get()
        rc = redis_lib.from_url(settings.REDIS_URL)
        proc = subprocess.Popen(_celery_cmd("--pool=solo"), cwd="/root/project")
        try:
            idle_ticks = 0
            deadline = time.monotonic() + 540
            while time.monotonic() < deadline and proc.poll() is None:
                depth = sum(int(rc.llen(q)) for q in QUEUES)
                idle_ticks = idle_ticks + 1 if depth == 0 else 0
                if idle_ticks >= 4:
                    break
                time.sleep(1.5)
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        return {
            "mode": "redis_celery",
            "recovery": recovery_summary,
            "reservations": reservation_summary,
            "privacy": privacy_summary,
            "worker_returncode": proc.returncode,
        }

    db = SessionLocal()
    try:
        open_job_ids = BrandCatalogService(db).recover_open_jobs()
    finally:
        db.close()

    drained = []
    for jid in open_job_ids:
        res = execute_catalog_import_with_retries(int(jid), max_attempts=3)
        drained.append({"job_id": int(jid), "status": res.get("status")})

    return {
        "mode": "durable_postgres",
        "recovered_count": len(open_job_ids),
        "drained": drained,
        "reservations": reservation_summary,
        "privacy": privacy_summary,
    }


@app.function(
    timeout=3600,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
)
def run_worker_window(max_tasks_per_child: int = 50) -> int:
    """Attach a live real-time Celery worker to an external Redis broker."""
    _normalize_worker_env()
    proc = subprocess.run(
        _celery_cmd(f"--max-tasks-per-child={max_tasks_per_child}"),
        cwd="/root/project",
        check=False,
    )
    return proc.returncode
