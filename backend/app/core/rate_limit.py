"""Shared rate limiter (slowapi) — cost control and brute-force control.

Why it exists: ``/try-on/*`` triggers real GPU spend per call once the worker is
deployed, ``/auth/*`` is the brute-force surface, and (added 2026-09-23)
``/stylist/chat`` spends provider quota per call while ``/wardrobe/upload``
writes to object storage and runs a vision model. A limit that exists only on
the cheap endpoints is not cost control.

Honest scope of the control
---------------------------
``Limiter`` is constructed **without a storage URI**, so counters live in the
process. On a single long-lived server that is per-deployment; on serverless
(Vercel) each warm instance keeps its own counters, so this bounds *per-client
bursts against one instance* — it is not a global quota. Closing that gap needs
a shared counter store (e.g. Redis), which this deployment does not have; that
is recorded as a limitation (report §K), not papered over.

Keying
------
``client_key`` identifies the caller as precisely as the request allows, and
never more: an authenticated token or guest session token (hashed, so no secret
is stored as a key) when present, otherwise the client IP. IP-only keying is
wrong behind a proxy — every shopper can share one bucket — and token-only keying
would let anonymous traffic through unmetered, so both are used with the
credential taking precedence.
"""

import hashlib
from typing import Optional

from fastapi import Request
from slowapi import Limiter


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        value = header[7:].strip()
        if value:
            return value
    return None


def _session_token(request: Request) -> Optional[str]:
    """The guest session token the store already uses for carts.

    Read from the header first (the API's documented transport) and the cookie
    second (what the browser sends), so a guest is metered as one caller instead
    of as whatever IP their network happens to share.
    """
    for header_name in ("x-session-token", "x-guest-token"):
        value = (request.headers.get(header_name) or "").strip()
        if value:
            return value
    for cookie_name in ("confit_session", "confit_guest_token", "session_token"):
        value = (request.cookies.get(cookie_name) or "").strip()
        if value:
            return value
    return None


def _client_ip(request: Request) -> str:
    """The client address, preferring proxy-set headers.

    ``x-real-ip`` is set by the platform's edge; ``x-forwarded-for`` is the
    standard fallback (first hop = original client). When neither is present the
    socket address is used. Whichever is chosen *is* the bucket identity, so the
    choice is stated here rather than buried in a decorator.
    """
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def client_key(request: Request) -> str:
    """Stable bucket identity: credential first, network address second.

    The token is hashed: the key must never be a value that could be replayed
    from a log or a metrics dump.
    """
    credential = _bearer_token(request) or _session_token(request)
    if credential:
        digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()[:32]
        return f"tok:{digest}"
    return f"ip:{_client_ip(request)}"


limiter = Limiter(key_func=client_key)
