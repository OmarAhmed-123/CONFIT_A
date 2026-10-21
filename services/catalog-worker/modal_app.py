"""Modal deployment wrapper for CONFIT's Celery background worker & maintenance sweeps.

Runs the real Celery worker (`backend.app.workers.celery_app`) on Modal cloud
infrastructure in Frankfurt (`eu-central`, matching Vercel `fra1` and Neon
PostgreSQL / S3 in `eu-central-1`):

  1. Scheduled 5-minute maintenance & queue-drain sweep (`recover_and_drain`):
     - Re-enqueues any stale `queued` / crashed `running` catalog imports via
       `recover_stalled_catalog_imports_task`.
     - Releases expired checkout inventory reservations via
       `release_expired_inventory_reservations_task`.
     - Starts a real `celery ... worker --burst` pass across
       `catalog_ingest,wardrobe_jobs,analytics_rollups,maintenance` until all
       pending broker messages have drained cleanly.
  2. Long-running real-time worker (`run_worker_window`):
     - Keeps an active Celery worker attached to Upstash/TLS Redis for immediate
       sub-second pickup of newly submitted brand CSV imports.

Deploy command (operator runbook):
  modal secret create confit-catalog-worker \\
    DATABASE_URL="<production-or-staging-postgres-url>" \\
    REDIS_URL="<upstash-rediss-url>" \\
    STORAGE_PROVIDER="s3" \\
    S3_BUCKET="confit-a-media" \\
    AWS_ENDPOINT_URL_S3="<neon-s3-endpoint>" \\
    AWS_ACCESS_KEY_ID="<access-key>" \\
    AWS_SECRET_ACCESS_KEY="<secret-key>" \\
    AWS_REGION="eu-central-1" \\
    SECRET_KEY="<app-secret-key>"
  modal deploy services/catalog-worker/modal_app.py
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_NAME = os.environ.get("CONFIT_CATALOG_WORKER_SECRET", "confit-catalog-worker")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(REPO_ROOT / "backend" / "requirements.txt"))
    .env({"PYTHONPATH": "/root/project"})
    .add_local_dir(str(REPO_ROOT / "backend"), remote_path="/root/project/backend")
)

app = modal.App("confit-catalog-worker", image=image)


def _celery_cmd(*extra_args: str) -> list[str]:
    return [
        "celery",
        "-A",
        "backend.app.workers.celery_app",
        "worker",
        "-Q",
        "catalog_ingest,wardrobe_jobs,analytics_rollups,maintenance",
        "--loglevel=info",
        "--concurrency=2",
        *extra_args,
    ]


@app.function(
    timeout=900,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    schedule=modal.Period(minutes=5),
)
def recover_and_drain() -> dict:
    """Periodic 5-minute recovery sweep + full burst drain on real Celery."""
    from backend.app.workers.tasks import (
        recover_stalled_catalog_imports_task,
        release_expired_inventory_reservations_task,
    )

    recovery_summary = recover_stalled_catalog_imports_task.apply().get()
    reservation_summary = release_expired_inventory_reservations_task.apply().get()
    burst = subprocess.run(
        _celery_cmd("--burst"),
        cwd="/root/project",
        capture_output=True,
        text=True,
        timeout=600,
    )
    return {
        "recovery": recovery_summary,
        "reservations": reservation_summary,
        "burst_returncode": burst.returncode,
    }


@app.function(
    timeout=3600,
    secrets=[modal.Secret.from_name(SECRET_NAME)],
)
def run_worker_window(max_tasks_per_child: int = 50) -> int:
    """Attach a live real-time Celery worker to the configured Redis broker."""
    proc = subprocess.run(
        _celery_cmd(f"--max-tasks-per-child={max_tasks_per_child}"),
        cwd="/root/project",
        check=False,
    )
    return proc.returncode
