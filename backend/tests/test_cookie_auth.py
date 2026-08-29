"""Proof for the localStorage -> httpOnly cookie session migration (S4).

Real flow, no mocks: login sets an HttpOnly cookie, cookie-only auth works,
cookie-authenticated mutations without a CSRF header are rejected (403), the
same request with the double-submit header succeeds, and logout clears the
session cookie.
"""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_cookie_session_full_flow():
    client = TestClient(app)

    # 1. Login sets the session cookie as HttpOnly
    res = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!",
    })
    assert res.status_code == 200
    set_cookie = res.headers.get("set-cookie", "")
    assert "confit_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "confit_csrf=" in res.headers.get_list("set-cookie")[1] or "confit_csrf" in str(res.headers.get_list("set-cookie"))

    # 2. Cookie-only auth works — no Authorization header at all
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "shopper@confit.io"

    # 3. Cookie-authenticated mutation WITHOUT the CSRF header -> 403
    csrf = client.cookies.get("confit_csrf")
    assert csrf, "login must set the readable CSRF cookie"
    blocked = client.patch("/api/v1/me/consents", json={"privacy_consent_tryon_storage": True})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "CSRF_TOKEN_MISMATCH"

    # 4. Same mutation WITH the double-submit header -> 200
    allowed = client.patch(
        "/api/v1/me/consents",
        headers={"X-CSRF-Token": csrf},
        json={"privacy_consent_tryon_storage": True},
    )
    assert allowed.status_code == 200

    # 5. Bearer-auth API clients bypass CSRF by design (headers can't be
    # forged cross-site) — backward compatible.
    bearer = client.patch(
        "/api/v1/me/consents",
        headers={"Authorization": f"Bearer {res.json()['access_token']}"},
        json={"privacy_consent_tryon_storage": False},
    )
    assert bearer.status_code == 200

    # 6. Logout clears the session cookie server-side
    out = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert out.status_code == 200
    logout_cookies = str(out.headers.get_list("set-cookie"))
    assert "confit_token" in logout_cookies and ('Max-Age=0' in logout_cookies or "expires" in logout_cookies.lower())
