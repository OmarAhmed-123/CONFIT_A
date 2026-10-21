"""Server-side image fetching that cannot be pointed at the cluster's inside.

WHY THIS EXISTS
---------------
The catalogue import fetches a URL that a *brand owner* typed into a CSV and
then hands the bytes to the materialiser. Stock sources (Unsplash, Pexels) are
fixed hosts and were safe by construction, so nothing guarded the request. As
soon as first-party URLs are allowed — a boutique's own CDN, which is the
normal case for a real clothing catalogue — that typed string becomes a
server-side request forgery primitive:

    image_url = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"

would have the API process read cloud metadata credentials and then store them
as a "product image". `http://127.0.0.1:6379/`, `http://10.0.0.5:8080/` and
`http://[::1]/` are the same class of problem against an internal network.

THE RULE
--------
A URL may be fetched only if ALL of these hold:
  * scheme is http or https;
  * it has a host and no embedded credentials (``user:pass@host``);
  * the port is 80/443 (or unset);
  * the host is not a name that resolves to loopback/link-local/private/
    reserved space — checked against *every* address the name resolves to,
    because a split-horizon or attacker-controlled DNS answer can return one
    public and one private record;
  * every redirect hop is re-checked, so a public host cannot bounce us
    inward. Redirects are therefore followed here, one hop at a time, rather
    than by httpx.

A literal IP is checked directly without DNS. IPv4-mapped IPv6
(``::ffff:127.0.0.1``) is unwrapped first — `ipaddress` classifies the wrapper,
not the address inside it, and that is exactly the shape used to slip past a
naive check.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Iterable, List
from urllib.parse import urlsplit, urljoin

ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443, None)
#: Bounded so a redirect loop cannot hang a worker for the whole import.
MAX_REDIRECTS = 3


class UnsafeURLError(ValueError):
    """The URL would fetch from somewhere the API must never reach."""


def _addresses_for(host: str) -> List[ipaddress._BaseAddress]:
    """Every address `host` resolves to, as ipaddress objects.

    A resolution failure is raised as `UnsafeURLError`: "we could not resolve
    it" is not evidence of safety, and treating it as such is how allow-by-
    default bugs get shipped.
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeURLError(f"could not resolve {host!r}: {exc}") from exc

    out: List[ipaddress._BaseAddress] = []
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        # ::ffff:127.0.0.1 -> 127.0.0.1 before we ask what it is.
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        out.append(addr)
    if not out:
        raise UnsafeURLError(f"{host!r} did not resolve to any IP address")
    return out


def _is_public(addr: ipaddress._BaseAddress) -> bool:
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        # `is_private` already covers these on modern CPython; named anyway so
        # the intent survives a stdlib redefinition.
        or getattr(addr, "is_site_local", False)
    )


def assert_public_http_url(url: str) -> str:
    """Return `url` unchanged, or raise `UnsafeURLError` explaining why not."""
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError("empty URL")
    parts = urlsplit(url.strip())

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"scheme {parts.scheme or '(none)'!r} is not allowed; only http and https"
        )
    if parts.username or parts.password:
        raise UnsafeURLError("URL must not embed credentials")
    host = (parts.hostname or "").strip().lower()
    if not host:
        raise UnsafeURLError("URL has no host")
    try:
        port = parts.port
    except ValueError as exc:  # malformed :port
        raise UnsafeURLError(f"invalid port in URL: {exc}") from exc
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"port {port} is not allowed; only 80 and 443")

    # Local names are refused by name as well as by address: a container
    # orchestrator may resolve `redis` or `host.docker.internal` to something
    # that `is_private` reports inconsistently.
    if host in ("localhost",) or host.endswith((".localhost", ".local", ".internal", ".localdomain")):
        raise UnsafeURLError(f"{host!r} is an internal hostname")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        addresses: Iterable[ipaddress._BaseAddress] = _addresses_for(host)
    else:
        if isinstance(literal, ipaddress.IPv6Address) and literal.ipv4_mapped is not None:
            literal = literal.ipv4_mapped
        addresses = [literal]

    for addr in addresses:
        if not _is_public(addr):
            raise UnsafeURLError(
                f"{host!r} resolves to {addr}, which is private/loopback/link-local "
                "and must not be fetched by the server"
            )
    return url.strip()


def safe_get(url: str, *, fetch=None, timeout: float = 30.0,
             max_redirects: int = MAX_REDIRECTS, allow_hop=None) -> bytes:
    """GET `url` with every hop validated. Returns the body bytes.

    `fetch` is the single-hop transport (``fetch(url) -> httpx.Response``-like
    object with ``status_code``, ``headers`` and ``content``); it is injectable
    so the redirect logic can be tested without a network. Without it, httpx is
    used with ``follow_redirects=False`` — the redirects are ours to check.

    `allow_hop` is an optional second, INDEPENDENT gate applied to the first URL
    and to every redirect destination: ``allow_hop(url) -> None`` raising to
    refuse. It exists because network safety and brand ownership are different
    questions, and a redirect is where an ownership check can be walked out of:

        brand's verified CDN  --302-->  attacker's host

    The first URL is authorized; the hop is not. Checking ownership only before
    the fetch would authorize the redirect implicitly. Network safety alone does
    not catch it either — the attacker's host is perfectly public. Both gates
    therefore run on every hop, and neither replaces the other.
    """
    if allow_hop is not None:
        allow_hop(assert_public_http_url(url))
    else:
        assert_public_http_url(url)
    if fetch is None:
        import httpx

        def fetch(u: str):
            return httpx.get(
                u,
                timeout=timeout,
                # Deliberately NOT following redirects inside httpx: a hop that
                # lands on 169.254.169.254 would otherwise be fetched before we
                # could look at it.
                follow_redirects=False,
                headers={"User-Agent": "CONFIT-catalog-materializer/1.0"},
            )

    current = assert_public_http_url(url)
    for _hop in range(max_redirects + 1):
        response = fetch(current)
        status = getattr(response, "status_code", 200)
        if status in (301, 302, 303, 307, 308):
            location = (getattr(response, "headers", {}) or {}).get("location")
            if not location:
                raise UnsafeURLError(f"redirect from {current} without a Location header")
            nxt = urljoin(current, location)
            # Raises before the next request is made — network safety first.
            current = assert_public_http_url(nxt)
            if allow_hop is not None:
                # ...and then ownership, on the DESTINATION.
                allow_hop(current)
            continue
        if status >= 400:
            raise UnsafeURLError(f"image source returned HTTP {status}")
        return getattr(response, "content", b"") or b""
    raise UnsafeURLError(f"too many redirects (>{max_redirects})")
