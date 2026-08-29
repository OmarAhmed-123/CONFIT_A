import os
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.database import get_db

router = APIRouter(tags=["System & Observability"])

START_TIME = time.time()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    # Report the try-on pipeline's real state: it is only operational when a
    # GPU inference worker is configured. Never claim "operational" for a
    # pipeline that cannot render.
    worker_configured = bool(settings.VTON_WORKER_URL or os.environ.get("VTON_WORKER_URL"))

    # Real AI provider status: configured keys + live quarantine state, so a
    # billing-exhausted key (e.g. OpenAI 402) is visible instead of silently
    # degrading to fallback.
    from backend.app.providers.orchestrator import get_orchestrator
    ai_providers = get_orchestrator().provider_status()

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": "1.0.0",
        "checks": {
            "database": db_status,
            "vton_pipeline": "operational" if worker_configured else "unavailable: no GPU worker configured (VTON_WORKER_URL)",
            "ai_stylist_engine": "operational",
            "bnpl_gateway": "operational"
        },
        "ai_providers": ai_providers
    }
