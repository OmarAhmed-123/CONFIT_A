"""Chain verification must walk APPEND order (id), never display order.

Found on the production ledger (2026-10-06): two audit rows written
concurrently carried microsecond-INVERTED timestamps (row 863's timestamp
was earlier than row 862's although 863 was appended after 862 and the
hash links by id were correct — each writer pins ``now()`` before the
advisory lock serialises the append). ``AuditTrailService.integrity`` fed
``verify_chain`` the sample in reversed-TIMESTAMP order, so the swapped
pair walked out of append order and the verifier reported
``chain_link_mismatch`` on an INTACT chain — three false positives that
made a healthy ledger look tampered.

The contract is in ``verify_chain``'s own docstring: "rows must be in
ascending id order". This test pins the fix (sort by id) by writing rows
through the REAL chained path with the inversion present at write time —
exactly as production produced it — so every HMAC is genuinely valid.
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.models.user import AuditLog, User, UserRole
from backend.tests.conftest import TestingSessionLocal


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_inverted_timestamps_do_not_fake_a_chain_break(client: TestClient):
    db = TestingSessionLocal()
    try:
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        base = datetime.now(timezone.utc).replace(tzinfo=None)
        # Later id gets the EARLIER timestamp — the production inversion.
        # The mapper listener chains + signs each row over the timestamp it
        # is written with, so both HMACs are genuinely valid.
        for i, ts in enumerate([base + timedelta(microseconds=200),
                                base + timedelta(microseconds=100)]):
            db.add(AuditLog(
                user_id=admin.id if admin else 1,
                action="ORDERING_PROBE",
                resource_type="Probe",
                resource_id=str(i),
                timestamp=ts,
            ))
            db.flush()  # separate appends, deterministic id order
        db.commit()

        rows = (
            db.query(AuditLog)
            .filter(AuditLog.action == "ORDERING_PROBE")
            .order_by(AuditLog.id.asc())
            .all()
        )
        assert len(rows) == 2
        assert rows[0].timestamp > rows[1].timestamp, "inversion must be present"
        assert rows[1].prev_hash == rows[0].entry_hash, "chain is intact by id"
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}
    body = client.get("/api/v1/admin/audit/integrity", headers=headers).json()

    chain_issues = [
        v for v in body.get("violations", [])
        if v.get("issue") in ("chain_link_mismatch", "entry_hash_mismatch")
    ]
    assert chain_issues == [], (
        "an intact chain with write-time inverted timestamps must verify "
        f"clean; got {chain_issues}"
    )
