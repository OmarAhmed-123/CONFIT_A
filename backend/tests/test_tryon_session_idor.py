"""Try-on SESSION IDOR regression (mandatory Phase-3 closure, 2026-09-06).

Production defect being guarded (mirrors the F-14 measurement IDOR):

* ``GET  /api/v1/try-on/sessions/{id}`` answered ANY anonymous request for an
  enumerable session id.
* ``POST .../apply-item`` / ``remove-item`` / ``reorder`` were NOT
  ownership-gated at all — an anonymous caller, or a different authenticated
  user, could mutate another person's try-on session (add/remove/reorder their
  garments, rewrite the layer order, or purge it).

The fix closes this with ONE canonical, fail-closed, server-side ownership
resolver — ``TryOnRepository.get_owned_tryon_session`` — that is reused across
every read/mutation (GET, apply-item, remove-item, reorder, apply-measurements,
purge) and is the ONLY place ownership is decided. Ownership is derived from
trusted server-side state only:

    authenticated owner           -> allowed
    different authenticated user  -> 404 (no existence oracle)
    anonymous (no identity/token) -> 404
    guest with its OWN bound token-> allowed (app-wide X-Session-Token)
    guest with a FOREIGN token    -> 404
    client-forged owner/user ids  -> ignored (server identity wins)

A session is bound either to ``user_id`` (authenticated) or to a
``guest_session_token`` (anonymous). A user-bound session can never be reached
via a token; a guest session is reachable only with its exact bound token.

These tests exercise the real endpoints through the FastAPI app. The GPU
re-render triggered by apply-item is stubbed for the OWNER (allow) case only so
the suite is deterministic and burns zero GPU; the ownership gate itself always
runs for real (it executes before the render). Denial cases return 404 at the
gate, before any GPU work, and need no stub.
"""

import json
import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.conftest import TestingSessionLocal as SessionLocal
from backend.app.models.tryon import TryOnSession
from backend.app.models.catalog import Product
from backend.app.services.tryon_service import TryOnService

SUFFIX = uuid.uuid4().hex[:10]
PW = "Sec!Test#Pass2026x9"
TR = "/api/v1/try-on/sessions"

# Stored try-on items: each needs a position (reorder key) + product_id.
ITEMS_ONE = [
    {"product_id": 1, "position": "upper_inner", "slot_type": "upper_inner",
     "title": "Shirt", "price": 40, "image_url": "data:image/jpeg;base64,s"},
]
ITEMS_TWO = [
    {"product_id": 1, "position": "upper_inner", "slot_type": "upper_inner",
     "title": "Shirt", "price": 40, "image_url": "data:image/jpeg;base64,s"},
    {"product_id": 2, "position": "upper_outer", "slot_type": "upper_outer",
     "title": "Blazer", "price": 120, "image_url": "data:image/jpeg;base64,b"},
]


def _register(client: TestClient, name: str) -> dict:
    email = f"idor.{name}.{uuid.uuid4().hex[:10]}@{SUFFIX}.test.dev"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PW, "full_name": name, "role": "admin"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["user"]["role"] in ("consumer", "CONSUMER", "admin"), body
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert login.status_code == 200, login.text
    return {"token": login.json()["access_token"], "id": body["user"]["id"]}


def _auth(u: dict) -> dict:
    return {"Authorization": f"Bearer {u['token']}"}


def _guest(token: str) -> dict:
    return {"X-Session-Token": token}


def _make_session(db, user_id=None, guest_token=None, items=None) -> TryOnSession:
    items = items if items is not None else ITEMS_TWO
    s = TryOnSession(
        user_id=user_id,
        guest_session_token=guest_token,
        status="completed",
        fit_verdict="True to Size",
        fit_confidence_score=95,
        body_scaling_factor=1.0,
        applied_items_json=json.dumps(items),
        slot_mapping_json=json.dumps({it["position"]: it["product_id"] for it in items}),
        layering_order_json=json.dumps([it["position"] for it in items]),
        render_metadata_json=json.dumps({}),
        input_user_image_url="data:image/jpeg;base64,PERSON",
        user_image_url="data:image/jpeg;base64,PERSON",
        rendered_result_url=None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _applied(db, sid: int) -> list:
    row = db.query(TryOnSession).filter(TryOnSession.id == sid).first()
    if row is None:
        return None
    return json.loads(row.applied_items_json) if row.applied_items_json else []


# ── 1. owner read allowed ───────────────────────────────────────────────────
def test_owner_get_allowed():
    client = TestClient(app)
    u = _register(client, "owner")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=u["id"])
        sid = sess.id
    got = client.get(f"{TR}/{sid}", headers=_auth(u))
    assert got.status_code == 200, got.text
    assert got.json()["session_id"] == sid


