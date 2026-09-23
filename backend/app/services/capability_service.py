"""One source of truth for "what can this deployment actually do?".

``GET /capabilities`` already derived its flags from live configuration. The
public ``/health`` endpoint, answering the same question for a different
audience, instead hardcoded two of them:

    "ai_stylist_engine": "operational",
    "bnpl_gateway": "operational"

Those strings were literals. No probe stood behind either one; they reported
"operational" on a deployment where BNPL had no PSP key and would report it
just as cheerfully if every AI provider key were revoked. A health endpoint
asserting a value it never measured is worse than one that says it does not
know, so both now come from here.

This module is the single place that turns configuration and probe results into
capability verdicts. ``/capabilities`` keeps its existing wire contract;
``/health`` and ``/health/ready`` consume :func:`capability_probes` and reduce
it with :mod:`backend.app.core.readiness`. Adding a capability means adding it
here once, and both surfaces report it.
"""

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.readiness import (
    CRITICALITY_CORE,
    CRITICALITY_SUPPORTING,
    STATE_BLOCKED,
    STATE_DEGRADED,
    STATE_NOT_PROBED,
    STATE_READY,
    Capability,
)
from backend.app.models.catalog import StoreLocation
from backend.app.services import vton_worker_observability as vton_observability
from backend.app.services.storage_service import storage_status
from backend.app.services.vton_worker_observability import (
    ENGINE_STATE_AVAILABLE,
    ENGINE_STATE_COLD_START,
    engine_can_render,
    engine_state_from_probe,
)

__all__ = ["capability_flags", "capability_probes", "RETURNS_WINDOW_DAYS"]

#: Business rule: the returns window advertised to shoppers. Kept here so the
#: capability surface and the readiness surface cannot disagree about it.
RETURNS_WINDOW_DAYS = 30


def _ai_quarantine_state() -> "tuple[Dict[str, Any], Dict[str, Any]]":
    """(configured, quarantined) provider maps from the live orchestrator.

    Split out as its own function for two reasons: it is the one place this
    module reads runtime state instead of configuration, and it lets tests pin
    the measurement deterministically instead of depending on whether some
    earlier request happened to trip a cooldown.

    Returns empty maps on any failure. A failure to *read* availability is not
    evidence of availability, so the caller falls through to ``not_probed`` —
    which is what "we could not establish it" honestly is. Nothing here raises:
    an observability helper that can take down /health is worse than none.
    """
    configured: Dict[str, Any] = {}
    quarantined: Dict[str, Any] = {}
    try:
        from backend.app.providers.orchestrator import get_orchestrator

        for name, entry in (get_orchestrator().provider_status() or {}).items():
            if not isinstance(entry, dict):
                continue
            if entry.get("configured"):
                configured[name] = entry
            # A quarantine record is NOT gated on the current `configured` flag:
            # the entry only exists because a provider was actually called and
            # actually failed. Dropping it when the flag disagrees discarded the
            # only real measurement this function has. (When the last key is
            # removed the caller returns earlier, so a stale quarantine for a
            # no-longer-configured provider cannot surface as a false outage.)
            if float(entry.get("cooling_for_seconds") or 0) > 0:
                quarantined[name] = entry
    except Exception as exc:
        logger.warning("ai_stylist_quarantine_read_failed", error=str(exc))
        return {}, {}
    return configured, quarantined


def _ai_stylist_capability() -> Capability:
    """AI Stylist availability — measured where measurable, honest where not.

    ``ready`` means "probed and working" in this project's own vocabulary
    (``backend/app/core/readiness``). Until 2026-09-22 this capability was
    reported ``ready`` whenever a provider key existed:

        state=STATE_READY if providers else STATE_DEGRADED,
        detail=f"{len(providers)} live provider key(s) configured"

    A key is not a measurement, and the detail string said "live" about a value
    nobody had contacted. That is the same configuration-as-measurement defect
    as ``vton_gpu_ready``, on the same payload — it happened to fail quietly
    rather than loudly, which does not make it less wrong.

    What CAN be measured is the shared orchestrator's live quarantine registry:
    a provider is quarantined only after it actually failed (HTTP 402/429/auth),
    so "every configured provider is quarantined" is a real observation that the
    live path is down right now. That yields ``degraded`` — working, on the
    deterministic grounded fallback.

    With providers configured and none quarantined, the honest state is
    ``not_probed``: no availability probe exists, and the absence of a recorded
    failure is not evidence of success. It is a **supporting** capability, so
    ``not_probed`` does not set the platform unready; it names an honest gap
    instead of asserting a value nobody checked.
    """
    providers = _ai_provider_keys()
    if not providers:
        return Capability(
            "ai_stylist", STATE_DEGRADED, CRITICALITY_SUPPORTING,
            "no provider key configured; the deterministic grounded fallback answers",
        )

    configured, quarantined = _ai_quarantine_state()

    # A quarantine entry exists only after a provider really failed, so the
    # quarantine count is the measured half of this decision — and it must drive
    # the verdict on its own when the configuration registry disagrees with the
    # key list. Keying the decision off `configured` alone silently discarded
    # the measurement in exactly that disagreement case.
    if quarantined and len(quarantined) >= len(configured):
        return Capability(
            "ai_stylist", STATE_DEGRADED, CRITICALITY_SUPPORTING,
            "all {} known live provider(s) are quarantined after real failures "
            "({}); the deterministic grounded fallback answers".format(
                len(quarantined), ", ".join(sorted(quarantined))
            ),
        )

    if quarantined:
        return Capability(
            "ai_stylist", STATE_DEGRADED, CRITICALITY_SUPPORTING,
            "{}/{} live provider(s) quarantined after real failures ({}); the "
            "remaining provider(s) still answer, with the deterministic grounded "
            "fallback behind them".format(
                len(quarantined), len(configured) or len(quarantined),
                ", ".join(sorted(quarantined)),
            ),
        )

    return Capability(
        "ai_stylist", STATE_NOT_PROBED, CRITICALITY_SUPPORTING,
        "{} provider key(s) configured and no provider is currently quarantined, "
        "but no availability probe exists — a configured key is not a measurement".format(
            len(providers)
        ),
    )


