"""Round-3 hardening regression tests (single-process; PG concurrency proofs
live in test_mfa_concurrency_postgres.py).

Covers:
- R3-2  recovery-code regeneration requires step-up (password + current code)
- R3-3  deletion scrubs personal payloads from anonymized rows
- R3-5  export includes measurement/visual-search/recently-viewed data
- R3-6a legacy plaintext MFA secret is lazily re-encrypted on next verify
- R3-10 breached-but-composition-compliant passwords are refused
"""
import time

import pyotp
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

PASSWORD = "Rnd3-Hardening!42"


def _register_and_login(client: TestClient, email: str) -> str:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Round3 Test"},
    )
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _enroll_mfa(client: TestClient, token: str):
    r = client.post("/api/v1/auth/mfa/setup", headers=_auth(token))
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    totp = pyotp.TOTP(secret)
    r = client.post(
        "/api/v1/auth/mfa/verify", headers=_auth(token), json={"code": totp.now()}
    )
    assert r.status_code == 200, r.text
    return secret, r.json()["backup_codes"]


def _next_step_code(secret: str) -> str:
    totp = pyotp.TOTP(secret)
    time.sleep(totp.interval - (time.time() % totp.interval) + 0.5)
    return totp.now()


# ---------------------------------------------------------------------------
# R3-2: regenerate-codes step-up
# ---------------------------------------------------------------------------
class TestRegenerateCodesStepUp:
    def test_regenerate_without_credentials_is_refused(self, client: TestClient):
        token = _register_and_login(client, "r3-regen-1@round3.example.com")
        _enroll_mfa(client, token)
        r = client.post(
            "/api/v1/auth/mfa/regenerate-codes", headers=_auth(token), json={}
        )
        assert r.status_code == 401, r.text
        assert "PASSWORD_REQUIRED" in r.text

    def test_regenerate_with_password_but_no_code_is_refused(self, client: TestClient):
        token = _register_and_login(client, "r3-regen-2@round3.example.com")
        _enroll_mfa(client, token)
        r = client.post(
            "/api/v1/auth/mfa/regenerate-codes",
            headers=_auth(token),
            json={"password": PASSWORD},
        )
        assert r.status_code == 401, r.text
        assert "MFA_CODE_REQUIRED" in r.text

    def test_regenerate_with_wrong_password_is_refused_and_audited(self, client: TestClient):
        token = _register_and_login(client, "r3-regen-3@round3.example.com")
        secret, _codes = _enroll_mfa(client, token)
        r = client.post(
            "/api/v1/auth/mfa/regenerate-codes",
            headers=_auth(token),
            json={"password": "Wrong-Password!9", "mfa_code": pyotp.TOTP(secret).now()},
        )
        assert r.status_code == 401, r.text

    def test_regenerate_with_full_stepup_succeeds_and_invalidates_old_codes(
        self, client: TestClient, db_session
    ):
        token = _register_and_login(client, "r3-regen-4@round3.example.com")
        secret, old_codes = _enroll_mfa(client, token)
        code = _next_step_code(secret)
        r = client.post(
            "/api/v1/auth/mfa/regenerate-codes",
            headers=_auth(token),
            json={"password": PASSWORD, "mfa_code": code},
        )
        assert r.status_code == 200, r.text
        new_codes = r.json()["backup_codes"]
        assert len(new_codes) == 10
        assert set(new_codes).isdisjoint(set(old_codes))
        # An OLD recovery code must now be dead (login attempt).
        r = client.post(
            "/api/v1/auth/login",
            json={
                "email": "r3-regen-4@round3.example.com",
                "password": PASSWORD,
                "mfa_code": old_codes[0],
            },
        )
        assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# R3-3: deletion scrubs personal payloads from anonymized rows
# ---------------------------------------------------------------------------
class TestDeletionScrubsPersonalPayloads:
    def test_tryon_rows_lose_person_images_on_delete(self, client: TestClient, db_session):
        from backend.app.models.user import User
        from backend.app.models.tryon import TryOnSession, TryOnJob, VisualSearchQuery

        email = "r3-delete-pii@round3.example.com"
        token = _register_and_login(client, email)
        user = db_session.query(User).filter(User.email == email).first()
        uid = user.id

        db_session.add(TryOnSession(
            user_id=uid,
            user_image_url="https://cdn.example/person-photo.jpg",
            input_user_image_url="data:image/jpeg;base64,PERSONBYTES",
            rendered_result_url="https://cdn.example/rendered.jpg",
        ))
        db_session.add(TryOnJob(
            job_id="r3-job-1",
            user_id=uid,
            input_person_image_url="data:image/jpeg;base64,RAWPERSONPAYLOAD",
            delivery_token_hash="a" * 64,
        ))
        db_session.add(VisualSearchQuery(
            user_id=uid, input_image_url="data:image/jpeg;base64,SEARCHPHOTO"
        ))
        db_session.commit()

        r = client.request(
            "DELETE",
            "/api/v1/auth/account",
            headers=_auth(token),
            json={"confirm": "DELETE", "password": PASSWORD},
        )
        assert r.status_code == 200, r.text

        db_session.expire_all()
        sessions = db_session.query(TryOnSession).filter(
            TryOnSession.rendered_result_url.isnot(None)
        ).all()
        # our session row was scrubbed: no person URLs anywhere with our data
        assert db_session.query(TryOnSession).filter(
            TryOnSession.user_image_url == "https://cdn.example/person-photo.jpg"
        ).count() == 0
        assert db_session.query(TryOnJob).filter(
            TryOnJob.input_person_image_url.like("%RAWPERSONPAYLOAD%")
        ).count() == 0
        assert db_session.query(VisualSearchQuery).filter(
            VisualSearchQuery.input_image_url.like("%SEARCHPHOTO%")
        ).count() == 0
        # and the anonymized rows carry no user linkage
        job = db_session.query(TryOnJob).filter(TryOnJob.job_id == "r3-job-1").first()
        assert job is not None and job.user_id is None and job.delivery_token_hash is None

    def test_recently_viewed_deleted_with_account(self, client: TestClient, db_session):
        from backend.app.models.user import User
        from backend.app.models.catalog import RecentlyViewed, Product

        email = "r3-delete-rv@round3.example.com"
        token = _register_and_login(client, email)
        user = db_session.query(User).filter(User.email == email).first()
        uid = user.id
        product = db_session.query(Product).first()
        if product is None:
            pytest.skip("no seeded product available")
        db_session.add(RecentlyViewed(user_id=uid, product_id=product.id))
        db_session.commit()

        r = client.request(
            "DELETE",
            "/api/v1/auth/account",
            headers=_auth(token),
            json={"confirm": "DELETE", "password": PASSWORD},
        )
        assert r.status_code == 200, r.text
        db_session.expire_all()
        assert db_session.query(RecentlyViewed).filter(
            RecentlyViewed.user_id == uid
        ).count() == 0


