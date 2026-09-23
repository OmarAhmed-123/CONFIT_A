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

    # 2026-09-23: the probe now exists, so this no longer has to end at
    # `not_probed`. It reads a CACHED snapshot (ai_readiness never probes on a
    # read path — consumer traffic must not become provider load) and maps the
    # measured verdict onto this project's vocabulary. `not_probed` remains the
    # honest answer before the first probe, after a refresh failure, and once
    # the snapshot passes its hard maximum age — a stale "ready" is not a ready.
    from backend.app.services.ai_readiness import (
        STATE_READY,
        STATE_NOT_CONFIGURED,
        ai_readiness,
    )

    readiness = ai_readiness()
    measured_state = readiness.get("state")

    if measured_state == STATE_READY:
        return Capability(
            "ai_stylist", STATE_READY, CRITICALITY_SUPPORTING,
            "live probe: {} provider(s) answered an authenticated request "
            "({}s old); the deterministic grounded engine remains the fallback".format(
                len(readiness.get("ready_providers") or []),
                readiness.get("probe_age_seconds"),
            ),
        )

    if measured_state == STATE_NOT_CONFIGURED:
        return Capability(
            "ai_stylist", STATE_DEGRADED, CRITICALITY_SUPPORTING,
            "no provider key configured; the deterministic grounded fallback answers",
        )

    if measured_state and measured_state != "not_probed":
        # auth_failed / quota_exhausted / rate_limited / unavailable / timeout:
        # a real measurement of a real failure. The shopper is still served by
        # the grounded fallback, so `degraded` — impaired, not absent.
        return Capability(
            "ai_stylist", STATE_DEGRADED, CRITICALITY_SUPPORTING,
            "live probe: {} ({}) — the deterministic grounded fallback answers".format(
                measured_state, readiness.get("detail"),
            ),
        )

    return Capability(
        "ai_stylist", STATE_NOT_PROBED, CRITICALITY_SUPPORTING,
        "{} provider key(s) configured and no provider is currently quarantined, "
        "but no availability measurement is available — a configured key is not "
        "a measurement".format(len(providers)),
    )


def _ai_provider_keys() -> List[str]:
    """Configured AI provider keys — delegated to the readiness module.

    This function used to hold its own list of settings. That list and the probe's
    list were two statements of the same fact, which is how a flag and the thing
    that measures it start disagreeing. There is now one enumeration
    (``ai_readiness.configured_provider_names``) and this is a thin alias, kept
    because existing tests and callers name it.

    The Groq nuance it used to carry is preserved there: ``groq_api_key`` (the
    property) resolves ``GROQ_API_KEY`` first and ``GROK_API_KEY`` as the
    backwards-compatible alias, and a whitespace-only value counts as unset — so
    a deployment using the documented spelling is not reported as unconfigured.
    """
    from backend.app.services.ai_readiness import configured_provider_names

    return configured_provider_names()


def _bnpl_configured() -> bool:
    """Is the BNPL provider CONFIGURED? (Configuration only — not availability.)

    Kept separate on purpose. ``len(keys) > 0`` and "a shopper can pay in
    instalments" are different facts, and collapsing them is the defect this
    module exists to prevent (see :func:`bnpl_is_live`).
    """
    return bool(settings.PAYMENTS_LIVE and (settings.TABBY_API_KEY or settings.TAMARA_API_KEY))


def ai_stylist_state() -> str:
    """The measured AI Stylist readiness state (see ``services.ai_readiness``).

    One function so the flag, the state field and the health capability cannot
    answer differently — the failure mode this module exists to prevent.

    Returns ``not_configured`` when no key exists, the cached measured verdict
    otherwise. It never probes: consumer traffic must not generate provider
    calls, so before the first probe (or after a refresh failure) the honest
    answer is ``not_probed``, which is why ``ai_stylist_live`` is then False.
    """
    from backend.app.services.ai_readiness import ai_readiness

    return str(ai_readiness().get("state") or "not_probed")


def payment_method_ids() -> List[str]:
    """Every method id the catalogue defines — one list, used by both surfaces.

    The capability flag and `/commerce/payment-methods` must not disagree about
    which methods exist; deriving both from the catalogue keeps a new method
    from being measured by one and forgotten by the other.
    """
    from backend.app.providers.payment.capability_registry import (
        MarketPaymentCapabilityRegistry,
    )

    return list(MarketPaymentCapabilityRegistry.PAYMENT_CATALOG)


