"""Spec 15 re-pass — consent store + one-click unsubscribe + event wiring.

The first pass shipped the template contract and the idempotent outbox but
documented three gaps honestly: no consent store, no unsubscribe endpoint,
List-Unsubscribe never reached the transport, and no business event called
``dispatch``. This suite pins the closure of all four:

  token    sign/verify · tamper → invalid · category swap → invalid ·
           expiry honoured · transactional category refuses to mint
  prefs    GET lazy defaults · PUT partial updates · auth required ·
           links in GET point at the real token mechanism
  1-click  POST flips exactly ONE category, no session, idempotent ·
           GET only validates (prefetch-safe, no state change) ·
           expired/invalid tokens → honest 4xx words
  dispatch consent gate suppresses engagement for opted-out user ·
           transactional ignores the switch · unsubscribe_url injected ·
           RFC 8058 headers passed to the transport
  event    checkout writes ONE outbox row per order (idempotent) with
           honest status when the transport is down
"""
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.models.email_outbox import EmailOutbox
from backend.app.models.email_preference import EmailPreference
from backend.app.models.user import User
from backend.app.services import email_consent
from backend.app.services.email_outbox import dispatch
from backend.tests.conftest import TestingSessionLocal


def _login(client: TestClient, email: str, password: str = "Password123!") -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(client: TestClient, email: str = "shopper@confit.io") -> dict:
    return {"Authorization": f"Bearer {_login(client, email)}"}


def _uid(email: str) -> int:
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Token mechanics
# ---------------------------------------------------------------------------
class TestUnsubscribeToken:
    def test_roundtrip(self):
        t = email_consent.make_unsubscribe_token(7, "engagement")
        assert email_consent.verify_unsubscribe_token(t) == (7, "engagement")

    def test_tampered_signature_rejected(self):
        t = email_consent.make_unsubscribe_token(7, "engagement")
        bad = t[:-4] + ("0000" if t[-4:] != "0000" else "1111")
        try:
            email_consent.verify_unsubscribe_token(bad)
            raise AssertionError("tampered token verified")
        except email_consent.UnsubscribeTokenError:
            pass

    def test_payload_swap_breaks_hmac(self):
        """Swapping the signed payload between two tokens must fail."""
        t_a = email_consent.make_unsubscribe_token(1, "engagement")
        t_b = email_consent.make_unsubscribe_token(2, "marketing")
        frankenstein = f"{t_a.rsplit('.', 1)[0]}.{t_b.rsplit('.', 1)[1]}"
        try:
            email_consent.verify_unsubscribe_token(frankenstein)
            raise AssertionError("cross-signed token verified")
        except email_consent.UnsubscribeTokenError:
            pass

    def test_expiry_honoured(self):
        t = email_consent.make_unsubscribe_token(7, "marketing", ttl_seconds=1)
        with patch("backend.app.services.email_consent.time") as faketime:
            faketime.time.return_value = time.time() + 5
            try:
                email_consent.verify_unsubscribe_token(t)
                raise AssertionError("expired token verified")
            except email_consent.UnsubscribeTokenExpired:
                pass

    def test_transactional_has_no_switch(self):
        try:
            email_consent.make_unsubscribe_token(7, "transactional")
            raise AssertionError("transactional minted an unsubscribe token")
        except email_consent.UnsubscribeTokenError:
            pass


