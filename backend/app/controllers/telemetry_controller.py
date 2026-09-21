import logging
import os
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.config import settings, vton_engine_metadata
from backend.app.core.database import get_db, engine
from backend.app.core import schema_gate
from backend.app.core.dependencies import require_role, ADMIN_ROLES
from backend.app.models.user import User
from backend.app.services.storage_service import storage_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System & Observability"])

START_TIME = time.time()


def _schema_report() -> dict:
    """Shared, process-cached verdict (see schema_gate.cached_report)."""
    report = schema_gate.cached_report(engine)
    payload = report.as_dict()
    payload["acceptable"] = schema_gate.acceptable(report, settings.ENVIRONMENT)
    return payload


def public_schema_summary(schema: dict) -> dict:
    """The public subset of a schema report.

    `database_revision` and `verdict` are published deliberately: the release
    gate compares the revision in a commit against the revision production
    reports, through this endpoint, and that contract predates this change (see
    backend/scripts/check_release_schema_parity.py). The full report, including
    `findings`, is admin-only.

    NOTE ON WHAT IS NOT SCRUBBED: findings are removed, not sanitised, because a
    diagnostic string assembled elsewhere is not safe to publish merely because
    it was truncated.
    """
    return {
        "verdict": schema.get("verdict"),
        "expected_head": schema.get("expected_head"),
        "database_revision": schema.get("database_revision"),
        "acceptable": schema.get("acceptable"),
        # `findings` is intentionally omitted — see /health/details.
        "findings_redacted": bool(schema.get("findings")),
    }


def public_storage_summary(status: dict | None) -> dict:
    """The publishable part of a storage status.

    `storage_status()` is an operator view: the local backend reports the
    absolute filesystem root, and an object backend reports the bucket and
    endpoint. On an unauthenticated endpoint that is a map of the deployment.
    The verdicts are what a caller needs — is upload durable, and did the live
    probe succeed — and those stay. The identifiers move to /health/details.
    """
    status = status or {}
    keep = ("provider", "production_grade", "probe_ok", "probe_verdict", "reason")
    return {k: status[k] for k in keep if k in status}


def _vton_pipeline_state() -> str:
    """Coarse VTON readiness state, derived from CONFIGURATION only.

    Returns one of: ``unavailable``, ``misconfigured``, ``configured``.

    "operational" was previously reported whenever VTON_WORKER_URL was set,
    even though the worker rejects every job without the admin token (the
    production job vton_job_32974a82027a failed with VTON_AUTH_FAILURE while
    /health claimed the pipeline was operational). The state machine keeps that
    honesty contract.
    """
    worker_url = settings.VTON_WORKER_URL or os.environ.get("VTON_WORKER_URL")
    token = (
        settings.VTON_WORKER_ADMIN_TOKEN
        or settings.CONFIT_WORKER_ADMIN_TOKEN
        or os.environ.get("VTON_WORKER_ADMIN_TOKEN")
        or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN")
    )
    if not worker_url:
        return "unavailable"
    if not token:
        return "misconfigured"
    return "configured"


def _vton_pipeline_status() -> str:
    """The public string for ``/health``, WITH the prefix the honesty tests pin.

    The audit finding behind this change: the public payload used to name the
    internal environment variables and the exact worker failure mode —
    "misconfigured: VTON_WORKER_URL set but no admin token
    (VTON_WORKER_ADMIN_TOKEN) — every job will fail VTON_AUTH_FAILURE" — to every
    anonymous caller. None of that helps a shopper, and all of it is free
    reconnaissance. The operator detail moved to ``/health/details``, which is
    admin-only; the public string keeps the state and drops the config map.

    The prefix is preserved deliberately: ``test_schema_drift_gate`` asserts
    that health never claims "operational" and that a missing token reads
    "misconfigured", and those assertions are the guard against the older,
    flattering lie.
    """
    state = _vton_pipeline_state()
    if state == "unavailable":
        return "unavailable: no GPU worker configured"
    if state == "misconfigured":
        return "misconfigured: GPU worker credentials incomplete — jobs will fail authentication"
    return "configured: GPU worker credentials present (readiness is checked per job, not here)"