def payment_method_is_live(method_id: str) -> bool:
    """Can THIS deployment actually settle a payment with this method?

    Replaces a literal. ``PaymentMethodOption.is_live`` defaulted to ``True`` and
    every entry of ``PAYMENT_CATALOG`` hardcoded ``is_live=True``, so production
    served ``{"id": "bnpl_tabby", "title_en": "Tabby — Split in 4",
    "description_en": "Split in 4 interest-free monthly payments. Sharia
    compliant.", "is_live": true}`` while the same deployment reported
    ``payments_mode=demo``, ``bnpl_live=false`` and had no Tabby key at all.
    "Sharia compliant instalment financing, live" is not a styling choice; it is
    a regulated financial claim, and nothing measured it.

    The rule, one place:

    * ``cod`` — cash on delivery engages no PSP, so it is live wherever offered;
    * otherwise ``PAYMENTS_LIVE`` must be on, a live adapter for the method must
      be *implemented* (``LIVE_PSP_ADAPTERS`` is deliberately empty until an
      integration is verified against the provider's sandbox), and that
      provider's credential must be configured.

    A method that fails this is still *offered* in demo mode — the shopper can
    exercise the flow — but it is labelled not-live, which is the difference
    between a demo and a claim about a lender.
    """
    method = (method_id or "").strip().lower()
    if not method:
        return False
    if method == "cod":
        return True
    if not settings.PAYMENTS_LIVE:
        return False
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    provider_key, adapter = PaymentOrchestrator.live_adapter_for(method)
    if adapter is None or not provider_key:
        return False
    credential = {
        "stripe": settings.STRIPE_SECRET_KEY,
        "tabby": settings.TABBY_API_KEY,
        "tamara": settings.TAMARA_API_KEY,
        "paymob": settings.PAYMOB_API_KEY,
    }.get(provider_key)
    return bool(credential)


def payment_disclaimer(
    country_code: str,
    offered_method_ids: List[str],
    live_method_ids: List[str],
) -> tuple[str, str]:
    """What may honestly be said about payment on THIS deployment, in this market.

    Replaces a literal. ``MarketPaymentCapabilityRegistry`` shipped one sentence
    for every market::

        All transactions in {code} are processed in compliance with local
        central bank regulations and PCI-DSS tokenization standards.

    Measured 2026-09-23: production served that sentence for EG while its own
    ``/commerce/payment-methods`` answered ``is_live=false`` for card, Tabby,
    Vodafone Cash and InstaPay, ``payments_mode=demo``, and no PSP credential
    existed. No card transaction was processed, so no tokenization standard was
    engaged — a compliance claim standing on nothing measured. It was also
    served for markets the platform does not serve at all (``?country_code=XX``
    → "All transactions in XX are processed..."). The project already holds the
    opposite convention: a disclaimer must describe what actually happened
    (see ``test_fit_finder_api.py::test_measurement_disclaimer_matches_the_real_source``).

    So the text is derived from the measurement, not the catalogue:

    * a PSP method is live → the compliance sentence is *earned* and kept;
    * only ``cod`` is live → say so, name it, and claim nothing else;
    * nothing is live in this market → say that instead of implying a rail.

    ``available_methods[].is_live`` and this text therefore read from the same
    two inputs, which is why the orchestrator stamps both.
    """
    code = (country_code or "EG").strip().upper() or "EG"
    offered = {str(m).strip().lower() for m in (offered_method_ids or [])}
    live = {str(m).strip().lower() for m in (live_method_ids or [])} & offered

    if live - {"cod"}:
        return (
            f"All transactions in {code} are processed in compliance with local "
            "central bank regulations and PCI-DSS tokenization standards.",
            f"تتم جميع المعاملات في {code} بما يتوافق مع تعليمات البنوك المركزية "
            "ومعايير التشفير الآمن PCI-DSS.",
        )
    if "cod" in live:
        return (
            f"Card and instalment payments are not enabled on this deployment. "
            f"Cash on delivery is the only live payment method in {code}.",
            f"الدفع بالبطاقة والتقسيط غير مُفعّل على هذا النشر. "
            f"الدفع نقدًا عند الاستلام هو وسيلة الدفع الحيّة الوحيدة في {code}.",
        )
    return (
        f"No payment method is enabled for {code} on this deployment.",
        f"لا توجد وسيلة دفع مُفعّلة في {code} على هذا النشر.",
    )


