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
from backend.app.core.readiness import (
    CRITICALITY_CORE,
    CRITICALITY_SUPPORTING,
    STATE_BLOCKED,
    STATE_DEGRADED,
    STATE_READY,
    Capability,
)
from backend.app.models.catalog import StoreLocation
from backend.app.services.storage_service import storage_status

__all__ = ["capability_flags", "capability_probes", "RETURNS_WINDOW_DAYS"]

#: Business rule: the returns window advertised to shoppers. Kept here so the
#: capability surface and the readiness surface cannot disagree about it.
RETURNS_WINDOW_DAYS = 30


def _ai_provider_keys() -> List[str]:
    return [
        k for k in (
            settings.NVIDIA_API_KEY,
            getattr(settings, "GROK_API_KEY", None),
            settings.GEMINI_API_KEY,
            settings.OPENAI_API_KEY,
        ) if k
    ]


def _bnpl_configured() -> bool:
    return bool(settings.PAYMENTS_LIVE and (settings.TABBY_API_KEY or settings.TAMARA_API_KEY))


def capability_flags(db: Session) -> Dict[str, Any]:
    """The ``/capabilities`` payload. Unchanged wire contract."""
    store_count = db.query(StoreLocation).count()
    return {
        "payments_live": bool(settings.PAYMENTS_LIVE),
        "payments_mode": "live" if settings.PAYMENTS_LIVE else "demo",
        "bnpl_live": _bnpl_configured(),
        "vton_gpu_ready": bool(settings.VTON_WORKER_URL),
        "ai_stylist_live": bool(_ai_provider_keys()),
        "bopis_live": store_count > 0,
        "bopis_store_count": int(store_count),
        "storage_mode": settings.STORAGE_PROVIDER,
        "returns_window_days": RETURNS_WINDOW_DAYS,
    }


def capability_probes(db: Session, database_ok: bool) -> List[Capability]:
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

    out.append(
        Capability(
            name="virtual_try_on",
            state=STATE_READY if settings.VTON_WORKER_URL else STATE_BLOCKED,
            criticality=CRITICALITY_CORE,
            detail=(
                "GPU worker URL configured; per-job readiness is checked by the pipeline"
                if settings.VTON_WORKER_URL
                else "no VTON_WORKER_URL configured"
            ),
        )
    )

    providers = _ai_provider_keys()
    out.append(
        Capability(
            name="ai_stylist",
            state=STATE_READY if providers else STATE_DEGRADED,
            criticality=CRITICALITY_SUPPORTING,
            detail=(
                f"{len(providers)} live provider key(s) configured"
                if providers
                else "no provider key configured; the deterministic grounded fallback answers"
            ),
        )
    )

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
