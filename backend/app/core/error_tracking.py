"""Production error tracking (GlitchTip / Sentry-compatible).

WHY THIS EXISTS
---------------
Until now CONFIT_A had **no error tracking at all**. A 500 in production was
discoverable only by a human hitting it — which is literally how the
brand-portal 500 was found on 2026-09-30: by an authorization walk, not by an
alert. The uptime monitor pings `/health` every 15 minutes, and `/health`
answered `200 healthy` throughout, because a handler raising for ONE role is
not a liveness failure.

GlitchTip is chosen over hosted Sentry because it is Sentry-SDK compatible
(no vendor lock-in: change one DSN to move) and has a real free tier
(1,000 events/month). Source: free-for.dev "Crash and Exception Handling".

PRIVACY IS THE HARD CONSTRAINT, NOT AN OPTION
---------------------------------------------
This application stores body measurements, photographs and addresses. An
error tracker that ships request bodies to a third party would export exactly
the data `ENCRYPTION_KEY_FOR_BODY_DATA` exists to protect, and would do it
silently, on every crash, to a server outside the operator's control.

So the defaults here are deliberately stricter than the SDK's:

* ``send_default_pii=False`` — no cookies, no headers, no user IP, no body.
* ``max_request_body_size="never"`` — belt and braces; the SDK must not
  serialise a request body even if a future SDK version changes the default.
* ``before_send`` scrubs any surviving key whose NAME looks like a secret or
  like body data, at every nesting level, before the event leaves the process.
  Name-based scrubbing is a last line of defence, not the first — the first is
  simply not collecting it.

It is fail-open by construction: a missing DSN disables tracking silently
(local dev and CI must not need a DSN), and an SDK that will not initialise
must never prevent the API from booting. Telemetry that can take the product
down is worse than no telemetry.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger

#: Redaction marker. Distinct from the SDK's own so it is obvious in GlitchTip
#: that CONFIT scrubbed the value, not the vendor.
REDACTED = "[confit-redacted]"

#: Key names whose VALUE must never leave the process. Matched
#: case-insensitively as substrings, so `SMTP_PASSWORD`, `hashed_password` and
#: `x-csrf-token` are all covered by three entries.
_SENSITIVE_NAME = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|apikey|authorization|auth|"
    r"cookie|session|credential|private|signature|hmac|dsn|"
    # Domain-specific: the measurements and imagery this product is trusted with.
    r"measurement|body_|bust|waist|hip|inseam|chest|shoulder|height_cm|weight_kg|"
    r"photo|image_base64|image_data|avatar|"
    # Direct identifiers.
    r"email|phone|address|full_name|recipient_name|card|iban|cvv)",
    re.IGNORECASE,
)

#: Guard against pathological structures — a deeply nested payload could make
#: scrubbing itself the slow part of an error path.
_MAX_DEPTH = 12


def _scrub(value: Any, depth: int = 0) -> Any:
    """Recursively redact values whose KEY name looks sensitive."""
    if depth > _MAX_DEPTH:
        return REDACTED
    if isinstance(value, dict):
        out: Dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_NAME.search(key):
                out[key] = REDACTED
            else:
                out[key] = _scrub(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub(item, depth + 1) for item in value]
        return type(value)(scrubbed) if isinstance(value, tuple) else scrubbed
    return value


def _before_send(event: Dict[str, Any], hint: Any) -> Optional[Dict[str, Any]]:
    """Last line of defence before an event leaves this process.

    Never raises: an exception here would be thrown while the SDK is already
    handling an exception, and would lose the original error.
    """
    try:
        event = _scrub(event)
        # The SDK attaches a `user` context from the auth integration. Keep the
        # id (needed to correlate an incident with a support ticket) and drop
        # everything else — id alone is meaningless without database access.
        user = event.get("user")
        if isinstance(user, dict):
            event["user"] = {"id": user.get("id")} if user.get("id") else {}
        # Query strings can carry a reset token or a currency the shopper
        # picked; the path alone is enough to locate the handler.
        request = event.get("request")
        if isinstance(request, dict):
            request.pop("query_string", None)
            request.pop("data", None)
            request.pop("cookies", None)
            request.pop("headers", None)
        return event
    except Exception:  # noqa: BLE001 - scrubbing must never lose the error
        # If scrubbing failed we cannot prove the event is clean, so drop it.
        # Losing one report beats leaking a measurement.
        return None


def is_configured() -> bool:
    return bool((getattr(settings, "GLITCHTIP_DSN", "") or "").strip())


def init_error_tracking() -> bool:
    """Initialise the tracker. Returns True when it is actually active.

    Called once at import time from ``main.py``. Fail-open: any problem is
    logged and swallowed, because an observability dependency must never be
    able to stop the API from serving traffic.
    """
    dsn = (getattr(settings, "GLITCHTIP_DSN", "") or "").strip()
    if not dsn:
        logger.info("error_tracking_disabled", reason="GLITCHTIP_DSN not set")
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("error_tracking_sdk_missing", action_required="pip install sentry-sdk")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=(getattr(settings, "ENVIRONMENT", "") or "unknown"),
            release=f"confit@{getattr(settings, 'VERSION', '0')}",
            # 1% of transactions. Each HTTP request is a transaction, and the
            # free tier is 1,000 EVENTS/month — a higher rate would spend the
            # whole budget on performance traces and drop real errors.
            traces_sample_rate=0.01,
            # Errors are the point; never sample them away.
            sample_rate=1.0,
            # GlitchTip does not implement release health sessions.
            auto_session_tracking=False,
            # PRIVACY: see the module docstring. These two are the difference
            # between "we monitor errors" and "we exported body measurements".
            send_default_pii=False,
            max_request_body_size="never",
            before_send=_before_send,
        )
    except Exception as exc:  # noqa: BLE001 - telemetry must never break boot
        logger.error("error_tracking_init_failed", error=f"{type(exc).__name__}: {exc}"[:200])
        return False

    logger.info("error_tracking_enabled", provider="glitchtip",
                environment=getattr(settings, "ENVIRONMENT", "unknown"))
    return True
