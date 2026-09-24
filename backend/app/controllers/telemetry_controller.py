import os
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.config import settings, vton_engine_metadata
from backend.app.core.database import get_db, engine
from backend.app.core import schema_gate
from backend.app.core.readiness import CONTRACT, liveness_status, summarise_capabilities
from backend.app.core.rate_limit import rate_limit_store_report
from backend.app.services.capability_service import capability_probes
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
    """One-line honest VTON status derived from a LIVE probe (cached).

    History of this field, in production:
      1. "operational" whenever VTON_WORKER_URL was set — a job then failed
         with VTON_AUTH_FAILURE while /health said operational.
      2. "configured: URL + admin token present" — truthful about configuration
         but still wrong about the product: on 2026-09-21 every try-on job
         failed with VTON_WORKER_NOT_READY because the GPU workspace had
         exceeded its spend limit, while /health kept saying "configured".
    Configuration is not availability, so the status is now taken from the
    cached live probe (see ``vton_worker_observability``). The probe never
    blocks: /health serves the last verdict and refreshes in the background.
    """
    from backend.app.services.vton_worker_observability import vton_health_summary

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
        # A missing admin token fails every job with VTON_AUTH_FAILURE no matter
        # how healthy the worker itself is, so say that FIRST.
        return ("misconfigured: VTON_WORKER_URL set but no admin token "
                "(VTON_WORKER_ADMIN_TOKEN) — every job will fail VTON_AUTH_FAILURE")

    summary = vton_health_summary()
    verdict = summary.get("verdict")
    detail = summary.get("detail")
    age = summary.get("probe_age_seconds")
    age_txt = f" (live probe, {age}s ago)" if age is not None else ""
    if verdict == "ready":
        return f"operational: GPU worker reachable and model loaded{age_txt}"
    if verdict == "cold_start":
        return f"degraded: worker reachable but cold/model loading{age_txt}"
    reason = summary.get("reason") or summary.get("error_code") or "unreachable"
    return f"unavailable: {detail} — last probe said: {reason}{age_txt}"


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


