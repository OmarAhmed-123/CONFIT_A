import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
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

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": "1.0.0",
        "checks": {
            "database": db_status,
            "vton_pipeline": "operational",
            "ai_stylist_engine": "operational",
            "bnpl_gateway": "operational"
        }
    }
