"""Every link we EMAIL must be a route the SPA actually serves (task §18/§19).

The incident this suite guards against: verification/reset emails pointed at
``/verify-email?token=…`` and ``/reset-password?token=…`` while the React router
had no such routes — every click fell through the catch-all to "/", so the
user believed they had verified/reset when nothing had happened.

This test therefore does not inspect a template string; it:
  1. runs the REAL flows that send mail (registration, forgot-password, email
     change, brand invitation, partner decision) against a loopback SMTP sink;
  2. extracts every absolute link that was actually delivered;
  3. asserts each link's path is a registered route in
     ``frontend/src/router/AppRoutes.tsx`` and is never the catch-all root.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The SMTP sink + message helpers are shared with the real-transport suite
# through a normal module (importing a test module by bare name would make the
# deployment dependency manifest gate treat it as an undeclared package).
from backend.tests.smtp_test_support import _csrf, _plain_text, smtp_sink  # noqa: F401

REPO = Path(__file__).resolve().parents[2]
ROUTES_FILE = REPO / "frontend" / "src" / "router" / "AppRoutes.tsx"

_LINK_RE = re.compile(r"https://confit-a\.vercel\.app(/[^\s\"'<>)]*)")


def _spa_routes() -> set[str]:
    """Static route patterns declared in the SPA router."""
    text = ROUTES_FILE.read_text()
    routes = set(re.findall(r'path="([^"]+)"', text))
    # Nested child routes are declared relative to their parent; the paths this
    # contract cares about (auth lifecycle, partner onboarding) are absolute.
    return routes


def _matches_spa_route(path: str, routes: set[str]) -> bool:
    for route in routes:
        if not route.startswith("/"):
            continue
        pattern = "^" + re.sub(r":[A-Za-z_]+", "[^/]+", re.escape(route).replace(r"\:", ":")) + "$"
        if re.match(pattern, path):
            return True
    return False


def test_every_delivered_link_resolves_to_a_real_spa_route(client: TestClient, smtp_sink):
    admin = TestClient(client.app)
    applicant = TestClient(client.app)

    # --- 1. verification email (registration) ------------------------------
    r = applicant.post(
        "/api/v1/auth/register",
        json={"email": "route-contract@example.com", "password": "Password123!", "full_name": "Route Contract"},
    )
    assert r.status_code == 201, r.text
    verification_token = re.search(
        r"token=([A-Za-z0-9_\-]+)", _plain_text(smtp_sink.messages[-1])
    ).group(1)

    # --- 2. reset email ----------------------------------------------------
    r = applicant.post(
        "/api/v1/auth/forgot-password", json={"email": "route-contract@example.com"}, headers=_csrf(applicant)
    )
    assert r.status_code == 200, r.text

    # --- 3. email-change email (authenticated, sent to the NEW address) ----
    r = applicant.post(
        "/api/v1/auth/email-change/request",
        json={"new_email": "route-contract-new@example.com"},
        headers=_csrf(applicant),
    )
    assert r.status_code == 200, r.text

    # --- 4. verify the address, then apply for partner access -------------
    v = applicant.post("/api/v1/auth/verify-email", json={"token": verification_token}, headers=_csrf(applicant))
    assert v.status_code == 200, v.text
    sub = applicant.post(
        "/api/v1/auth/partner-applications",
        json={"brand_name": "Route Contract Atelier", "market": "EG", "contact_name": "Route Contract"},
        headers=_csrf(applicant),
    )
    assert sub.status_code == 201, sub.text

    # --- 5. partner decision email (admin approval provisions the brand) ---
    assert admin.post(
        "/api/v1/auth/login", json={"email": "admin@confit.io", "password": "Password123!"}
    ).status_code == 200, "seeded platform admin must be able to sign in"
    listing = admin.get("/api/v1/admin/partner-applications?status=pending")
    target = next(a for a in listing.json()["items"] if a["id"] == sub.json()["id"])
    approve = admin.post(
        f"/api/v1/admin/partner-applications/{target['id']}/approve",
        json={"note": "route contract check"},
        headers=_csrf(admin),
    )
    assert approve.status_code == 200, approve.text

    # --- 6. invitation email (the freshly provisioned owner invites staff) -
    inv = applicant.post(
        "/api/v1/brand/invitations",
        json={"email": "route-invitee@example.com", "role": "brand_staff"},
        headers=_csrf(applicant),
    )
    assert inv.status_code == 201, inv.text

    # --- extract every link that was really delivered ----------------------
    links = set()
    for raw in smtp_sink.messages:
        for url in _LINK_RE.findall(_plain_text(raw)):
            # Compare the PATH only: the query carries the one-time token.
            links.add(url.split("?", 1)[0].split("#", 1)[0])
    assert links, "no links were delivered - the flows above should have sent mail"

    routes = _spa_routes()
    unresolved = sorted(p for p in links if not _matches_spa_route(p, routes))
    assert not unresolved, (
        "emailed link(s) point at routes the SPA does not serve (they would fall "
        f"through to the catch-all): {unresolved}"
    )
    assert "/" not in links, "an email linked to the catch-all root instead of a real flow page"

    for expected in ("/verify-email", "/reset-password", "/settings/confirm-email", "/invite", "/b2b"):
        assert expected in routes, f"SPA route {expected} is missing from AppRoutes.tsx"