# ── 2. non-owner read denied (no existence oracle) ──────────────────────────
def test_non_owner_get_denied_404_no_oracle():
    client = TestClient(app)
    a = _register(client, "alice")
    b = _register(client, "bob")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=a["id"])
        sid = sess.id
    read = client.get(f"{TR}/{sid}", headers=_auth(b))
    assert read.status_code == 404, read.text
    # Unknown-id shape is byte-identical in status (no existence oracle).
    missing = client.get(f"{TR}/{sid + 999999}", headers=_auth(b))
    assert missing.status_code == read.status_code == 404


# ── 3. anonymous (no identity) denied ───────────────────────────────────────
def test_anonymous_get_denied_404():
    client = TestClient(app)
    u = _register(client, "victim")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=u["id"])
        sid = sess.id
    anon = TestClient(app)  # truly anonymous: no cookies, no bearer, no token
    assert anon.get(f"{TR}/{sid}").status_code == 404


# ── 4. guest own-token allowed (anon same-owner) ────────────────────────────
def test_guest_own_token_get_allowed():
    client = TestClient(app)
    tok = "sess_tryonguest" + uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        sess = _make_session(db, user_id=None, guest_token=tok)
        sid = sess.id
    assert client.get(f"{TR}/{sid}", headers=_guest(tok)).status_code == 200


# ── 5. guest foreign-token denied (anon cross-owner) ────────────────────────
def test_guest_foreign_token_get_denied_404():
    client = TestClient(app)
    tok = "sess_tryonguest" + uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        sess = _make_session(db, user_id=None, guest_token=tok)
        sid = sess.id
    foreign = _guest("sess_someone_else_" + uuid.uuid4().hex[:8])
    assert client.get(f"{TR}/{sid}", headers=foreign).status_code == 404
    # And a guest without any token is denied too.
    assert client.get(f"{TR}/{sid}").status_code == 404


# ── 6. random / unknown session id ──────────────────────────────────────────
def test_random_session_id_404():
    client = TestClient(app)
    u = _register(client, "rand")
    ghost = 4_000_000 + uuid.uuid4().int % 1_000_000
    assert client.get(f"{TR}/{ghost}", headers=_auth(u)).status_code == 404


# ── 7. malformed session id (non-integer) -> validation, not a crash ────────
def test_malformed_session_id_rejected():
    client = TestClient(app)
    u = _register(client, "malformed")
    res = client.get(f"{TR}/not-an-int", headers=_auth(u))
    assert res.status_code in (404, 422), res.text


# ── 8. owner reorder allowed; foreign user's reorder is a denied mutation ───
def test_owner_reorder_allowed():
    client = TestClient(app)
    u = _register(client, "reorderer")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=u["id"], items=ITEMS_TWO)
        sid = sess.id
    res = client.post(
        f"{TR}/{sid}/reorder",
        json={"slot_order": ["upper_outer", "upper_inner"]},
        headers=_auth(u),
    )
    assert res.status_code == 200, res.text
    assert res.json()["layering_order"] == ["upper_outer", "upper_inner"]


def test_non_owner_reorder_denied_404_and_no_state_change():
    client = TestClient(app)
    a = _register(client, "reordown")
    b = _register(client, "reordintruder")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=a["id"], items=ITEMS_TWO)
        sid = sess.id
        before = _applied(db, sid)
    res = client.post(
        f"{TR}/{sid}/reorder",
        json={"slot_order": ["upper_outer", "upper_inner"]},
        headers=_auth(b),
    )
    assert res.status_code == 404, res.text
    with SessionLocal() as db:
        assert _applied(db, sid) == before, "cross-user reorder mutated the session"


# ── 9. remove-item: owner removes their last item (no GPU -> 200) ───────────
def test_owner_remove_last_item_allowed():
    client = TestClient(app)
    u = _register(client, "remover")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=u["id"], items=ITEMS_ONE)
        sid = sess.id
    res = client.post(
        f"{TR}/{sid}/remove-item", json={"product_id": 1}, headers=_auth(u)
    )
    # Removing the only item empties the outfit -> honest 200 with no GPU call.
    assert res.status_code == 200, res.text
    assert res.json()["applied_items"] == []


