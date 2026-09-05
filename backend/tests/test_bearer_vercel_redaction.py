"""Regression: Vercel edge redacts the Authorization header on production
serverless functions, which silently broke bearer auth for every API client.

Production evidence (2026-09-05, live probe of the scope bytes in
/api/v1/auth/me): a request sent as ``Authorization: Bearer <jwt>`` arrived
at the app as ``Authorization: ***<jwt>`` — the scheme prefix replaced by
``***`` while the JWT payload survived intact. HTTPBearer then found no
scheme and returned None, so every bearer client got
``401 AUTH_FAILED "Authorization bearer token required."`` while the
cookie flow (unaffected by the redaction) kept working.

The app-side recovery lives in ``_extract_token``: it accepts the platform's
redaction marker in place of the Bearer scheme and returns the intact token,
which then passes the exact same signature/expiry/subject validation as any
bearer token. These tests pin both the unit behavior and the real
end-to-end behavior through the full app (login -> redacted header ->
authenticated response), including the negative cases that prove the
redaction marker alone never grants access.
"""

from fastapi import Request
from fastapi.testclient import TestClient

from backend.app.core.dependencies import _extract_token
from backend.app.main import app


def _request_with_auth(value: str, cookie: str | None = None) -> Request:
    headers = []
    if value is not None:
        headers.append((b"authorization", value.encode()))
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))
    return Request({"type": "http", "method": "GET", "path": "/api/v1/auth/me",
                    "headers": headers})


JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidHlwZSI6ImFjY2VzcyJ9.fakesig"


def test_extract_token_standard_bearer():
    req = _request_with_auth(f"Bearer {JWT}")
    assert _extract_token(req, credentials=None) == JWT


def test_extract_token_standard_bearer_lowercase_scheme():
    req = _request_with_auth(f"bearer {JWT}")
    assert _extract_token(req, credentials=None) == JWT


def test_extract_token_httpbearer_credentials_win():
    from fastapi.security import HTTPAuthorizationCredentials
    req = _request_with_auth(f"Bearer {JWT}")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=JWT)
    assert _extract_token(req, creds) == JWT


def test_extract_token_vercel_redacted_form_recovers_jwt():
    """Exactly what production observed: '***' + intact JWT."""
    req = _request_with_auth(f"***{JWT}")
    assert _extract_token(req, credentials=None) == JWT


def test_extract_token_bare_redaction_marker_never_authenticates():
    """Low-entropy values arrive as bare '***' — the token is gone and must
    NOT fall through to a fake success; cookie fallback still applies."""
    req = _request_with_auth("***")
    assert _extract_token(req, credentials=None) is None
    req_with_cookie = _request_with_auth("***", cookie="confit_token=sessionjwt")
    assert _extract_token(req_with_cookie, credentials=None) == "sessionjwt"


def test_extract_token_cookie_fallback_intact():
    req = _request_with_auth(None, cookie="confit_token=sessionjwt")
    assert _extract_token(req, credentials=None) == "sessionjwt"


def test_extract_token_nothing_present():
    assert _extract_token(_request_with_auth(None), credentials=None) is None


def test_redacted_bearer_end_to_end_through_real_app():
    """Full stack: login (real JWT) -> send the Vercel-redacted header shape
    -> the same authenticated response a normal bearer client would get."""
    client = TestClient(app)
    login = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!",
    })
    assert login.status_code == 200
    token = login.json()["access_token"]

    # 1. Normal bearer still works (regression guard)
    ok = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.json()["email"] == "shopper@confit.io"

    # 2. The exact shape Vercel's edge produces in production
    redacted = client.get("/api/v1/auth/me", headers={"Authorization": f"***{token}"})
    assert redacted.status_code == 200
    assert redacted.json()["email"] == "shopper@confit.io"


def test_redacted_marker_alone_or_invalid_token_still_401():
    """The marker must not weaken validation: no token, or a token that does
    not pass signature/expiry checks, is still rejected."""
    client = TestClient(app)
    none = client.get("/api/v1/auth/me", headers={"Authorization": "***"})
    assert none.status_code == 401

    invalid = client.get("/api/v1/auth/me", headers={"Authorization": "***not.a.real.token"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "AUTH_FAILED"

    # malformed in the plain form too
    plain_malformed = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert plain_malformed.status_code == 401


def _login_token(client: TestClient) -> str:
    login = client.post("/api/v1/auth/login", json={
        "email": "shopper@confit.io",
        "password": "Password123!",
    })
    assert login.status_code == 200
    return login.json()["access_token"]


def test_expired_jwt_rejected_in_both_forms():
    """Expiry validation is untouched by the redaction recovery."""
    from datetime import timedelta

    from backend.app.core.security import create_access_token
    client = TestClient(app)
    # a token that passed every other check once (real sub/iss/aud), now
    # expired — minted with the real signing key
    expired = create_access_token({"sub": "1", "email": "shopper@confit.io", "role": "consumer"},
                                  expires_delta=timedelta(seconds=-3600))
    for header in (f"Bearer {expired}", f"***{expired}"):
        res = client.get("/api/v1/auth/me", headers={"Authorization": header})
        assert res.status_code == 401, (header[:14], res.text)


def test_wrong_signature_rejected_in_both_forms():
    """Signature validation is untouched: a JWT shaped correctly but signed
    with a different key is rejected in both the plain and the redacted
    form — the marker never grants trust by itself."""
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone

    from backend.app.core.config import settings
    now = datetime.now(timezone.utc)
    forged = pyjwt.encode(
        {"sub": "1", "email": "shopper@confit.io", "role": "consumer",
         "exp": now + timedelta(hours=1), "iat": now, "type": "access",
         "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE},
        "not-the-real-signing-key-0123456789",
        algorithm=settings.ALGORITHM,
    )
    client = TestClient(app)
    for header in (f"Bearer {forged}", f"***{forged}"):
        res = client.get("/api/v1/auth/me", headers={"Authorization": header})
        assert res.status_code == 401, (header[:14], res.text)
        assert res.json()["error"]["code"] == "AUTH_FAILED"


def test_valid_token_still_authenticates_in_both_forms():
    """Full matrix positive arm: the same real token authenticates in the
    standard form AND in the production-observed redacted form."""
    client = TestClient(app)
    token = _login_token(client)
    for header in (f"Bearer {token}", f"***{token}"):
        res = client.get("/api/v1/auth/me", headers={"Authorization": header})
        assert res.status_code == 200, (header[:14], res.text)
        assert res.json()["email"] == "shopper@confit.io"


def test_refresh_token_rejected_as_access_token_in_redacted_form():
    """A refresh token smuggled in via the redacted marker is rejected by
    the type check (expected_type='access'), not accepted."""
    from backend.app.core.security import create_refresh_token
    client = TestClient(app)
    login = _login_token(client)  # ensure fixtures
    refresh = create_refresh_token({"sub": "1", "email": "shopper@confit.io", "role": "consumer"})
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"***{refresh}"})
    assert res.status_code == 401, res.text