def _vton_pipeline_diagnostics() -> dict:
    """Operator detail for the admin-only endpoint. Names the variables so the
    person deploying knows what to set — that is the whole reason it is not
    public."""
    worker_url = settings.VTON_WORKER_URL or os.environ.get("VTON_WORKER_URL")
    token = (
        settings.VTON_WORKER_ADMIN_TOKEN
        or settings.CONFIT_WORKER_ADMIN_TOKEN
        or os.environ.get("VTON_WORKER_ADMIN_TOKEN")
        or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN")
    )
    return {
        "state": _vton_pipeline_state(),
        "worker_url_set": bool(worker_url),
        "admin_token_set": bool(token),
        "required_env": ["VTON_WORKER_URL", "VTON_WORKER_ADMIN_TOKEN"],
    }


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
    db_error: str | None = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        # The raw exception used to be interpolated straight into this PUBLIC,
        # unauthenticated payload (`f"unhealthy: {str(exc)}"`). A driver error
        # carries the host, the database and the role, and sometimes the failing
        # SQL — free reconnaissance from an endpoint anyone can poll. The type is
        # reported publicly because it is a fixed vocabulary; the message goes to
        # the logs and to the admin-only /health/details.
        logger.error("health: database check failed: %s: %s", type(exc).__name__, exc)
        db_status = "unhealthy"
        db_error = f"{type(exc).__name__}: {str(exc)[:200]}"

    # Schema-drift verdict: "healthy" must mean the schema the code expects is
    # really there, not merely that SELECT 1 works.
    try:
        schema = _schema_report()
    except Exception as exc:  # never crash health; report the failure instead
        schema = {"verdict": "unknown", "acceptable": False, "findings": [f"{type(exc).__name__}: {str(exc)[:160]}"]}

    overall = "healthy" if (db_status == "healthy" and schema.get("acceptable") is True) else "degraded"

    return {
        "status": overall,
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": settings.VERSION,
        # ── PUBLIC SURFACE ──────────────────────────────────────────────────
        # This endpoint is unauthenticated and polled by the uptime monitor, so
        # it carries liveness and the verdicts that other automated gates depend
        # on (release-gate reads checks.schema.database_revision) — and nothing
        # that reads like a deployment inventory.
        #
        # Moved behind require_role(ADMIN_ROLES) at /health/details:
        #   · schema.findings       — internal drift diagnostics
        #   · ai_providers          — provider names, quarantine state, errors
        #   · vton_engine metadata  — engine, weights and license status
        #   · storage internals     — backend, bucket and path configuration
        #   · raw error strings     — see the database check above
        "checks": {
            "database": db_status,
            "schema": public_schema_summary(schema),
            "vton_pipeline": _vton_pipeline_status(),
            # vton_engine stays PUBLIC on purpose. It is not an inventory leak
            # but a disclosure: `backend/tests/test_vton_engine_contract.py`
            # pins that a non-commercial engine can never be presented as
            # commercially deployable by a bare "operational" string. Removing
            # it would trade a real integrity guarantee for a marginal one.
            "vton_engine": vton_engine_metadata(),
            "storage": public_storage_summary(storage_status()),
            "ai_stylist_engine": "operational",
            "bnpl_gateway": "operational",
        },
    }


@router.get("/health/details", include_in_schema=False)
def health_details(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(ADMIN_ROLES)),
):
    """Operator diagnostics. Admin-only.

    Everything the public /health used to disclose, so that tightening the
    public surface costs operators nothing. The raw database error is included
    here because the caller is already an authenticated administrator.
    """
    db_status = "healthy"
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = "unhealthy"
        db_error = f"{type(exc).__name__}: {str(exc)[:500]}"

    from backend.app.providers.orchestrator import get_orchestrator

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": time.time(),
        "version": settings.VERSION,
        "checks": {
            "database": db_status,
            "database_error": db_error,
            "schema": schema,
            "vton_pipeline": _vton_pipeline_diagnostics(),
            "vton_engine": vton_engine_metadata(),
            "storage": storage_status(),
        },
        "ai_providers": get_orchestrator().provider_status(),
    }