def test_non_owner_remove_denied_404_and_no_state_change():
    client = TestClient(app)
    a = _register(client, "remowner")
    b = _register(client, "remointruder")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=a["id"], items=ITEMS_TWO)
        sid = sess.id
        before = _applied(db, sid)
    res = client.post(
        f"{TR}/{sid}/remove-item", json={"product_id": 1}, headers=_auth(b)
    )
    assert res.status_code == 404, res.text
    with SessionLocal() as db:
        assert _applied(db, sid) == before, "cross-user remove mutated the session"


# ── 10. apply-item: owner allowed (render stubbed), non-owner denied ────────
def test_owner_apply_item_allowed(monkeypatch):
    client = TestClient(app)
    u = _register(client, "appowner")
    with SessionLocal() as db:
        target = db.query(Product).first().id
        sess = _make_session(db, user_id=u["id"], items=ITEMS_ONE)
        sid = sess.id

    # Stub ONLY the GPU re-render so the test is deterministic + zero-GPU.
    # The ownership gate in apply_item_to_session still runs for real.
    calls = {}

    async def fake_execute(self, **kw):
        calls.update(kw)
        return {
            "session_id": sid, "status": "completed", "applied_items": [],
            "rendered_result_url": "data:image/jpeg;base64,RESULT",
            "fit_confidence_score": 95, "body_fit_verdict": "ok",
            "recommended_sizes": {}, "ai_disclosure": "test",
            "traceability_hash": "T", "layering_order": [], "expires_at": None,
            "model_used": None, "execution_time_ms": 1,
        }

    monkeypatch.setattr(TryOnService, "execute_multi_garment_tryon", fake_execute)
    res = client.post(
        f"{TR}/{sid}/apply-item", json={"product_id": target}, headers=_auth(u)
    )
    assert res.status_code == 200, res.text
    # The re-render was reached for the owner (gate let them through) and was
    # handed their OWN session + their own identity.
    assert calls.get("existing_session_id") == sid
    assert calls.get("user_id") == u["id"]


def test_non_owner_apply_item_denied_404():
    client = TestClient(app)
    a = _register(client, "applyowner")
    b = _register(client, "applyintruder")
    with SessionLocal() as db:
        target = db.query(Product).first().id
        sess = _make_session(db, user_id=a["id"], items=ITEMS_ONE)
        sid = sess.id
    # Authenticated non-owner (Bearer) -> 404 at the gate, before any GPU.
    res = client.post(
        f"{TR}/{sid}/apply-item", json={"product_id": target}, headers=_auth(b)
    )
    assert res.status_code == 404, res.text
    # A different guest (foreign token) is denied the same way. Use a FRESH
    # client (no session cookie from the logins above) so the app-wide CSRF
    # middleware does not engage — a real anonymous guest holds no session
    # cookie, so this mirrors production.
    guest_client = TestClient(app)
    tok = "sess_applyguest" + uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        gsess = _make_session(db, user_id=None, guest_token=tok, items=ITEMS_ONE)
        gsid = gsess.id
    foreign = _guest("sess_other_" + uuid.uuid4().hex[:8])
    assert guest_client.post(
        f"{TR}/{gsid}/apply-item", json={"product_id": target}, headers=foreign
    ).status_code == 404


# ── 11. apply-measurements: owner allowed, non-owner denied ─────────────────
def test_owner_apply_measurements_allowed():
    client = TestClient(app)
    u = _register(client, "measurer")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=u["id"])
        sid = sess.id
    res = client.post(
        f"{TR}/{sid}/apply-measurements",
        json={"height_cm": 180.0, "chest_cm": 104.0},
        headers=_auth(u),
    )
    assert res.status_code == 200, res.text
    assert res.json()["scaling_factor"] == round(180.0 / 175.0, 2)


def test_non_owner_apply_measurements_denied_404():
    client = TestClient(app)
    a = _register(client, "measowner")
    b = _register(client, "measintruder")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=a["id"])
        sid = sess.id
    res = client.post(
        f"{TR}/{sid}/apply-measurements",
        json={"height_cm": 180.0},
        headers=_auth(b),
    )
    assert res.status_code == 404, res.text


# ── 12. purge: owner allowed, non-owner + anonymous denied ──────────────────
def test_owner_purge_allowed():
    client = TestClient(app)
    u = _register(client, "purger")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=u["id"])
        sid = sess.id
    res = client.delete(f"{TR}/{sid}/purge", headers=_auth(u))
    assert res.status_code in (200, 204), res.text
    with SessionLocal() as db:
        assert db.query(TryOnSession).filter(TryOnSession.id == sid).first() is None


