"""F-14 regression: measurement-session IDOR + consent fabrication.

Production evidence (2026-09-05, live audit):
* ``GET /api/v1/measurements/sessions/{id}`` answered ANY anonymous request
  with the full session row — including ``user_id`` and every stored body
  measurement — for any enumerable integer id.
* ``POST /api/v1/measurements/sessions/{id}/results`` answered ANY anonymous
  request; posting to an unknown id AUTO-CREATED a session with
  ``consent_granted=True`` and wrote fabricated default dimensions
  (shoulder 45 / chest 98 / waist 82 / hip 96) — consent fabrication plus
  PII write with no identity at all.

Invariant under test (enforced in
``backend/app/services/measurement_service.py``):

    authenticated owner        -> allowed
    different authenticated    -> 404 (no oracle)
    anonymous (no identity)    -> 404 / 422, no state created
    guest with own token       -> allowed (app-wide X-Session-Token pattern)
    guest with foreign token   -> 404
    consent                    -> captured only at session start, never
                                  assumed, never mutable via results
"""

import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.conftest import TestingSessionLocal as SessionLocal
from backend.app.models.tryon import MeasurementSession, MeasurementResult

SUFFIX = uuid.uuid4().hex[:10]
PW = "Sec!Test#Pass2026x9"
MEAS = "/api/v1/measurements/sessions"


def _register(client: TestClient, name: str) -> dict:
    email = f"f14.{name}.{uuid.uuid4().hex[:10]}@{SUFFIX}.test.dev"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PW, "full_name": name, "role": "admin"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    # The role fix (separate branch) may or may not be merged here; either
    # way this test needs a logged-in consumer.
    assert body["user"]["role"] in ("consumer", "CONSUMER", "admin"), body
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PW}
    )
    assert login.status_code == 200, login.text
    return {"token": login.json()["access_token"], "id": body["user"]["id"], "email": email}


def _auth(u: dict) -> dict:
    return {"Authorization": f"Bearer {u['token']}"}


def _create(client: TestClient, headers: dict, body: dict | None = None) -> dict:
    payload = {"capture_mode": "client_side"}
    if body:
        payload.update(body)
    return client.post(MEAS, json=payload, headers=headers)


