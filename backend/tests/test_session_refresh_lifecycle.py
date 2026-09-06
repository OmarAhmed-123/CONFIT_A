"""CYCLE-3 (BLOCKER J): browser session-lifecycle contract.

The refresh token used to be returned only in the response body — which the
SPA deliberately discards (no token-shaped value in web storage) — so nothing
could ever call /auth/refresh, and the operator could not lower the 24h
ACCESS_TOKEN_EXPIRE_MINUTES without logging users out constantly.

Contract pinned here:
- login/register/refresh set an httpOnly `confit_refresh` cookie (rotated);
- POST /auth/refresh works from the cookie alone (no body) — the SPA path;
- the body path is unchanged (API/mobile clients) — backward compatible;
- refresh failure clears the stale cookie (no client retry hammering);
- logout deletes the refresh cookie together with the session cookie.
"""

import pytest
from fastapi.testclient import TestClient

LOGIN = {"email": "shopper@confit.io", "password": "Password123!"}


def _login(client: TestClient) -> dict:
    res = client.post("/api/v1/auth/login", json=LOGIN)
    assert res.status_code == 200
    return res.json()


def _csrf(client: TestClient) -> dict:
    token = client.cookies.get("confit_csrf")
    return {"X-CSRF-Token": token} if token else {}


def test_login_sets_httponly_refresh_cookie(client: TestClient):
    body = _login(client)
    refresh_cookie = client.cookies.get("confit_refresh")
    assert refresh_cookie, "login must set the confit_refresh cookie"
    assert refresh_cookie == body["refresh_token"]
    # httpOnly is a Set-Cookie attribute; assert it on the raw response
    raw = [c for c in client.post("/api/v1/auth/login", json=LOGIN).headers.get_list("set-cookie") if "confit_refresh" in c]
    assert raw and "httponly" in raw[0].lower(), raw
    assert "samesite=lax" in raw[0].lower()


def test_cookie_only_refresh_rotates_and_keeps_session(client: TestClient):
    _login(client)
    old_refresh = client.cookies.get("confit_refresh")
    assert old_refresh

    # SPA path: the empty JSON object the browser client sends — the refresh
    # cookie drives the renewal
    res = client.post(
        "/api/v1/auth/refresh",
        headers={**_csrf(client), "Content-Type": "application/json"},
        content=b"{}",
    )
    assert res.status_code == 200, res.text
    assert res.json()["refresh_token"] != old_refresh, "refresh token must rotate"
    assert client.cookies.get("confit_refresh") == res.json()["refresh_token"]

    # the renewed access cookie actually authenticates
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == LOGIN["email"]

    # replaying the OLD refresh token (cookie value captured above) must trip
    # server-side reuse detection — the whole family is revoked
    client.cookies.set("confit_refresh", old_refresh)
    replay = client.post("/api/v1/auth/refresh", headers=_csrf(client))
    assert replay.status_code == 401


def test_body_refresh_still_works_backward_compatible(client: TestClient):
    body = _login(client)
    client.cookies.delete("confit_refresh")
    res = client.post(
        "/api/v1/auth/refresh",
        headers=_csrf(client),
        json={"refresh_token": body["refresh_token"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


def test_refresh_without_any_token_is_honest_401(client: TestClient):
    _login(client)
    client.cookies.delete("confit_refresh")
    # no body at all
    res = client.post("/api/v1/auth/refresh", headers=_csrf(client))
    assert res.status_code == 401
    assert "not provided" in res.json()["error"]["message"].lower()
    # AND the exact browser shape: empty JSON object "{}" must reach the
    # handler (not die as 422 on a required-field model)
    res2 = client.post(
        "/api/v1/auth/refresh",
        headers={**_csrf(client), "Content-Type": "application/json"},
        content=b"{}",
    )
    assert res2.status_code == 401, res2.text
    assert "not provided" in res2.json()["error"]["message"].lower()


def test_expired_refresh_clears_stale_cookie(client: TestClient):
    _login(client)
    client.cookies.set("confit_refresh", "garbage-not-a-jwt")
    res = client.post("/api/v1/auth/refresh", headers=_csrf(client))
    assert res.status_code == 401
    # the stale cookie must be dropped so the browser stops auto-refreshing
    raw = [c for c in res.headers.get_list("set-cookie") if "confit_refresh" in c]
    assert raw and ("max-age=0" in c.lower() or '""' in c for c in raw), raw


def test_logout_deletes_refresh_cookie(client: TestClient):
    _login(client)
    assert client.cookies.get("confit_refresh")
    res = client.post("/api/v1/auth/logout", headers=_csrf(client))
    assert res.status_code == 200
    raw = [c for c in res.headers.get_list("set-cookie") if "confit_refresh" in c]
    assert raw and any("max-age=0" in c.lower() or '""' in c for c in raw), raw


def test_logout_tolerates_empty_json_body(client: TestClient):
    """Live-preview regression: a client sending '{}' to /auth/logout must
    still log out (422 from a required-field model would strand cookies)."""
    _login(client)
    res = client.post(
        "/api/v1/auth/logout",
        headers={**_csrf(client), "Content-Type": "application/json"},
        content=b"{}",
    )
    assert res.status_code == 200