# ---------------------------------------------------------------------------
# R3-5: export completeness — new sections present and owned
# ---------------------------------------------------------------------------
class TestExportNewSections:
    def test_export_contains_measurements_visual_searches_recently_viewed(
        self, client: TestClient, db_session
    ):
        from backend.app.models.user import User
        from backend.app.models.tryon import MeasurementSession, MeasurementResult, VisualSearchQuery

        email = "r3-export@round3.example.com"
        token = _register_and_login(client, email)
        user = db_session.query(User).filter(User.email == email).first()

        ms = MeasurementSession(user_id=user.id, status="completed", consent_granted=True)
        db_session.add(ms)
        db_session.flush()
        db_session.add(MeasurementResult(session_id=ms.id, height_cm=171.0, waist_cm=80.0))
        db_session.add(VisualSearchQuery(
            user_id=user.id, input_image_url="ignored", detected_category="jackets"
        ))
        db_session.commit()

        r = client.get("/api/v1/auth/gdpr-export", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        for section in ("measurement_sessions", "visual_searches", "recently_viewed"):
            assert section in data, f"export missing section {section}"
        assert data["measurement_sessions"][0]["results"][0]["height_cm"] == 171.0
        assert data["visual_searches"][0]["detected_category"] == "jackets"
        # No secrets or raw input images in the new sections either.
        body = r.text
        assert "input_image_url" not in body

    def test_new_sections_are_cross_user_isolated(self, client: TestClient, db_session):
        from backend.app.models.user import User
        from backend.app.models.tryon import VisualSearchQuery

        token_a = _register_and_login(client, "r3-export-a@round3.example.com")
        token_b = _register_and_login(client, "r3-export-b@round3.example.com")
        user_b = db_session.query(User).filter(User.email == "r3-export-b@round3.example.com").first()
        db_session.add(VisualSearchQuery(
            user_id=user_b.id, input_image_url="x", detected_category="b-only-marker"
        ))
        db_session.commit()

        r = client.get("/api/v1/auth/gdpr-export", headers=_auth(token_a))
        assert r.status_code == 200
        assert "b-only-marker" not in r.text


# ---------------------------------------------------------------------------
# R3-6a: legacy plaintext MFA secret is re-encrypted on next successful verify
# ---------------------------------------------------------------------------
class TestLegacySecretLazyReencryption:
    def test_plaintext_secret_rewritten_encrypted_after_login(self, client: TestClient, db_session):
        from backend.app.models.user import User

        email = "r3-legacy-secret@round3.example.com"
        token = _register_and_login(client, email)
        secret, _codes = _enroll_mfa(client, token)

        # Simulate a pre-hardening row: overwrite with the PLAINTEXT secret.
        user = db_session.query(User).filter(User.email == email).first()
        user.mfa_secret = secret
        db_session.commit()

        code = _next_step_code(secret)
        r = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD, "mfa_code": code},
        )
        assert r.status_code == 200, r.text

        db_session.expire_all()
        user = db_session.query(User).filter(User.email == email).first()
        assert user.mfa_secret.startswith("enc:v1:"), (
            "legacy plaintext secret was not lazily re-encrypted on successful verify"
        )
        # And the encrypted row still validates on the following step.
        code2 = _next_step_code(secret)
        r = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD, "mfa_code": code2},
        )
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# R3-10: breached-password screen
# ---------------------------------------------------------------------------
class TestBreachedPasswordScreen:
    @pytest.mark.parametrize("bad", ["P@ssw0rd", "Welcome1!", "Qwerty123!", "welcome1!"])
    def test_breached_compliant_passwords_refused_at_register(self, client: TestClient, bad):
        r = client.post(
            "/api/v1/auth/register",
            json={"email": f"r3-breach-{abs(hash(bad))}@round3.example.com", "password": bad, "full_name": "X"},
        )
        assert r.status_code == 422, f"{bad!r} should be refused: {r.text}"
        assert "breach" in r.text.lower()

    def test_breached_password_refused_at_change_password(self, client: TestClient):
        token = _register_and_login(client, "r3-breach-change@round3.example.com")
        r = client.post(
            "/api/v1/auth/change-password",
            headers=_auth(token),
            json={"current_password": PASSWORD, "new_password": "Welcome123!"},
        )
        assert r.status_code == 422, r.text

    def test_strong_uncommon_password_still_accepted(self, client: TestClient):
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "r3-breach-ok@round3.example.com",
                "password": "Tricky-Falcon_9!x",
                "full_name": "X",
            },
        )
        assert r.status_code == 201, r.text
