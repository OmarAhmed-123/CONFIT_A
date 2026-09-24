"""Shared rate limiter (slowapi) — cost control and brute-force control.

Why it exists: ``/try-on/*`` triggers real GPU spend per call once the worker is
deployed, ``/auth/*`` is the brute-force surface, and (added 2026-09-23)
``/stylist/chat`` spends provider quota per call while ``/wardrobe/upload``
writes to object storage and runs a vision model. A limit that exists only on
the cheap endpoints is not cost control.

Honest scope of the control
---------------------------
Where the counters live is now a **configured decision with a reported answer**,
not a silent property:

* ``RATE_LIMIT_STORAGE_URL`` unset (the state of this deployment, and the
  default) -> the in-process store. On serverless each warm instance keeps its
  own counters, so the limiter bounds *per-client bursts against one instance*
  and is **not** a global quota. ``rate_limit_store_report()`` says exactly that
  and ``/health`` publishes it, so nobody has to read this docstring to find out
  which of the two they are running.
* set to a real ``redis://`` / ``rediss://`` endpoint -> counters are shared by
  every instance, and the report says the quota is global.

Degradation is explicit rather than fatal: when a shared store is configured but
unreachable, the limiter falls back to the in-process store (``swallow_errors``
+ ``in_memory_fallback``) so a store outage cannot turn every request into a 500,
and the fallback is named in the report. Falling back silently would be the fake
version of this feature; falling back loudly is the honest one.

The algorithm is intentionally unchanged: slowapi's default fixed window, with
the 429 envelope and ``Retry-After`` behaviour this project already tests.
Sliding-window and token-bucket were considered and rejected for THIS change
because the defect being closed is *where the counter lives*, not how it decays
— swapping the algorithm at the same time would make the regression evidence
ambiguous. See the report for the comparison.

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
import time
from typing import Any, Dict, Optional

from backend.app.core.config import settings

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded


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


# ``headers_enabled`` is deliberately left OFF, and that is a measured decision.
#
# Setting it True makes slowapi's per-endpoint wrapper call
# ``_inject_headers(kwargs["response"], …)``. Endpoints that do not declare a
# ``response: Response`` parameter — which is most of this codebase's routes, since
# services return dicts — pass ``None`` and slowapi raises
# "parameter `response` must be an instance of starlette.responses.Response".
# DEFECT I INTRODUCED AND THEN MEASURED (2026-09-23): with the flag on,
# ``GET /orders/CONF-436F4425`` (a guest order that must stay readable anonymously)
# returned 500 while the identical call returned 200 with the flag off. The flag is
# therefore not usable here.
#
# The Retry-After / X-RateLimit contract is instead served by
# ``rate_limit_exceeded_handler`` below, which builds the 429 itself and has no
# ``response`` parameter constraint.
# ``key_style="endpoint"`` — measured, not stylistic.
#
# slowapi buckets a limit by ``endpoint_url if self._key_style == "url" else
# endpoint_func_name`` (slowapi/extension.py, ``_check_request_limit``), and ``url``
# is the default. This API mounts the same router under several prefixes and
# registers most consumer routes under two spellings (``/orders/{n}`` and
# ``/commerce/orders/{n}``, ``/cart`` and ``/commerce/cart``, and so on), so a
# URL-keyed bucket hands the caller one allowance PER SPELLING.
#
# MEASURED 2026-09-23 against production (``confit-a.vercel.app``), same client
# identity, same minute, on the order-lookup limit that exists to bound
# enumeration of order numbers:
#
#     /api/v1/orders/CONF-00000000          30 × 404, then 429   (bucket exhausted)
#     /api/v1/commerce/orders/CONF-00000000 -> 404  PROCESSED    (separate bucket)
#
# and locally, where every prefix is served:
#
#     /v1/orders/…  -> 404 PROCESSED     /orders/…  -> 404 PROCESSED
#
# i.e. the intended 30/minute was really 2× (production spellings) to 6× (all
# prefixes served). Keying by the endpoint function makes every spelling of one
# logical route share a single allowance, which is what the limit always claimed
# to be. Views of a *different* resource (detail vs tracking) keep their own
# bucket, because they are different endpoints reached at different cost.
MEMORY_STORE = "memory://"
SHARED_STORE_SCHEMES = ("redis://", "rediss://", "unix://", "memcached://", "mongodb://")


def configured_storage_uri() -> str:
    """The store this deployment is configured to use. Never synthesised.

    Unset/blank -> ``memory://`` (the in-process store). A value that is not a
    recognised shared scheme is honoured verbatim by ``limits`` and reported as
    an unknown store rather than being quietly rewritten into something that
    looks global.
    """
    raw = getattr(settings, "RATE_LIMIT_STORAGE_URL", None)
    uri = (raw or "").strip()
    return uri or MEMORY_STORE


def is_shared_store(uri: str) -> bool:
    return any(uri.startswith(scheme) for scheme in SHARED_STORE_SCHEMES)


def build_limiter(storage_uri: Optional[str] = None, key_func: Optional[Any] = None) -> Limiter:
    """Construct a limiter against an explicit store.

    A factory rather than a literal so tests can build one against a real Redis
    (or against a store that is down) without touching the module-level
    ``limiter`` the application uses.
    """
    uri = storage_uri.strip() if isinstance(storage_uri, str) and storage_uri.strip() else (
        storage_uri if storage_uri is None else MEMORY_STORE
    )
    uri = uri or configured_storage_uri()
    kwargs: Dict[str, Any] = {}
    if is_shared_store(uri):
        # A store outage must not become an outage of the API: fall back to the
        # in-process counters and report the degradation (see the module docstring).
        #
        # MEASURED 2026-09-24 while building this: `in_memory_fallback` takes
        # LIMIT STRINGS, not a storage URI. Passing `["memory://"]` (the first
        # version of this code) made slowapi parse "memory://" as a limit and
        # raise ValueError inside the request path — the fallback then 500'd the
        # API it was there to protect. `in_memory_fallback_enabled` is the switch;
        # the list is for *changing* the limits while degraded, which this project
        # does not want: the same limits must apply in both states, or a client
        # could lift its own quota by breaking the store.
        kwargs = {
            "swallow_errors": True,
            "in_memory_fallback_enabled": True,
        }
    return Limiter(
        key_func=key_func or client_key,
        key_style="endpoint",
        storage_uri=uri,
        **kwargs,
    )


def rate_limit_store_report(storage_uri: Optional[str] = None) -> Dict[str, Any]:
    """What the limiter's counters actually are, in words that cannot overclaim.

    Read by ``/health`` (the operator surface). It deliberately does NOT appear in
    the public capability contract: which storage backend an app uses is not a
    shopper's business, and publishing it would be topology disclosure for no
    consumer benefit.
    """
    uri = storage_uri if storage_uri is not None else configured_storage_uri()
    shared = is_shared_store(uri)
    if shared:
        scheme = uri.split("://", 1)[0]
        return {
            "store": scheme,
            "shared_across_instances": True,
            "quota_semantics": "global: every instance counts against one quota",
            "on_store_failure": "degrades to in-process counters (per-instance) and reports it",
        }
    return {
        "store": "memory" if uri == MEMORY_STORE else uri.split("://", 1)[0],
        "shared_across_instances": False,
        "quota_semantics": (
            "per-instance: bounds a client's burst against one warm instance; "
            "it is NOT a global quota"
        ),
        "on_store_failure": None,
    }


limiter = build_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """429 in this project's error envelope, carrying ``Retry-After``.

    Two contract points, both measured:

    1. **Shape.** slowapi's stock handler returns ``{"error": "Rate limit exceeded: …"}``,
       a bare string where every other error path in this API returns
       ``{"error": {"code", "message", "details"}}``. A client cannot branch on a
       machine code it is not given, so the 429 is expressed in the same envelope as
       the rest of the API with the stable code ``RATE_LIMITED``.
    2. **Back-off information.** The stock handler injected headers only when the
       limiter was constructed with ``headers_enabled=True`` (unusable here, see the
       note on ``limiter`` above), so a throttled caller received a 429 with no hint
       of when to retry — measured 2026-09-23: 30 requests passed, the next ones
       returned 429 with an empty ``Retry-After``. RFC 6585 defines ``Retry-After``
       for 429 precisely so clients back off instead of retrying immediately.

    The retry delay comes from the limiter's own window statistics, so it reflects
    the real window rather than a hardcoded guess. If the storage cannot be read the
    header is omitted and ``details.retry_after_seconds`` is absent — an absent
    header is honest; a fabricated one is not.
    """
    retry_after: Optional[int] = None
    window = getattr(request.state, "view_rate_limit", None)
    if window:
        try:
            reset_epoch = limiter.limiter.get_window_stats(window[0], *window[1])[0]
            retry_after = max(1, int(1 + reset_epoch - time.time()))
        except Exception:  # storage unreachable — omit rather than invent
            retry_after = None

    details: Dict[str, Any] = {"limit": str(exc.detail)}
    if retry_after is not None:
        details["retry_after_seconds"] = retry_after

    response = JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests. Please retry after the indicated delay.",
                "details": details,
            }
        },
    )
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    return response
