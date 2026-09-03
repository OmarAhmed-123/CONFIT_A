import os
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.database import get_db, engine
from backend.app.core import schema_gate
from backend.app.core.dependencies import require_role, ADMIN_ROLES
from backend.app.models.user import User
from backend.app.services.storage_service import storage_status

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


def _revision_verdict(worker_sha) -> dict:
    """T4 — compare the deployed worker revision with the intended commit.

    Verdicts: ``match`` / ``mismatch`` / ``worker_unknown`` (worker predates the
    traceable build or reports 'unknown') / ``dirty_deploy`` (deployed from an
    uncommitted tree) / ``no_expected_sha`` (nothing to compare against on
    this host). Only a ``match`` is a passing gate.
    """
    expected = (
        (getattr(settings, "VTON_WORKER_EXPECTED_GIT_SHA", None) or "").strip()
        or os.environ.get("VTON_WORKER_EXPECTED_GIT_SHA", "").strip()
        or os.environ.get("VERCEL_GIT_COMMIT_SHA", "").strip()
    )
    out = {"expected_git_sha": expected or None, "worker_git_sha": worker_sha, "verdict": "no_expected_sha"}
    if not worker_sha or worker_sha == "unknown":
        out["verdict"] = "worker_unknown"
        return out
    if str(worker_sha).endswith("-dirty"):
        out["verdict"] = "dirty_deploy"
        return out
    if not expected:
        return out
    w, e = str(worker_sha).lower(), expected.lower()
    out["verdict"] = "match" if (w == e or w.startswith(e) or e.startswith(w)) and min(len(w), len(e)) >= 7 else "mismatch"
    return out


async def probe_vton_worker_contract(timeout: float = 45.0) -> dict:  # < Vercel maxDuration 60 s; cold start of a scaled-to-zero GPU container can exceed this -> "worker_unreachable", retry
    """T6 — verify the API ↔ GPU-worker credential CONTRACT without ever
    reading, printing or rotating the secret.

    Sends an intentionally invalid job (empty garments) with the configured
    X-VTON-Admin token. The worker authenticates BEFORE validating the payload:

        401 UNAUTHORIZED           -> token mismatch (API env ≠ Modal secret)
        422 / 400 (payload error)  -> token accepted, contract consistent
        503 VTON_ENGINE_UNAVAILABLE-> token accepted, model not loaded

    Also reports the worker's /health metadata (git_sha, model, segmentation
    engine) and the T4 revision verdict: the worker's git_sha is compared with
    VTON_WORKER_EXPECTED_GIT_SHA (fallback: this API's own VERCEL_GIT_COMMIT_SHA)
    so a Modal deployment that does not match the intended commit is visible
    as ``revision: mismatch`` instead of silently serving old masks.
    """
    import httpx
    from backend.app.services.tryon_service import TryOnService

    worker_url = settings.VTON_WORKER_URL or os.environ.get("VTON_WORKER_URL")
    token = (
        settings.VTON_WORKER_ADMIN_TOKEN or settings.CONFIT_WORKER_ADMIN_TOKEN
        or os.environ.get("VTON_WORKER_ADMIN_TOKEN") or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN") or ""
    )
    result: dict = {
        "worker_configured": bool(worker_url),
        "token_configured": bool(token),
        "token_source": (
            "VTON_WORKER_ADMIN_TOKEN" if (settings.VTON_WORKER_ADMIN_TOKEN or os.environ.get("VTON_WORKER_ADMIN_TOKEN"))
            else "CONFIT_WORKER_ADMIN_TOKEN" if token else None
        ),
        "contract": "unknown",
    }
    if not worker_url:
        result["contract"] = "worker_not_configured"
        return result

    health_url, readiness_url, process_url = TryOnService._derive_worker_urls(TryOnService.__new__(TryOnService), worker_url)
    result["endpoints"] = {"health": health_url, "readiness": readiness_url, "process": process_url}
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            h = await client.get(health_url)
            hj = h.json() if h.headers.get("content-type", "").startswith("application/json") else {}
            result["worker_health"] = {
                "status_code": h.status_code,
                "git_sha": hj.get("git_sha"),
                "model": hj.get("model"),
                "model_loaded": hj.get("model_loaded"),
                "segmentation_model": hj.get("segmentation_model"),
                "mask_engine": hj.get("mask_engine"),
                "device": hj.get("device"),
            }
        except Exception as exc:  # noqa: BLE001
            result["worker_health"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

        result["revision"] = _revision_verdict(result["worker_health"].get("git_sha"))

        if not token:
            result["contract"] = "token_missing_on_api"
            return result
        try:
            r = await client.post(
                process_url,
                json={"job_id": "contract_probe", "user_image_base64_or_url": "probe", "garments": []},
                headers={"X-VTON-Admin": token},
            )
            result["probe_status_code"] = r.status_code
            if r.status_code == 401:
                result["contract"] = "token_mismatch"
                result["remediation"] = (
                    "API env VTON_WORKER_ADMIN_TOKEN/CONFIT_WORKER_ADMIN_TOKEN ≠ Modal secret "
                    "confit-worker-admin-token (CONFIT_WORKER_ADMIN_TOKEN). Owner: set both sides to the SAME value."
                )
            elif r.status_code in (400, 422):
                result["contract"] = "consistent"
            elif r.status_code == 503:
                result["contract"] = "consistent_but_worker_not_ready"
            else:
                result["contract"] = f"unexpected_http_{r.status_code}"
        except Exception as exc:  # noqa: BLE001
            result["contract"] = "worker_unreachable"
            result["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return result


@router.get("/health/vton-contract", include_in_schema=False)
async def vton_contract_check(user: User = Depends(require_role(ADMIN_ROLES))):
    """Admin-only. Live verification of the GPU-worker credential contract and
    deployed worker revision. Never returns the token."""
    return await probe_vton_worker_contract()


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
            # Where uploads/labels would be persisted. "local" is development-only
            # and read-only/ephemeral on serverless hosts: upload features answer
            # 501 FEATURE_NOT_CONFIGURED in production until object storage is set.
            "storage": storage_status(),
            "ai_stylist_engine": "operational",
            "bnpl_gateway": "operational"
        },
        "ai_providers": ai_providers
    }
