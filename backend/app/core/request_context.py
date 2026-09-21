"""Request-scoped correlation helpers, shared by every controller.

Two facts were previously re-implemented (badly) per controller:

* ``auth_controller._client_ip`` returned ``request.client.host`` — on Vercel
  that is the platform edge, not the shopper. Every audit row written by the
  auth flow therefore recorded the same handful of proxy addresses (G-05).
* ``admin_controller._request_id`` re-derived the correlation id inline.

Both live here now so the audit trail records the same notion of "who, from
where, in which request" no matter which controller wrote the row.

Header trust
------------
``X-Forwarded-For`` is *appended* by each hop, so its left-most entry is
client-supplied and spoofable, while the entry the trusted edge appended is
not. ``X-Real-IP`` is set outright by the edge. We therefore prefer
``X-Real-IP``, then the *right-most* ``X-Forwarded-For`` entry (the one the
platform added), and only then the socket peer. The value is validated so a
junk header can never land in the audit table.
"""

from __future__ import annotations

import ipaddress
from typing import Optional

from fastapi import Request

MAX_IP_LEN = 45  # longest textual IPv6 form


def _valid_ip(candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return None
    candidate = candidate.strip()
    if not candidate or len(candidate) > MAX_IP_LEN:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def client_ip(request: Request) -> Optional[str]:
    """Best-available client address, most-trusted source first."""
    direct = _valid_ip(request.headers.get("x-real-ip"))
    if direct:
        return direct

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Right-most entry is the one appended by the nearest trusted hop.
        for hop in reversed([part.strip() for part in forwarded.split(",") if part.strip()]):
            ip = _valid_ip(hop)
            if ip:
                return ip

    return _valid_ip(request.client.host if request.client else None)


def user_agent(request: Request, limit: int = 500) -> Optional[str]:
    value = request.headers.get("user-agent")
    return value[:limit] if value else None


def request_id(request: Request) -> str:
    """Correlation id set by ``main.request_id_guard``; "" when absent."""
    return getattr(request.state, "request_id", "") or ""
