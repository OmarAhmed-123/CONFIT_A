"""In-app notification system — API + authorization contract.

Covers the properties that matter for a feature that connects customers and
store owners:
  * strictly per-recipient reads (no cross-user leakage);
  * cross-user acknowledgement is refused with 404 (no existence leakage);
  * unread-count / list / mark-read / mark-all-read behave correctly;
  * authentication is required;
  * there is NO client-facing create endpoint (creation is server-side only);
  * the service validates input (non-empty title, in-app relative links).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.core.exceptions import ValidationDomainError
from backend.app.services.notification_service import NotificationService
from backend.tests.conftest import TestingSessionLocal


def _register(client: TestClient, label: str):
    email = f"notif_{label}_{uuid.uuid4().hex[:8]}@confit.io"
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": f"Notif {label}",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}


def _seed(recipient_user_id: int, n: int = 1, *, type="order_status",
          title="Your order shipped", body="", link=None, data=None):
    ids = []
    db = TestingSessionLocal()
    try:
        svc = NotificationService(db)
        for i in range(n):
            row = svc.create(recipient_user_id, type, f"{title} #{i}", body, link=link, data=data)
            ids.append(row.id)
    finally:
        db.close()
    return ids


# ─────────────────────────── owner scoping / IDOR ───────────────────────────

def test_notifications_are_strictly_per_recipient(client: TestClient):
    a_id, a_h = _register(client, "a")
    b_id, b_h = _register(client, "b")
    _seed(a_id, 3)

    # A sees its own three; B sees none.
    assert client.get("/api/v1/notifications/unread-count", headers=a_h).json()["unread_count"] == 3
    assert client.get("/api/v1/notifications/unread-count", headers=b_h).json()["unread_count"] == 0

    a_list = client.get("/api/v1/notifications", headers=a_h).json()
    assert len(a_list["items"]) == 3
    b_list = client.get("/api/v1/notifications", headers=b_h).json()
    assert b_list["items"] == [] and b_list["unread_count"] == 0


def test_cross_user_cannot_acknowledge_anothers_notification(client: TestClient):
    a_id, a_h = _register(client, "own")
    b_id, b_h = _register(client, "intruder")
    (nid,) = _seed(a_id, 1)

    # Intruder B cannot mark A's notification read -> 404 (no existence leak).
    res = client.post(f"/api/v1/notifications/{nid}/read", headers=b_h)
    assert res.status_code == 404, res.text

    # It is still unread for the real owner, who CAN acknowledge it.
    assert client.get("/api/v1/notifications/unread-count", headers=a_h).json()["unread_count"] == 1
    ok = client.post(f"/api/v1/notifications/{nid}/read", headers=a_h)
    assert ok.status_code == 200 and ok.json()["read"] is True
    assert client.get("/api/v1/notifications/unread-count", headers=a_h).json()["unread_count"] == 0


# ─────────────────────────── behaviour ───────────────────────────

def test_list_is_newest_first_and_keyset_paginated(client: TestClient):
    a_id, a_h = _register(client, "page")
    _seed(a_id, 5)
    first = client.get("/api/v1/notifications?limit=2", headers=a_h).json()
    assert len(first["items"]) == 2
    assert first["items"][0]["id"] > first["items"][1]["id"]  # newest first
    assert first["next_before_id"] == first["items"][1]["id"]
    second = client.get(
        f"/api/v1/notifications?limit=2&before_id={first['next_before_id']}", headers=a_h
    ).json()
    assert len(second["items"]) == 2
    assert second["items"][0]["id"] < first["items"][1]["id"]


def test_unread_only_filter(client: TestClient):
    a_id, a_h = _register(client, "unread")
    ids = _seed(a_id, 3)
    client.post(f"/api/v1/notifications/{ids[0]}/read", headers=a_h)
    unread = client.get("/api/v1/notifications?unread_only=true", headers=a_h).json()
    assert len(unread["items"]) == 2 and unread["unread_count"] == 2


def test_mark_all_read(client: TestClient):
    a_id, a_h = _register(client, "all")
    _seed(a_id, 4)
    res = client.post("/api/v1/notifications/read-all", headers=a_h)
    assert res.status_code == 200 and res.json()["updated"] == 4
    assert client.get("/api/v1/notifications/unread-count", headers=a_h).json()["unread_count"] == 0
    # Idempotent: a second call updates nothing.
    assert client.post("/api/v1/notifications/read-all", headers=a_h).json()["updated"] == 0


def test_mark_read_is_idempotent(client: TestClient):
    a_id, a_h = _register(client, "idem")
    (nid,) = _seed(a_id, 1)
    assert client.post(f"/api/v1/notifications/{nid}/read", headers=a_h).json()["read"] is True
    assert client.post(f"/api/v1/notifications/{nid}/read", headers=a_h).json()["read"] is True


# ─────────────────────────── auth + abuse surface ───────────────────────────

def test_requires_authentication(client: TestClient):
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.get("/api/v1/notifications/unread-count").status_code == 401
    assert client.post("/api/v1/notifications/read-all").status_code == 401


def test_there_is_no_client_create_endpoint(client: TestClient):
    """Creation is server-side only; a client POST to the collection must not
    create a notification (no spam vector)."""
    _, a_h = _register(client, "nocreate")
    res = client.post("/api/v1/notifications", headers=a_h, json={
        "recipient_user_id": 1, "type": "system", "title": "spam", "body": "x",
    })
    assert res.status_code in (404, 405), res.text  # no such route / method
    assert res.status_code != 201


# ─────────────────────────── service validation (unit) ───────────────────────────

def test_service_rejects_empty_title_and_offsite_link():
    a_id, _ = None, None
    db = TestingSessionLocal()
    try:
        svc = NotificationService(db)
        # a real recipient id is needed; reuse user 1 from the seed, or create a row-less check
        with pytest.raises(ValidationDomainError):
            svc.create(1, "system", "   ")  # empty title
        with pytest.raises(ValidationDomainError):
            svc.create(1, "system", "ok", link="https://evil.example.com")  # off-site link
    finally:
        db.rollback()
        db.close()


def test_service_clamps_unknown_type_and_serialises_data(client: TestClient):
    a_id, a_h = _register(client, "typ")
    _seed(a_id, 1, type="totally-unknown-type", data={"order_id": 42, "n": 3})
    item = client.get("/api/v1/notifications", headers=a_h).json()["items"][0]
    assert item["type"] == "system"            # unknown type clamped, not 500
    assert item["data"] == {"order_id": 42, "n": 3}
