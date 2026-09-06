"""Feature 01 (security foundation): deployment security-headers contract.

vercel.json applies these headers to every route (SPA + /api functions).
This test pins the contract so a refactor cannot silently drop a header
(the exact failure mode found in production on 2026-09-06: only HSTS was
set; X-Content-Type-Options / X-Frame-Options / CSP / Referrer-Policy /
Permissions-Policy were all absent).
"""

import json
from pathlib import Path

import pytest

VERCEL_JSON = Path(__file__).resolve().parents[2] / "vercel.json"

REQUIRED_HEADERS = {
    "Strict-Transport-Security": None,  # kept by Vercel edge by default; not in our block
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _global_headers() -> dict:
    cfg = json.loads(VERCEL_JSON.read_text())
    headers = {}
    for rule in cfg.get("headers", []):
        if rule.get("source") == "/(.*)":
            for h in rule.get("headers", []):
                headers[h["key"]] = h["value"]
    return headers


def test_global_security_headers_present():
    headers = _global_headers()
    for key, expected in REQUIRED_HEADERS.items():
        if expected is None:
            continue
        assert headers.get(key) == expected, f"missing/wrong {key}"


def test_csp_contract():
    csp = _global_headers().get("Content-Security-Policy", "")
    # hard requirements
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    # product-critical allowances (dropping these breaks catalog images / fonts)
    assert "https://images.unsplash.com" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert "blob:" in csp  # client-side try-on canvas previews
    # scripts must never be inline
    assert "script-src 'self'" in csp


def test_permissions_policy_allows_camera_for_tryon():
    pp = _global_headers().get("Permissions-Policy", "")
    assert "camera=(self)" in pp
    assert "microphone=()" in pp
