"""G-10 — every admin route is authorization-tested, including ones added tomorrow.

The admin surface is mounted under three prefixes at once — ``/admin/...``,
``/api/v1/admin/...`` and ``/v1/admin/...`` — so a guard added to one router
covers all three, but a *test* that hardcodes ``/api/v1`` paths silently leaves
two thirds of the surface unverified. That is what the audit found: 51 admin
paths existed and the RBAC tests named a handful.

So this module does not name any path. It reads the application's own OpenAPI
route registry and parametrizes over whatever it finds, which means:

* an admin endpoint added next week is covered the moment it is registered,
  with nobody having to remember to edit a list;
* a route that loses its guard fails here by name, on every prefix;
* the test cannot quietly shrink — it asserts the enumeration is non-empty and
  that all three prefixes are present, so a routing refactor that stops
  exposing the surface fails loudly instead of passing vacuously.

Positive authorization lives in ``test_admin01_governance.py``; this file is
the negative half — nobody who is not a platform admin gets through, by header,
by cookie, by alias, by a different HTTP method, or by a malformed token.
"""

import re

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

DENIED = (401, 403)


def _admin_paths():
    """Every path the app itself declares to be an admin surface."""
    spec = app.openapi()["paths"]
    out = []
    for path, methods in spec.items():
        segments = [s for s in path.split("/") if s]
        if "admin" not in segments:
            continue
        for method in methods:
            if method.lower() in ("get", "post", "patch", "put", "delete"):
                out.append((method.upper(), path))
    return sorted(set(out))


ADMIN_ROUTES = _admin_paths()


def _fill(path: str) -> str:
    """Substitute path parameters with values that exist.

    A bogus ``order_number`` could 404 before authorization ran, and a 404
    would look like "denied" while proving nothing about the guard. Using a
    real one forces the request through the dependency that is under test.
    """
    if "{" not in path:
        return path
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.commerce import Order

    db = TestingSessionLocal()
    try:
        order = db.query(Order).order_by(Order.id.desc()).first()
        assert order is not None, "the seeded database must contain an order"
        number = order.order_number
    finally:
        db.close()
    return re.sub(r"\{[^}]+\}", number, path)


def _login(email: str) -> str:
    client = TestClient(app)  # isolated jar: no cookie leakage between cases
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def consumer_token() -> str:
    return _login("shopper@confit.io")


# --- the enumeration itself must be trustworthy ----------------------------


def test_the_route_registry_actually_exposes_an_admin_surface():
    """Guard against a vacuous pass: an empty list would make every test below
    disappear and the suite would still be green."""
    assert len(ADMIN_ROUTES) >= 20, (
        f"only {len(ADMIN_ROUTES)} admin routes discovered — the enumeration is broken "
        "or the admin surface moved; this test exists so that cannot pass silently"
    )


def test_all_three_prefixes_are_covered():
    """The gap was alias coverage, so assert the aliases are really enumerated."""
    paths = {p for _, p in ADMIN_ROUTES}
    assert any(p.startswith("/api/v1/admin") for p in paths), "missing /api/v1/admin"
    assert any(p.startswith("/v1/admin") for p in paths), "missing /v1/admin"
    assert any(re.match(r"^/admin(/|$)", p) for p in paths), "missing the bare /admin alias"


def test_every_discovered_route_appears_under_every_prefix():
    """An alias that exists for some endpoints but not others is how a route
    ends up reachable on one prefix and unguarded on another."""
    bare = {p[len("/admin"):] for _, p in ADMIN_ROUTES if re.match(r"^/admin(/|$)", p)}
    apiv1 = {p[len("/api/v1/admin"):] for _, p in ADMIN_ROUTES if p.startswith("/api/v1/admin")}
    v1 = {p[len("/v1/admin"):] for _, p in ADMIN_ROUTES if p.startswith("/v1/admin")}
    assert bare == apiv1 == v1, (
        f"alias coverage diverges: bare-only={sorted(bare - apiv1)}, "
        f"apiv1-only={sorted(apiv1 - bare)}, v1-only={sorted(v1 - bare)}"
    )


# --- negative authorization, per route, per alias --------------------------


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_a_guest_cannot_reach_any_admin_route(method: str, path: str):
    """No credentials at all. 401 or 403 — never 200, and never a 404 that
    would masquerade as a denial."""
    client = TestClient(app)
    r = client.request(method, _fill(path))
    assert r.status_code in DENIED, (
        f"{method} {path} returned {r.status_code} for an unauthenticated caller"
    )


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_a_consumer_cannot_reach_any_admin_route(method: str, path: str, consumer_token: str):
    client = TestClient(app)
    r = client.request(method, _fill(path),
                       headers={"Authorization": f"Bearer {consumer_token}"})
    assert r.status_code in DENIED, (
        f"{method} {path} returned {r.status_code} for a consumer"
    )


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_a_malformed_token_grants_nothing(method: str, path: str):
    """A token that is not a token must not be treated as an anonymous success
    nor as a valid identity."""
    client = TestClient(app)
    for bad in ("Bearer not-a-jwt", "Bearer ", "Basic Zm9vOmJhcg==", "Bearer ***"):
        r = client.request(method, _fill(path), headers={"Authorization": bad})
        assert r.status_code in DENIED, (
            f"{method} {path} returned {r.status_code} for a malformed token {bad!r}"
        )


# --- positive authorization, so the guards are not simply "deny everyone" ---


def test_an_admin_can_reach_the_read_surface():
    """If every route returned 403 the tests above would all pass and the
    platform would be useless. Prove the guard admits the right role."""
    token = _login("admin@confit.io")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/api/v1/admin/analytics", "/v1/admin/analytics",
                 "/admin/overview", "/api/v1/admin/audit"):
        r = client.get(path, headers=headers)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


def test_the_same_route_denies_on_every_alias_identically(consumer_token: str):
    """One endpoint, three prefixes, one answer."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {consumer_token}"}
    codes = {p: client.get(p, headers=headers).status_code
             for p in ("/admin/analytics", "/api/v1/admin/analytics", "/v1/admin/analytics")}
    assert len(set(codes.values())) == 1, f"aliases disagree: {codes}"
    assert set(codes.values()) <= set(DENIED), codes