def bnpl_is_live() -> bool:
    """Can a shopper actually pay in instalments right now?

    Three independent conditions, all required:

    1. ``PAYMENTS_LIVE`` is on;
    2. a Tabby/Tamara key is configured;
    3. a live PSP adapter for that provider is **implemented**.

    The third is the one that was missing everywhere. ``LIVE_PSP_ADAPTERS`` is
    empty by design until an integration is written and verified against the
    provider's sandbox, so "configured" said nothing about whether an
    instalment could be charged. Measured 2026-09-23: production had
    ``bnpl_live=false`` and no provider key at all, while the product page told
    shoppers "4 payments of 72.25 USD with Tabby" — the quote is a local
    calculation (:meth:`BNPLProvider.quote_sync`) with a lender's name attached.

    This is the single authority for that question. The capability flag, the
    capability probe, the product teaser and the cart quote all read it, so the
    four surfaces cannot disagree.
    """
    provider = (settings.BNPL_DEFAULT_PROVIDER or "tabby").lower()
    return payment_method_is_live(f"bnpl_{provider}")


def uploads_ready() -> bool:
    """Can a consumer actually persist a photo right now?

    One derivation for both the shopper-facing flag and the health probe. The
    Wardrobe UI used to read ``storage_mode == "local"`` — the provider's *name*
    — so a deployment configured for s3 with an unreachable bucket offered
    uploads that could only fail, which is the same
    configuration-as-measurement defect in a different costume.
    ``storage_status()`` folds the live put/get/delete probe into
    ``production_grade`` when the probe is enabled, so this is a measurement
    wherever the deployment asks for one.
    """
    storage = storage_status()
    return bool(storage.get("production_grade")) and bool(storage.get("writable", True))


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

    # Measured, not configured. The published flag drove a consumer-visible
    # sentence -- `footer.payment_mode_disclosure`'s sibling
    # "Card payments are processed by a live payment service provider." -- while
    # its value was `bool(settings.PAYMENTS_LIVE)`. One environment variable
    # (`PAYMENTS_LIVE=true`) with no provider key and no live adapter therefore
    # made the trust footer claim a live PSP on a deployment where
    # `payment_method_is_live("card")` is False. Same defect class as the
    # catalogue literal: configuration published as capability.
    #
    # cash on delivery settles without a PSP, so it is excluded from the
    # "live payments" verdict: the sentence above is about a payment service
    # provider, and COD does not involve one. `cod_live` carries that fact
    # separately so the UI can state it truthfully instead of implying either
    # "everything works" or "nothing works".
    live_method_ids = [m for m in payment_method_ids() if payment_method_is_live(m)]
    psp_methods_live = [m for m in live_method_ids if m != "cod"]

    return {
        "payments_live": bool(psp_methods_live),
        "payments_live_methods": live_method_ids,
        "cod_live": "cod" in live_method_ids,
        "payments_mode": "live" if settings.PAYMENTS_LIVE else "demo",
        # Measured: live only when a live PSP adapter for the provider exists.
        "bnpl_live": bnpl_is_live(),
        # Measured: true only for a live `ready` verdict from the GPU worker.
        "vton_gpu_ready": engine_state == ENGINE_STATE_AVAILABLE,
        # Canonical state, identical to /try-on/capabilities `engine_state`.
        "vton_engine_state": engine_state,
        # Whether the deployment offers try-on at all (worker configured).
        # False is "not offered", not an outage — see _vton_capability().
        "vton_offered": bool(settings.VTON_WORKER_URL),
        "vton_renderable": engine_can_render(engine_state),
        # MEASURED (2026-09-23): `ready` only when a probe reached a provider and
        # its credential was accepted. Until now this was
        # `bool(_ai_provider_keys())` — configuration standing in for
        # reachability, one env var away from a claim nothing verified. The
        # configuration fact is still published, under a name that says so.
        "ai_stylist_live": ai_stylist_state() == "ready",
        #: CONFIGURATION: is at least one provider key present? NOT readiness.
        "ai_stylist_configured": bool(_ai_provider_keys()),
        #: The measured state (not_configured / not_probed / ready / degraded /
        #: unavailable / auth_failed / quota_exhausted / rate_limited / timeout).
        "ai_stylist_state": ai_stylist_state(),
        "bopis_live": store_count > 0,
        "bopis_store_count": int(store_count),
        "storage_mode": settings.STORAGE_PROVIDER,
        # Measured (live storage probe when enabled): can a photo be persisted?
        "photo_upload_available": uploads_ready(),
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
    uploads_ok = uploads_ready()
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
            state=(
                STATE_READY
                if bnpl_is_live()
                else STATE_DEGRADED
                if _bnpl_configured()
                else STATE_BLOCKED
            ),
            criticality=CRITICALITY_SUPPORTING,
            detail=(
                "live PSP adapter present, payments live and a provider key configured"
                if bnpl_is_live()
                else (
                    "a provider key is configured and payments are live, but no live "
                    "PSP adapter is implemented for this provider — instalments are an "
                    "estimate and cannot be charged"
                    if _bnpl_configured()
                    else "requires PAYMENTS_LIVE, a Tabby or Tamara key, and a live PSP adapter"
                )
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