def _ai_provider_keys() -> List[str]:
    """Configured AI provider keys, read through the canonical accessors.

    ``groq_api_key`` (the property) is used for the Groq slot, NOT the
    ``GROK_API_KEY`` field. The field is a backwards-compatible alias only:
    ``docs/PRODUCTION_DEPLOYMENT_CONTRACT.md`` documents ``GROQ_API_KEY`` (Groq,
    api.groq.com — a different vendor from xAI's Grok), and
    ``MultiProviderAIOrchestrator`` already resolves both through the property.

    Reading the field directly made the capability contract disagree with the
    orchestrator about reality, and it failed in the *silent* direction: measured
    on 2026-09-22, a deployment configured with the documented ``GROQ_API_KEY``
    reported ``ai_stylist_live: false`` while ``settings.groq_api_key`` resolved
    to a real key and the orchestrator was genuinely calling Groq. Under-claiming
    a working capability is the same class of defect as over-claiming a broken
    one — the contract simply was not reading what the system actually uses.
    """
    return [
        k for k in (
            settings.NVIDIA_API_KEY,
            settings.groq_api_key,
            settings.GEMINI_API_KEY,
            settings.OPENAI_API_KEY,
        ) if k
    ]


def _bnpl_configured() -> bool:
    return bool(settings.PAYMENTS_LIVE and (settings.TABBY_API_KEY or settings.TAMARA_API_KEY))


def _vton_capability(vton_worker: Dict[str, Any] | None) -> Capability:
    """Try-on availability from the LIVE worker probe, not from configuration.

    Two distinctions matter and are easy to collapse:

    *Configuration is not availability.* PR #142 established this the hard way:
    ``VTON_WORKER_URL`` was set and every job still failed, first with
    VTON_AUTH_FAILURE and then VTON_WORKER_NOT_READY when the GPU workspace ran
    out of spend, while health reported "configured". So the verdict comes from
    the cached live probe.

    *Not offered is not broken.* A deployment with no worker configured at all
    — development, CI, a non-try-on host — does not have an outage; it simply
    does not offer the feature. Marking that ``blocked`` would leave every
    development environment permanently unready and teach people to ignore the
    field. In production, though, try-on is part of the product, so an absent
    worker there IS a blocked core capability.
    """
    configured = bool(settings.VTON_WORKER_URL)
    probe = vton_worker or {}
    verdict = probe.get("verdict")

    if not configured:
        if settings.is_production:
            return Capability(
                "virtual_try_on", STATE_BLOCKED, CRITICALITY_CORE,
                "production deployment with no VTON_WORKER_URL configured",
            )
        return Capability(
            "virtual_try_on", STATE_DEGRADED, CRITICALITY_SUPPORTING,
            "not offered on this deployment (no VTON_WORKER_URL); not an outage",
        )

    # The state comes from the shared classifier, not from a second private
    # derivation of the same fact (2026-09-22 consumer-role closure).
    engine_state = engine_state_from_probe(probe, configured=configured)
    if engine_state == ENGINE_STATE_AVAILABLE:
        return Capability(
            "virtual_try_on", STATE_READY, CRITICALITY_CORE,
            f"GPU worker reachable and model loaded (probe: {verdict})",
        )
    if engine_state == ENGINE_STATE_COLD_START:
        return Capability(
            "virtual_try_on", STATE_DEGRADED, CRITICALITY_CORE,
            "worker reachable but cold or still loading the model",
        )
    code = probe.get("error_code") or "VTON_ENGINE_UNAVAILABLE"
    reason = probe.get("reason") or probe.get("detail") or "no detail from the probe"
    return Capability(
        "virtual_try_on", STATE_BLOCKED, CRITICALITY_CORE,
        f"worker configured but cannot serve jobs: {code} — {reason}",
    )