# ---------------------------------------------------------------------------
# Preferences endpoints
# ---------------------------------------------------------------------------
class TestPreferencesEndpoints:
    def test_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/email/preferences").status_code == 401
        assert client.put(
            "/api/v1/email/preferences", json={"marketing": False}
        ).status_code == 401

    def test_lazy_defaults_all_allowed(self, client: TestClient):
        body = client.get("/api/v1/email/preferences", headers=_auth(client)).json()
        assert body["engagement"] is True
        assert body["marketing"] is True
        assert body["categories"]["transactional"]["switchable"] is False
        # the links are REAL tokens for this very user
        token = body["links"]["marketing"].split("token=")[1]
        uid, cat = email_consent.verify_unsubscribe_token(token)
        assert cat == "marketing"
        assert uid == _uid("shopper@confit.io")

    def test_put_partial_update(self, client: TestClient):
        h = _auth(client)
        body = client.put(
            "/api/v1/email/preferences", json={"marketing": False}, headers=h
        ).json()
        assert body["marketing"] is False
        assert body["engagement"] is True  # untouched
        body = client.put(
            "/api/v1/email/preferences", json={"marketing": True}, headers=h
        ).json()
        assert body["marketing"] is True

    def test_put_empty_body_rejected(self, client: TestClient):
        r = client.put("/api/v1/email/preferences", json={}, headers=_auth(client))
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# One-click unsubscribe
# ---------------------------------------------------------------------------
class TestOneClickUnsubscribe:
    def test_get_validates_without_state_change(self, client: TestClient):
        uid = _uid("shopper@confit.io")
        t = email_consent.make_unsubscribe_token(uid, "engagement")
        body = client.get(f"/api/v1/email/unsubscribe?token={t}").json()
        assert body == {"valid": True, "category": "engagement"}
        # GET must NOT have unsubscribed (prefetch safety)
        prefs = client.get("/api/v1/email/preferences", headers=_auth(client)).json()
        assert prefs["engagement"] is True

    def test_post_flips_exactly_one_category_no_session(self, client: TestClient):
        uid = _uid("shopper@confit.io")
        t = email_consent.make_unsubscribe_token(uid, "engagement")
        r = client.post("/api/v1/email/unsubscribe", json={"token": t})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "unsubscribed"
        assert body["category"] == "engagement"
        assert body["engagement"] is False
        assert body["marketing"] is True  # untouched
        # idempotent replay — same answer, no error
        again = client.post("/api/v1/email/unsubscribe", json={"token": t})
        assert again.status_code == 200
        assert again.json()["engagement"] is False
        # restore
        client.put(
            "/api/v1/email/preferences", json={"engagement": True},
            headers=_auth(client),
        )

    def test_invalid_and_expired_tokens_honest(self, client: TestClient):
        assert client.get("/api/v1/email/unsubscribe?token=garbage").json() == {
            "valid": False, "reason": "invalid",
        }
        r = client.post("/api/v1/email/unsubscribe", json={"token": "garbage"})
        assert r.status_code == 422
        uid = _uid("shopper@confit.io")
        t = email_consent.make_unsubscribe_token(uid, "marketing", ttl_seconds=1)
        with patch("backend.app.services.email_consent.time") as faketime:
            faketime.time.return_value = time.time() + 5
            assert client.get(f"/api/v1/email/unsubscribe?token={t}").json() == {
                "valid": False, "reason": "expired",
            }
            r = client.post("/api/v1/email/unsubscribe", json={"token": t})
            assert r.status_code == 422
            assert "expired" in r.text.lower()


# ---------------------------------------------------------------------------
# dispatch(): consent gate + injected link + RFC 8058 headers
# ---------------------------------------------------------------------------
class TestDispatchConsent:
    def _clean(self, key: str):
        db = TestingSessionLocal()
        try:
            db.query(EmailOutbox).filter(EmailOutbox.event_key == key).delete()
            db.commit()
        finally:
            db.close()

    def test_opted_out_user_is_suppressed_before_render(self, client: TestClient):
        uid = _uid("shopper@confit.io")
        db = TestingSessionLocal()
        try:
            email_consent.set_preference(db, uid, "marketing", False)
            key = f"test:suppress:{time.time()}"
            with patch("backend.app.services.email_outbox.send_email") as send:
                row = dispatch(
                    db, event_key=key, template="price_drop", locale="en",
                    recipient="shopper@confit.io", user_id=uid,
                    payload={},  # would FAIL render — suppression must win first
                )
            assert row.status == "unsubscribed"
            send.assert_not_called()
            email_consent.set_preference(db, uid, "marketing", True)
        finally:
            db.close()

    def test_transactional_ignores_switches_and_sends_without_list_header(self):
        db = TestingSessionLocal()
        try:
            uid = db.query(User).first().id
            email_consent.set_preference(db, uid, "engagement", False)
            key = f"test:txn:{time.time()}"
            with patch("backend.app.services.email_outbox.send_email") as send:
                send.return_value = {"message_id": "<x@test>"}
                row = dispatch(
                    db, event_key=key, template="payment_failed", locale="en",
                    recipient="x@test.io", user_id=uid,
                    payload={
                        "order_number": "CF-1", "reason": "card declined",
                        "retry_url": "https://confit-a.vercel.app/orders/CF-1",
                    },
                )
            assert row.status == "sent"
            # transactional: NO List-Unsubscribe headers
            assert send.call_args.kwargs.get("headers") is None
            email_consent.set_preference(db, uid, "engagement", True)
        finally:
            db.close()

    def test_engagement_injects_link_and_8058_headers(self):
        db = TestingSessionLocal()
        try:
            uid = db.query(User).first().id
            key = f"test:eng:{time.time()}"
            with patch("backend.app.services.email_outbox.send_email") as send:
                send.return_value = {"message_id": "<y@test>"}
                row = dispatch(
                    db, event_key=key, template="saved_look", locale="en",
                    recipient="y@test.io", user_id=uid,
                    payload={
                        "look_name": "Monochrome Monday",
                        "look_url": "https://confit-a.vercel.app/my-looks/1",
                        # NOTE: no unsubscribe_url — dispatch must inject it
                    },
                )
            assert row.status == "sent"
            headers = send.call_args.kwargs["headers"]
            assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
            url = headers["List-Unsubscribe"].strip("<>")
            token = url.split("token=")[1]
            got_uid, cat = email_consent.verify_unsubscribe_token(token)
            assert (got_uid, cat) == (uid, "engagement")
            # the rendered footer carries the SAME link family
            assert "/email/unsubscribe?token=" in url
        finally:
            db.close()