def _probe(db: Session):
    """Run the shared checks once, for whichever surface is answering.

    Split out so the public and admin endpoints cannot drift apart in what they
    measure — only in what they are willing to publish.
    """
    db_status = "healthy"
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "unhealthy"
        db_error = f"{type(exc).__name__}: {str(exc)[:160]}"

    # Schema-drift verdict: "healthy" must mean the schema the code expects is
    # really there, not merely that SELECT 1 works.
    try:
        schema = _schema_report()
    except Exception as exc:  # never crash health; report the failure instead
        schema = {"verdict": "unreachable", "acceptable": False, "blocking": False,
                  "findings": [f"{type(exc).__name__}: {str(exc)[:160]}"]}

    # Live GPU-worker verdict (cached, background-refreshed) from PR #142.
    # Machine-readable; the human string lives in checks.vton_pipeline.
    try:
        from backend.app.services.vton_worker_observability import vton_health_summary
        vton_worker = vton_health_summary()
    except Exception as exc:  # never crash health; report the failure instead
        vton_worker = {"verdict": "unknown", "production_ready": False,
                       "detail": f"probe failed: {type(exc).__name__}: {str(exc)[:140]}"}

    database_ok = db_status == "healthy"
    # The AI readiness probe is refreshed HERE, on the operator surface, and
    # never on a consumer read path. `ensure_readiness` is bounded by a total
    # budget, so it cannot become the slowest part of a health check, and it
    # returns the cached verdict when that verdict is still fresh.
    from backend.app.services.ai_readiness import ensure_readiness

    ensure_readiness()
    capabilities = capability_probes(db, database_ok, vton_worker=vton_worker)
    readiness = summarise_capabilities(capabilities)
    status = liveness_status(database_ok, bool(schema.get("acceptable")))
    return {
        "db_status": db_status,
        "db_error": db_error,
        "schema": schema,
        "vton_worker": vton_worker,
        "capabilities": capabilities,
        "readiness": readiness,
        "rate_limit": rate_limit_store_report(),
        "status": status,
    }


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Public liveness + capability readiness. Deliberately minimal (G-08/G-09).

    Two questions, answered separately and never conflated:

    ``status`` — can this process serve traffic? Liveness scope only.
    ``ready``  — can it do everything it advertises? A blocked core capability
                 sets this false and is named, so a broken capability cannot
                 hide behind a green status the way ``storage`` used to.

    What is *not* here, and why: the provider inventory, the storage provider
    and the environment variables that change it, the VTON engine's licence and
    fork provenance, and the schema's missing tables and columns. Publishing
    those to an unauthenticated caller is a reconnaissance summary, not
    observability. Operators get them from ``/health/ready``.

    ``checks.schema.database_revision`` is retained on purpose: the release
    gate reads it to prove production can run the commit being merged, and
    removing it would blind the one check that prevents a schema-drift outage.
    """
    probe = _probe(db)
    schema = probe["schema"]
    readiness = probe["readiness"]
    return {
        "status": probe["status"],
        "ready": readiness["ready"],
        "blocking_capabilities": readiness["blocking_capabilities"],
        "degraded_capabilities": readiness["degraded_capabilities"],
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": settings.VERSION,
        "checks": {
            "database": probe["db_status"],
            "schema": {
                "verdict": schema.get("verdict"),
                "database_revision": schema.get("database_revision"),
                "blocking": bool(schema.get("blocking")),
                "acceptable": bool(schema.get("acceptable")),
            },
        },
        "contract": CONTRACT,
        "detail": "/api/v1/health/ready (admin)",
    }


@router.get("/health/ready", include_in_schema=False)
def health_ready(
    user: User = Depends(require_role(ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Internal readiness diagnostics. Admin-only (G-08).

    Everything the public endpoint withholds: per-capability detail, the
    provider inventory with live quarantine state, storage posture, the
    resolved VTON engine and its licence, and the schema findings. This is the
    endpoint an operator reads during an incident; it is not a public surface.
    """
    probe = _probe(db)
    schema = probe["schema"]
    readiness = probe["readiness"]

    # Real AI provider status: configured keys + live quarantine state, so a
    # billing-exhausted key (e.g. OpenAI 402) is visible instead of silently
    # degrading to fallback.
    from backend.app.providers.orchestrator import get_orchestrator

    return {
        "status": probe["status"],
        "ready": readiness["ready"],
        "blocking_capabilities": readiness["blocking_capabilities"],
        "degraded_capabilities": readiness["degraded_capabilities"],
        "unprobed_capabilities": readiness["unprobed_capabilities"],
        # Where the rate limiter's counters actually live, and therefore what its
        # quota means. Reported on the OPERATOR surface only: which storage backend
        # the API uses is not a shopper's business, and publishing it in the public
        # contract would be topology disclosure with no consumer benefit.
        #
        # MEASURED 2026-09-24, twice wrong before it was right: the first attempt
        # put this value in the _probe() payload (dead data — both health endpoints
        # build their own dicts), and the second landed in the PUBLIC endpoint,
        # because `str.replace(..., 1)` matched the first of two identical returns
        # and the public surface briefly published storage topology. A test in
        # test_rate_limit_store.py now pins both halves (operator has it, public
        # does not) so an edit cannot drift back to either mistake.
        "rate_limit": probe["rate_limit"],
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": settings.VERSION,
        "checks": {
            "database": probe["db_status"],
            "database_error": probe["db_error"],
            "schema": schema,
            "vton_pipeline": _vton_pipeline_status(),
            # Machine-readable live verdict (the string above is for humans).
            "vton_worker": probe["vton_worker"],
            # Resolved production engine + its (honest) license/commercial status.
            # Surfaced so a non-commercial engine is never silently presented as
            # commercially deployable by a "configured"/"operational" string alone.
            "vton_engine": vton_engine_metadata(),
            # Where uploads/labels would be persisted. "local" is development-only
            # and read-only/ephemeral on serverless hosts: upload features answer
            # 501 FEATURE_NOT_CONFIGURED in production until object storage is set.
            "storage": storage_status(),
        },
        "capabilities": readiness["capabilities"],
        "ai_providers": get_orchestrator().provider_status(),
        "contract": CONTRACT,
    }