def test_non_owner_purge_denied_404_and_session_survives():
    client = TestClient(app)
    a = _register(client, "purgeowner")
    b = _register(client, "purgeintruder")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=a["id"])
        sid = sess.id
    res = client.delete(f"{TR}/{sid}/purge", headers=_auth(b))
    assert res.status_code == 404, res.text
    with SessionLocal() as db:
        assert db.query(TryOnSession).filter(TryOnSession.id == sid).first() is not None

    # Anonymous (no token) cannot purge a guest session either.
    tok = "sess_purgeguest" + uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        gsess = _make_session(db, user_id=None, guest_token=tok)
        gsid = gsess.id
    anon = TestClient(app)
    assert anon.delete(f"{TR}/{gsid}/purge").status_code == 404
    with SessionLocal() as db:
        assert db.query(TryOnSession).filter(TryOnSession.id == gsid).first() is not None


# ── 13. guest mutation flows (own token ok, foreign token denied) ───────────
def test_guest_reorder_own_token_allowed_foreign_denied():
    client = TestClient(app)
    tok = "sess_reorguest" + uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        sess = _make_session(db, user_id=None, guest_token=tok, items=ITEMS_TWO)
        sid = sess.id
    assert client.post(
        f"{TR}/{sid}/reorder",
        json={"slot_order": ["upper_outer", "upper_inner"]},
        headers=_guest(tok),
    ).status_code == 200
    foreign = _guest("sess_other_" + uuid.uuid4().hex[:8])
    assert client.post(
        f"{TR}/{sid}/reorder",
        json={"slot_order": ["upper_inner", "upper_outer"]},
        headers=foreign,
    ).status_code == 404


# ── 14. client-forged ownership fields are ignored (server identity wins) ───
def test_forged_client_ownership_fields_ignored():
    client = TestClient(app)
    a = _register(client, "realowner")
    b = _register(client, "spoofed")
    with SessionLocal() as db:
        sess = _make_session(db, user_id=a["id"], items=ITEMS_TWO)
        sid = sess.id
    # B (authenticated) tries to reach A's session by FORGING ownership in the
    # body/query. The server derives ownership from B's real identity, so this
    # is still a 404 — the forged fields have no effect.
    res = client.post(
        f"{TR}/{sid}/reorder",
        json={"slot_order": ["upper_outer", "upper_inner"], "user_id": a["id"],
              "owner_id": a["id"], "session_owner": a["id"]},
        headers=_auth(b),
    )
    assert res.status_code == 404, res.text

    # A guest forging a token that is not the bound one is denied.
    tok = "sess_forgedguest" + uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        gsess = _make_session(db, user_id=None, guest_token=tok, items=ITEMS_TWO)
        gsid = gsess.id
    forged = _guest("sess_not_the_bound_token_" + uuid.uuid4().hex[:8])
    assert client.get(f"{TR}/{gsid}", headers=forged).status_code == 404
    # Presenting a user identity plus a foreign token still cannot open it.
    assert client.get(f"{TR}/{gsid}", headers={**_auth(b), **forged}).status_code == 404


# ── 15. explicit cross-user mutation matrix (all mutation verbs) ────────────
def test_cross_user_mutation_all_verbs_denied():
    client = TestClient(app)
    a = _register(client, "mutowner")
    b = _register(client, "mutintruder")
    with SessionLocal() as db:
        target = db.query(Product).first().id
        sess = _make_session(db, user_id=a["id"], items=ITEMS_TWO)
        sid = sess.id

    assert client.post(
        f"{TR}/{sid}/apply-measurements", json={"height_cm": 178.0}, headers=_auth(b)
    ).status_code == 404
    assert client.post(
        f"{TR}/{sid}/reorder", json={"slot_order": ["upper_outer", "upper_inner"]},
        headers=_auth(b),
    ).status_code == 404
    assert client.post(
        f"{TR}/{sid}/remove-item", json={"product_id": 1}, headers=_auth(b)
    ).status_code == 404
    assert client.post(
        f"{TR}/{sid}/apply-item", json={"product_id": target}, headers=_auth(b)
    ).status_code == 404
    assert client.delete(f"{TR}/{sid}/purge", headers=_auth(b)).status_code == 404

    with SessionLocal() as db:
        # Nothing changed and the session is intact and still owned by A.
        row = db.query(TryOnSession).filter(TryOnSession.id == sid).first()
        assert row is not None and row.user_id == a["id"]
        assert _applied(db, sid) == ITEMS_TWO
