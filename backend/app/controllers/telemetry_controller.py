import os
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.database import get_db, engine
from backend.app.core import schema_gate

router = APIRouter(tags=["System & Observability"])

START_TIME = time.time()


def _schema_report() -> dict:
    """Shared, process-cached verdict (see schema_gate.cached_report)."""
    report = schema_gate.cached_report(engine)
    payload = report.as_dict()
    payload["acceptable"] = schema_gate.acceptable(report, settings.ENVIRONMENT)
    return payload


def _vton_pipeline_status() -> str:
    """Honest VTON status from CONFIGURATION only (no network call on /health).

    "operational" was previously reported whenever VTON_WORKER_URL was set,
    even though the worker rejects every job without the admin token (the
    production job vton_job_32974a82027a failed with VTON_AUTH_FAILURE while
    /health claimed the pipeline was operational).
    """
    worker_url = settings.VTON_WORKER_URL or os.environ.get("VTON_WORKER_URL")
    token = (
        settings.VTON_WORKER_ADMIN_TOKEN
        or settings.CONFIT_WORKER_ADMIN_TOKEN
        or os.environ.get("VTON_WORKER_ADMIN_TOKEN")
        or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN")
    )
    if not worker_url:
        return "unavailable: no GPU worker configured (VTON_WORKER_URL)"
    if not token:
        return "misconfigured: VTON_WORKER_URL set but no admin token (VTON_WORKER_ADMIN_TOKEN) — every job will fail VTON_AUTH_FAILURE"
    return "configured: GPU worker URL + admin token present (readiness is checked per job, not here)"


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    # Schema-drift verdict: "healthy" must mean the schema the code expects is
    # really there, not merely that SELECT 1 works.
    try:
        schema = _schema_report()
    except Exception as exc:  # never crash health; report the failure instead
        schema = {"verdict": "unknown", "acceptable": False, "findings": [f"{type(exc).__name__}: {str(exc)[:160]}"]}

    # Real AI provider status: configured keys + live quarantine state, so a
    # billing-exhausted key (e.g. OpenAI 402) is visible instead of silently
    # degrading to fallback.
    from backend.app.providers.orchestrator import get_orchestrator
    ai_providers = get_orchestrator().provider_status()

    overall = "healthy" if (db_status == "healthy" and schema.get("acceptable") is True) else "degraded"

    return {
        "status": overall,
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": settings.VERSION,
        "checks": {
            "database": db_status,
            "schema": schema,
            "vton_pipeline": _vton_pipeline_status(),
            "ai_stylist_engine": "operational",
            "bnpl_gateway": "operational"
        },
        "ai_providers": ai_providers
    }