# ---------------------------------------------------------------------------
# The wired business event: checkout → ONE outbox row per order
# ---------------------------------------------------------------------------
class TestOrderConfirmationEvent:
    def test_checkout_writes_one_idempotent_outbox_row(self, client: TestClient):
        h = {**_auth(client), "X-Session-Token": "email-evt-session-1"}
        r = client.post(
            "/api/v1/commerce/cart/items",
            json={"product_sku_id": 1, "quantity": 1},
            headers=h,
        )
        assert r.status_code in (200, 201), r.text
        with patch("backend.app.services.email_outbox.send_email") as send:
            send.return_value = {"message_id": "<order@test>"}
            r = client.post(
                "/api/v1/commerce/checkout",
                json={
                    "payment_method": "bnpl_tabby", "fulfillment_type": "bopis",
                    "bopis_store_id": 1, "recipient_name": "Email Event Test",
                    "phone": "+201001234567", "city": "Giza", "country": "EG",
                },
                headers=h,
            )
        assert r.status_code in (200, 201), r.text
        order_number = r.json()["order_number"]

        db = TestingSessionLocal()
        try:
            rows = (
                db.query(EmailOutbox)
                .filter(EmailOutbox.event_key == f"order:{order_number}:confirmation")
                .all()
            )
            assert len(rows) == 1
            row = rows[0]
            assert row.template == "order_confirmation"
            assert row.status == "sent"
            assert row.recipient == "shopper@confit.io"
            # replaying the event cannot send twice
            replay = dispatch(
                db, event_key=row.event_key, template="order_confirmation",
                locale="en", recipient=row.recipient, payload={},
            )
            assert replay.id == row.id and replay.attempts == row.attempts
        finally:
            db.close()

    def test_transport_down_is_recorded_honestly_and_order_survives(
        self, client: TestClient
    ):
        h = {**_auth(client), "X-Session-Token": "email-evt-session-2"}
        client.post(
            "/api/v1/commerce/cart/items",
            json={"product_sku_id": 1, "quantity": 1},
            headers=h,
        )
        from backend.app.services.email_service import EmailDeliveryError
        with patch("backend.app.services.email_outbox.send_email") as send:
            send.side_effect = EmailDeliveryError("SMTP 525 unauthorized IP")
            r = client.post(
                "/api/v1/commerce/checkout",
                json={
                    "payment_method": "bnpl_tabby", "fulfillment_type": "bopis",
                    "bopis_store_id": 1, "recipient_name": "Email Event Test",
                    "phone": "+201001234567", "city": "Giza", "country": "EG",
                },
                headers=h,
            )
        # the ORDER is fine — email trouble never breaks checkout
        assert r.status_code in (200, 201), r.text
        order_number = r.json()["order_number"]
        db = TestingSessionLocal()
        try:
            row = (
                db.query(EmailOutbox)
                .filter(EmailOutbox.event_key == f"order:{order_number}:confirmation")
                .first()
            )
            assert row is not None
            assert row.status == "failed"
            assert "525" in (row.last_error or "")
        finally:
            db.close()