# ── 1. legitimate authenticated flow ──────────────────────────────────────
def test_authenticated_owner_lifecycle():
    client = TestClient(app)
    u = _register(client, "owner")
    h = _auth(u)

    cr = _create(client, h, {"consent_granted": True})
    assert cr.status_code == 201, cr.text
    sid = cr.json()["id"]

    got = client.get(f"{MEAS}/{sid}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["consent_granted"] is True

    res = client.post(
        f"{MEAS}/{sid}/results",
        json={"height_cm": 178.0, "chest_cm": 101.0},
        headers=h,
    )
    assert res.status_code == 201, res.text
    assert res.json()["result_id"]

    got2 = client.get(f"{MEAS}/{sid}", headers=h)
    assert got2.status_code == 200
    assert len(got2.json()["results"]) == 1


# ── 2. different authenticated user is denied (no oracle) ─────────────────
def test_different_user_denied_with_404_not_oracle():
    client = TestClient(app)
    a = _register(client, "alice")
    b = _register(client, "bob")

    cr = _create(client, _auth(a), {"consent_granted": True})
    sid = cr.json()["id"]

    read = client.get(f"{MEAS}/{sid}", headers=_auth(b))
    assert read.status_code == 404, read.text
    write = client.post(
        f"{MEAS}/{sid}/results", json={"height_cm": 170.0}, headers=_auth(b)
    )
    assert write.status_code == 404, write.text

    # Unknown-id shape is byte-identical in status (no existence oracle).
    missing = client.get(f"{MEAS}/{sid + 999999}", headers=_auth(b))
    assert missing.status_code == read.status_code == 404

    # And nothing was written to A's session.
    with SessionLocal() as db:
        n = db.query(MeasurementResult).filter(MeasurementResult.session_id == sid).count()
        assert n == 0


# ── 3. anonymous access is denied everywhere ──────────────────────────────
def test_anonymous_read_write_denied():
    client = TestClient(app)
    u = _register(client, "victim")
    cr = _create(client, _auth(u), {"consent_granted": True})
    sid = cr.json()["id"]

    # Fresh client = no cookies, no bearer: a truly anonymous caller.
    anon = TestClient(app)
    assert anon.get(f"{MEAS}/{sid}").status_code == 404
    assert (
        anon.post(f"{MEAS}/{sid}/results", json={"height_cm": 170.0}).status_code
        == 404
    )


def test_anonymous_create_without_token_rejected():
    client = TestClient(app)
    cr = client.post(MEAS, json={"capture_mode": "client_side"})
    assert cr.status_code == 422, cr.text
    with SessionLocal() as db:
        last = (
            db.query(MeasurementSession)
            .order_by(MeasurementSession.id.desc())
            .first()
        )
        # No unbindable session may exist: every session row carries either a
        # user_id or a guest_session_token.
        assert last is None or (last.user_id is not None or last.guest_session_token), (
            "unbound measurement session created"
        )


# ── 4. legitimate guest flow (app-wide X-Session-Token pattern) ───────────
def test_guest_flow_bound_to_session_token():
    client = TestClient(app)
    token = "sess_f14guest" + uuid.uuid4().hex[:12]
    h = {"X-Session-Token": token}

    cr = _create(client, h, {"consent_granted": True})
    assert cr.status_code == 201, cr.text
    assert cr.json()["session_token"] == token
    sid = cr.json()["id"]

    assert client.get(f"{MEAS}/{sid}", headers=h).status_code == 200

    other = {"X-Session-Token": "sess_someone_else_" + uuid.uuid4().hex[:8]}
    assert client.get(f"{MEAS}/{sid}", headers=other).status_code == 404
    assert (
        client.post(
            f"{MEAS}/{sid}/results",
            json={"height_cm": 170.0},
            headers=other,
        ).status_code
        == 404
    )

    res = client.post(f"{MEAS}/{sid}/results", json={"height_cm": 175.5}, headers=h)
    assert res.status_code == 201, res.text


# ── 5. no auto-creation via results POST ──────────────────────────────────
def test_results_post_to_unknown_id_creates_nothing():
    client = TestClient(app)
    u = _register(client, "writer")
    with SessionLocal() as db:
        before = db.query(MeasurementSession).count()

    ghost = 4_000_000 + uuid.uuid4().int % 100000
    anon = TestClient(app)  # truly anonymous: no cookies, no bearer
    assert anon.post(f"{MEAS}/{ghost}/results", json={"height_cm": 170.0}).status_code == 404
    # Bearer caller (no session cookie -> CSRF not engaged): still 404, and
    # still no creation.
    authed = client.post(
        f"{MEAS}/{ghost}/results", json={"height_cm": 170.0}, headers=_auth(u)
    )
    assert authed.status_code == 404

    with SessionLocal() as db:
        after = db.query(MeasurementSession).count()
        assert after == before, "results POST auto-created a session"
        row = db.query(MeasurementSession).filter(MeasurementSession.id == ghost).first()
        assert row is None


# ── 6. consent: explicit at creation, never fabricated later ──────────────
def test_consent_never_fabricated():
    client = TestClient(app)
    u = _register(client, "consent")
    h = _auth(u)

    # Unspecified consent -> persisted False (never assumed True).
    cr = _create(client, h)
    sid = cr.json()["id"]
    got = client.get(f"{MEAS}/{sid}", headers=h)
    assert got.json()["consent_granted"] is False

    # A results payload cannot flip consent (the schema has no consent
    # field; even a crafted extra field must not mutate the session).
    res = client.post(
        f"{MEAS}/{sid}/results",
        json={"height_cm": 171.0, "consent_granted": True},
        headers=h,
    )
    assert res.status_code == 201, res.text
    got2 = client.get(f"{MEAS}/{sid}", headers=h)
    assert got2.json()["consent_granted"] is False

    # Explicit consent at creation (the camera-scan flow) is honored.
    cr2 = _create(client, h, {"consent_granted": True})
    sid2 = cr2.json()["id"]
    assert client.get(f"{MEAS}/{sid2}", headers=h).json()["consent_granted"] is True


# ── 7. no identity disclosure / no fabricated dimensions ──────────────────
def test_output_does_not_expose_owner_id():
    client = TestClient(app)
    u = _register(client, "disclose")
    h = _auth(u)
    cr = _create(client, h)
    sid = cr.json()["id"]
    got = client.get(f"{MEAS}/{sid}", headers=h)
    assert got.status_code == 200
    assert "user_id" not in got.json(), got.json()


def test_no_fabricated_default_dimensions():
    client = TestClient(app)
    u = _register(client, "dims")
    h = _auth(u)
    cr = _create(client, h)
    sid = cr.json()["id"]
    res = client.post(
        f"{MEAS}/{sid}/results", json={"height_cm": 165.0}, headers=h
    )
    assert res.status_code == 201
    with SessionLocal() as db:
        row = (
            db.query(MeasurementResult)
            .filter(MeasurementResult.session_id == sid)
            .first()
        )
        assert row is not None
        assert row.height_cm == 165.0
        # Omitted dimensions must be NULL — not fabricated 45/98/82/96.
        assert row.shoulder_width_cm is None
        assert row.chest_cm is None
        assert row.waist_cm is None
        assert row.hip_cm is None


# ── 8. client-declared identity is ignored ────────────────────────────────
def test_client_supplied_user_id_is_ignored():
    client = TestClient(app)
    a = _register(client, "realowner")
    b = _register(client, "spoofed")
    h = _auth(a)

    cr = client.post(
        MEAS,
        json={
            "capture_mode": "client_side",
            "consent_granted": True,
            "user_id": b["id"],          # crafted: claim someone else
            "owner_id": b["id"],
            "session_owner": b["email"],
        },
        headers=h,
    )
    assert cr.status_code == 201, cr.text
    sid = cr.json()["id"]
    with SessionLocal() as db:
        row = db.query(MeasurementSession).filter(MeasurementSession.id == sid).first()
        assert row.user_id == a["id"], "session bound to client-declared identity"
        assert row.user_id != b["id"]


def test_service_submit_results_has_no_consent_parameter():
    """Structural invariant: the results path cannot touch consent at all."""
    import inspect

    from backend.app.services.measurement_service import MeasurementSessionService

    params = inspect.signature(MeasurementSessionService.submit_results).parameters
    assert "consent" not in " ".join(params)
    src = inspect.getsource(MeasurementSessionService.submit_results)
    assert "consent_granted=True" not in src
    assert "MeasurementSession(" not in src, "results path must not create sessions"