def capability_flags(
    db: Session, vton_worker: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """The ``/capabilities`` payload.

    ``vton_gpu_ready`` is MEASURED, not configured
    ---------------------------------------------
    Until 2026-09-22 this function answered ``bool(settings.VTON_WORKER_URL)``
    under the comment "Unchanged wire contract" — while the very same file,
    eighty lines below, carefully derived the identical fact from the live probe
    and explained at length why configuration is not availability. The result
    was served to production consumers:

        GET /api/v1/catalog/capabilities -> "vton_gpu_ready": true
        GET /api/v1/try-on/capabilities  -> "engine_state":
                                            "temporarily_unavailable"

    Both endpoints climbed through ``capability_service``; only one of them
    asked the worker. The frontend binds its commerce/trust claims to *this*
    payload (``useCapabilities``), so the one surface that drives user-visible
    promises was the one that lied — the exact failure mode the module docstring
    above condemns.

    The derivation now lives in one place (``engine_state_from_probe``) and both
    surfaces call it, so they cannot answer differently again.

    Wire contract: the nine original keys keep their names and types.
    ``vton_gpu_ready`` keeps its meaning (true only when try-on can really
    render now) and simply stops being a lie. Two keys are added so the UI can
    tell "we do not offer this here" apart from "this is broken right now"
    without parsing English prose out of ``engine.detail``.
    """
    store_count = db.query(StoreLocation).count()
    probe = (
        vton_worker
        if vton_worker is not None
        else vton_observability.vton_health_summary()
    )
    engine_state = engine_state_from_probe(probe)
    return {
        "payments_live": bool(settings.PAYMENTS_LIVE),
        "payments_mode": "live" if settings.PAYMENTS_LIVE else "demo",
        "bnpl_live": _bnpl_configured(),
        # Measured: true only for a live `ready` verdict from the GPU worker.
        "vton_gpu_ready": engine_state == ENGINE_STATE_AVAILABLE,
        # Canonical state, identical to /try-on/capabilities `engine_state`.
        "vton_engine_state": engine_state,
        # Whether the deployment offers try-on at all (worker configured).
        # False is "not offered", not an outage — see _vton_capability().
        "vton_offered": bool(settings.VTON_WORKER_URL),
        "vton_renderable": engine_can_render(engine_state),
        "ai_stylist_live": bool(_ai_provider_keys()),
        "bopis_live": store_count > 0,
        "bopis_store_count": int(store_count),
        "storage_mode": settings.STORAGE_PROVIDER,
        "returns_window_days": RETURNS_WINDOW_DAYS,
    }



def capability_probes(
    db: Session, database_ok: bool, vton_worker: Dict[str, Any] | None = None
) -> List[Capability]:
    """Probe every advertised capability. No invented verdicts.

    Each entry states what was actually measured. Where the platform has a
    designed fallback the state is ``degraded`` rather than ``blocked`` — a
    feature answering from a deterministic fallback is impaired, not absent,
    and calling it absent would be as dishonest as calling it operational.
    """
    out: List[Capability] = []

    out.append(
        Capability(
            name="database",
            state=STATE_READY if database_ok else STATE_BLOCKED,
            criticality=CRITICALITY_CORE,
            detail="SELECT 1 round trip" if database_ok else "the database did not answer SELECT 1",
        )
    )

    storage = storage_status()
    uploads_ok = bool(storage.get("production_grade")) and bool(storage.get("writable", True))
    out.append(
        Capability(
            name="file_uploads",
            state=STATE_READY if uploads_ok else STATE_BLOCKED,
            criticality=CRITICALITY_CORE,
            detail=(
                "durable object storage"
                if uploads_ok
                else (
                    f"provider={storage.get('provider')} is not production grade or not "
                    "writable; catalogue images, try-on inputs and return labels cannot be "
                    "persisted"
                )
            ),
        )
    )

    out.append(
        Capability(
            name="payments",
            state=STATE_READY if settings.PAYMENTS_LIVE else STATE_DEGRADED,
            criticality=CRITICALITY_CORE,
            detail=(
                "live capture via the signed provider webhook"
                if settings.PAYMENTS_LIVE
                else "demo mode: capture is an explicit admin action, no live settlement"
            ),
        )
    )

    out.append(_vton_capability(vton_worker))

    out.append(_ai_stylist_capability())

    out.append(
        Capability(
            name="buy_now_pay_later",
            state=STATE_READY if _bnpl_configured() else STATE_BLOCKED,
            criticality=CRITICALITY_SUPPORTING,
            detail=(
                "PSP key present and payments live"
                if _bnpl_configured()
                else "requires PAYMENTS_LIVE plus a Tabby or Tamara key"
            ),
        )
    )

    store_count = db.query(StoreLocation).count()
    out.append(
        Capability(
            name="click_and_collect",
            state=STATE_READY if store_count > 0 else STATE_BLOCKED,
            criticality=CRITICALITY_SUPPORTING,
            detail=(
                f"{store_count} store location(s) in the catalogue"
                if store_count
                else "no store locations exist, so BOPIS cannot be offered"
            ),
        )
    )

    return out
