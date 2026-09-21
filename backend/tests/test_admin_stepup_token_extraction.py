"""G-11 — step-up re-auth must accept the same tokens as ordinary auth.

`require_admin_recent` guarded state-changing admin actions by re-reading the
token itself instead of calling the platform's `_extract_token`. It handled the
FastAPI `credentials` object and the session cookie, and nothing else — so two
tokens that authenticate everywhere else failed step-up:

* a bare `Authorization: Bearer <tok>` header that FastAPI's `HTTPBearer`
  dependency did not populate into `credentials`;
* a bearer whose scheme prefix Vercel rewrote to its `***` redaction marker,
  which `_extract_token` explicitly recovers.

The observable bug: an admin could open the dashboard (plain `require_role`)
but every transition returned an authentication error. These tests drive the
real endpoint through the real extractor.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.core.dependencies import _REDACTED_BEARER_MARKER


def _login(client: TestClient, email: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _admin_order(client: TestClient, admin_token: str) -> str:
    """Create an order and read it back so a transition has something to act on."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.commerce import Order

    db = TestingSessionLocal()
    try:
        o = db.query(Order).order_by(Order.id.desc()).first()
        assert o is not None, "the seeded database must contain an order"
        return o.order_number
    finally:
        db.close()


@pytest.mark.parametrize("header_style", ["bearer", "redacted"])
def test_step_up_accepts_every_token_form_the_platform_issues(
    client: TestClient, header_style: str
):
    """The header must be the ONLY credential, or the test proves nothing.

    `TestClient` keeps a cookie jar per instance and `_extract_token` falls
    back to the httpOnly session cookie. Logging in on the shared client would
    therefore let the cookie authenticate the step-up call even when the header
    was ignored — which is exactly how the original bug stayed hidden. Every
    request below goes out on a cookie-free client.
    """
    from backend.app.main import app

    token = _login(client, "admin@confit.io")
    value = f"Bearer {token}" if header_style == "bearer" else f"{_REDACTED_BEARER_MARKER}{token}"
    headerless = TestClient(app)  # fresh jar: the header is the only credential
    assert "confit_token" not in headerless.cookies

    # Ordinary admin auth accepts it — this is the behaviour that already worked.
    r = headerless.get("/api/v1/admin/analytics", headers={"Authorization": value})
    assert r.status_code == 200, (header_style, r.text)

    # Step-up re-auth must accept the SAME token. Before G-11 the redacted form
    # failed here with 401 while the call above succeeded.
    order = _admin_order(client, token)
    r = headerless.post(
        f"/api/v1/admin/orders/{order}/transition",
        json={"new_status": "processing"},
        headers={"Authorization": value},
    )
    assert r.status_code != 401, (
        f"{header_style}: step-up rejected a token ordinary auth accepted: {r.text}"
    )


def test_the_cookie_still_satisfies_step_up(client: TestClient):
    """The httpOnly session cookie path must keep working."""
    login = client.post("/api/v1/auth/login",
                        json={"email": "admin@confit.io", "password": "Password123!"})
    assert login.status_code == 200
    order = _admin_order(client, login.json()["access_token"])
    r = client.post(f"/api/v1/admin/orders/{order}/transition",
                    json={"new_status": "processing"})
    assert r.status_code != 401, r.text


def test_a_garbage_token_still_fails_closed(client: TestClient):
    """Unifying the extractor must not loosen it.

    Uses a cookie-free client on purpose. `_extract_token` falls back to the
    httpOnly session cookie when the header carries nothing usable, which is
    correct — so a garbage header on an already-authenticated jar proves
    nothing. The assertion only means something with no cookie present.
    """
    from backend.app.main import app

    order = _admin_order(client, _login(client, "admin@confit.io"))
    anonymous = TestClient(app)  # fresh jar: no confit_token cookie
    for bad in ("Bearer not-a-jwt", f"{_REDACTED_BEARER_MARKER}", "Bearer ", ""):
        r = anonymous.post(
            f"/api/v1/admin/orders/{order}/transition",
            json={"new_status": "processing"},
            headers={"Authorization": bad},
        )
        assert r.status_code in (401, 403), (bad, r.status_code, r.text)


def test_require_admin_recent_shares_the_extractor():
    """Guard the wiring itself, so the divergence cannot quietly return."""
    import inspect

    from backend.app.core import dependencies

    src = inspect.getsource(dependencies.require_admin_recent)
    assert "_extract_token(" in src, "step-up must use the shared extractor"
    assert 'request.cookies.get("confit_token")' not in src, (
        "step-up is reading the cookie directly again"
    )
