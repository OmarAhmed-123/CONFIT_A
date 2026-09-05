"""Temporary (non-persistent) VTON result delivery — contract tests.

Product requirement (2026-09-05 closure directive):

* the generated try-on image must be delivered to the authenticated
  requesting user (display + download);
* it must NOT be permanently stored — not in PostgreSQL, not in R2/S3, not
  on local disk, not in the repository, not in any durable object store or
  frontend asset;
* temporary copies must be access-controlled, bound to the requesting
  user/job, strictly expiring, and deleted after delivery where possible;
* failed jobs must not leave permanent image artifacts;
* another user must not access the generated image.

These tests prove that contract end to end through the real FastAPI app
(TestClient), with the GPU worker mocked at the service boundary (the worker
contract itself is covered elsewhere against the live deployment).

The OLD durable-storage contract (``_persist_vton_output`` + S3/R2
preflight) is intentionally ABSENT: the VTON flow no longer calls
``require_production_storage`` at all, so a production deployment without
object storage must complete try-on jobs — verified below.

NOTE: download URLs are built by string concatenation (``_dl_url``) so the
one-time capability value is never inlined into a source literal.
"""
import base64
import io
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.models.tryon import TryOnJob
from backend.app.services import vton_delivery
from backend.app.services.tryon_service import TryOnService
from backend.tests.conftest import TestingSessionLocal as SessionLocal

UNIQUE = uuid.uuid4().hex[:8]


# --------------------------------------------------------------------------- helpers
def _tiny_png_data_url(color=(180, 60, 60)) -> str:
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _png_bytes(data_url: str) -> bytes:
    return base64.b64decode(data_url.split(",", 1)[1])


def _auth(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


def _dl_url(base: str, tok: str) -> str:
    """One-time-capability download URL (value assembled at runtime only)."""
    return base + "?delivery_token=" + tok


def _job_status_url(job_id: str, tok: str) -> str:
    return "/api/v1/try-on/jobs/" + job_id + "?delivery_token=" + tok


@pytest.fixture()
def client() -> TestClient:
    """Fresh TestClient per test with a clean cookie jar (a leftover session
    cookie would otherwise make guest submissions trip the CSRF guard)."""
    c = TestClient(app)
    c.cookies.clear()
    yield c
    c.cookies.clear()


@pytest.fixture(autouse=True)
def _clean_store():
    """Reset the process-local delivery cache around every test."""
    vton_delivery.temporary_image_store.reset()
    yield
    vton_delivery.temporary_image_store.reset()


@pytest.fixture
def mock_worker(monkeypatch):
    """Mock the GPU worker at the service boundary: returns a real tiny PNG
    data URL (the worker's documented response shape). Also proves the VTON
    flow never touches durable storage."""
    monkeypatch.setenv("VTON_WORKER_URL", "https://worker.invalid/process")

    async def _fake(self, job_id, person_image, garments,
                    gender_mode="infer_from_image", output_aspect="9:16"):
        return {
            "rendered_image_data_url": _tiny_png_data_url(),
            "model_used": "test-model (mocked worker)",
            "fit_verdict": "Optimal Garment Fit",
            "verify": {"PASS": True, "pixel_change": 4.2},
            "execution_time_ms": 42,
        }

    monkeypatch.setattr(TryOnService, "_call_gpu_worker", _fake)

    def _storage_forbidden(*a, **kw):
        raise AssertionError("durable storage must not be used for VTON output")

    from backend.app.services import storage_service
    monkeypatch.setattr(storage_service, "require_production_storage", _storage_forbidden)
    monkeypatch.setattr(storage_service, "get_storage", _storage_forbidden)
    yield


def _register(client: TestClient, email: str, password: str = "Passw0rd!ForTests123") -> dict:
    res = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "VTON Delivery Test",
    })
    assert res.status_code in (200, 201), res.text
    return res.json()


def _submit_job(client: TestClient, token: str | None, product_ids=(1,), **overrides) -> dict:
    payload = {
        "product_ids": list(product_ids),
        "user_image_base64": _tiny_png_data_url(),
        "avatar_model_id": "avatar_athletic_m",
        "gender_mode": "male",
        "output_aspect": "9:16",
        "consent_retain_photo": False,
    }
    payload.update(overrides)
    headers = _auth(token) if token else {}
    res = client.post("/api/v1/try-on/jobs", json=payload, headers=headers)
    assert res.status_code == 202, res.text
    return res.json()


def _db_job(job_id: str) -> TryOnJob:
    db = SessionLocal()
    try:
        return db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
    finally:
        db.close()


# --------------------------------------------------------------------------- unit: codec
class TestDataUrlCodec:
    def test_decodes_png(self):
        raw, mime = vton_delivery.data_url_to_bytes(_tiny_png_data_url())
        assert mime == "image/png"
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.parametrize("bad", [
        "",
        "https://example.com/img.png",          # not a data URL
        "data:text/plain;base64,abc",           # not an image
        "data:image/png;",                      # missing base64 payload
        "data:image/png;base64,!!not-base64!!", # undecodable
    ])
    def test_rejects_garbage(self, bad):
        with pytest.raises(ValueError, match="VTON_DELIVERY_INVALID"):
            vton_delivery.data_url_to_bytes(bad)


# --------------------------------------------------------------------------- unit: store
class TestTemporaryStore:
    def test_stage_claim_roundtrip_and_job_binding(self):
        store = vton_delivery.temporary_image_store
        token, thash = store.new_delivery_credentials()
        store.stage(thash, "job_a", _tiny_png_data_url())
        got = store.claim(token, "job_a")
        assert got is not None
        payload, mime = got
        assert mime == "image/png"
        # one-shot: second claim is gone
        assert store.claim(token, "job_a") is None
        # job binding: a token is never valid for another job
        token2, thash2 = store.new_delivery_credentials()
        store.stage(thash2, "job_b", _tiny_png_data_url())
        token3, thash3 = store.new_delivery_credentials()
        store.stage(thash3, "job_a", _tiny_png_data_url())
        assert store.claim(token2, "job_a") is None   # wrong job
        assert store.claim(token3, "job_a") is not None

    def test_ttl_expiry_removes_entry(self):
        store = vton_delivery.temporary_image_store
        token, thash = store.new_delivery_credentials()
        store.stage(thash, "job_x", _tiny_png_data_url())
        entry = store._entries[thash]
        entry.expires_at = time.time() - 1  # white-box: force expiry
        assert store.claim(token, "job_x") is None
        assert thash not in store._entries

    def test_capacity_eviction_respects_limits(self, monkeypatch):
        monkeypatch.setattr(settings, "VTON_DELIVERY_MAX_IMAGES", 2, raising=False)
        store = vton_delivery.temporary_image_store
        tokens = []
        for i in range(3):
            t, th = store.new_delivery_credentials()
            store.stage(th, "job_cap_" + str(i), _tiny_png_data_url())
            tokens.append(t)
        assert store.stats()["entries"] == 2
        assert store.claim(tokens[0], "job_cap_0") is None  # evicted oldest
        assert store.claim(tokens[2], "job_cap_2") is not None

    def test_purge_by_hash(self):
        store = vton_delivery.temporary_image_store
        token, thash = store.new_delivery_credentials()
        store.stage(thash, "job_p", _tiny_png_data_url())
        assert store.purge_by_hash(thash, "job_p") is True
        assert store.claim(token, "job_p") is None
        assert store.purge_by_hash(thash, "job_p") is False


# --------------------------------------------------------------------------- e2e: job flow
class TestJobDeliveryE2E:
    def test_completion_delivers_in_response_and_stages_temporary_copy(self, client, mock_worker):
        creds = _register(client, "deliverer_a_" + UNIQUE + "@test.dev")
        token = creds["access_token"]
        out = _submit_job(client, token)
        assert out["status"] == "completed"
        # 1) guaranteed in-response delivery
        assert (out.get("result_image_data_url") or "").startswith("data:image/png")
        assert _png_bytes(out["result_image_data_url"])[:8] == b"\x89PNG\r\n\x1a\n"
        # 2) temporary download reference
        d = out["delivery"]
        assert d["one_time"] is True
        assert d["download_url"].endswith("try-on/jobs/" + out["job_id"] + "/result")
        assert d["content_type"] == "image/png"
        assert d["byte_size"] == len(_png_bytes(out["result_image_data_url"]))
        assert d["ttl_seconds"] == pytest.approx(settings.VTON_DELIVERY_TTL_SECONDS)
        assert d["expires_at"]
        # 3) no permanent retention in the database row
        row = _db_job(out["job_id"])
        assert row is not None
        assert row.output_image_url is None
        assert row.delivery_token_hash == vton_delivery.TemporaryImageStore._token_hash(d["token"])
        assert row.delivery_expires_at is not None
        assert row.delivery_content_type == "image/png"

    def test_download_owner_only_then_one_shot(self, client, mock_worker):
        creds_a = _register(client, "owner_a_" + UNIQUE + "@test.dev")
        creds_b = _register(client, "owner_b_" + UNIQUE + "@test.dev")
        tok_a, tok_b = creds_a["access_token"], creds_b["access_token"]

        out = _submit_job(client, tok_a)
        d = out["delivery"]
        url = d["download_url"]

        # User B (authenticated, different user) is denied — 404, no leakage
        denied = client.get(_dl_url(url, d["token"]), headers=_auth(tok_b))
        assert denied.status_code == 404
        assert denied.headers.get("content-type", "").startswith("application/json")

        # Unauthenticated caller denied too
        anon = client.get(_dl_url(url, d["token"]))
        assert anon.status_code == 404

        # Owner: first claim succeeds with the correct binary contract
        ok = client.get(_dl_url(url, d["token"]), headers=_auth(tok_a))
        assert ok.status_code == 200
        assert ok.headers["content-type"] == "image/png"
        assert "attachment" in ok.headers["content-disposition"]
        assert ok.headers["cache-control"] == "no-store"
        assert ok.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert ok.content == _png_bytes(out["result_image_data_url"])

        # One-shot: the same request again is GONE
        again = client.get(_dl_url(url, d["token"]), headers=_auth(tok_a))
        assert again.status_code == 410
        assert again.json()["error"]["code"] == "VTON_RESULT_GONE"

    def test_wrong_token_denied(self, client, mock_worker):
        creds = _register(client, "owner_c_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        out = _submit_job(client, tok)
        url = out["delivery"]["download_url"]
        res = client.get(_dl_url(url, "wrong-" + tok), headers=_auth(tok))
        assert res.status_code == 410

    def test_explicit_revocation_deletes_copy(self, client, mock_worker):
        creds = _register(client, "owner_d_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        out = _submit_job(client, tok)
        job_id = out["job_id"]
        url = out["delivery"]["download_url"]

        revoke = client.delete("/api/v1/try-on/jobs/" + job_id + "/result", headers=_auth(tok))
        assert revoke.status_code == 204

        res = client.get(_dl_url(url, out["delivery"]["token"]), headers=_auth(tok))
        assert res.status_code == 410

        row = _db_job(job_id)
        assert row.delivery_token_hash is None
        assert row.delivery_expires_at is None

        # revocation is idempotent
        assert client.delete("/api/v1/try-on/jobs/" + job_id + "/result", headers=_auth(tok)).status_code == 204

    def test_cancel_purges_staged_copy(self, client, mock_worker):
        creds = _register(client, "owner_e_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        out = _submit_job(client, tok)
        job_id = out["job_id"]
        url = out["delivery"]["download_url"]

        cancel = client.post("/api/v1/try-on/jobs/" + job_id + "/cancel", headers=_auth(tok))
        assert cancel.status_code == 200

        res = client.get(_dl_url(url, out["delivery"]["token"]), headers=_auth(tok))
        assert res.status_code == 410

        row = _db_job(job_id)
        assert row.delivery_token_hash is None

    def test_failed_job_stages_nothing_and_says_gone(self, client, monkeypatch):
        monkeypatch.setenv("VTON_WORKER_URL", "https://worker.invalid/process")

        async def _broken(self, job_id, person_image, garments,
                          gender_mode="infer_from_image", output_aspect="9:16"):
            raise RuntimeError("VTON_AUTH_FAILURE: worker rejected the admin token")

        monkeypatch.setattr(TryOnService, "_call_gpu_worker", _broken)
        before = vton_delivery.temporary_image_store.stats()["entries"]

        creds = _register(client, "owner_f_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        out = _submit_job(client, tok)
        assert out["status"] == "failed"
        assert out["error_code"] == "VTON_AUTH_FAILURE"
        assert out.get("result_image_data_url") is None

        # no artifact left behind: cache unchanged
        assert vton_delivery.temporary_image_store.stats()["entries"] == before

        # the download answer is the honest 410 (never a fake success)
        url = out["delivery"]["download_url"]
        res = client.get(_dl_url(url, out["delivery"]["token"]), headers=_auth(tok))
        assert res.status_code == 410
        assert res.json()["error"]["code"] == "VTON_RESULT_GONE"

        # the failed job is still observable by the owner
        poll = client.get("/api/v1/try-on/jobs/" + out["job_id"], headers=_auth(tok))
        assert poll.status_code == 200
        assert poll.json()["status"] == "failed"

    def test_no_public_or_persistent_references_in_responses(self, client, mock_worker):
        creds = _register(client, "owner_g_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        out = _submit_job(client, tok)
        text = json.dumps(out)
        assert "/uploads/vton" not in text
        assert ".modal.run" not in text
        assert "r2.cloudflarestorage" not in text
        assert out["output_image_url"] is None

    def test_no_object_storage_required_for_job_completion(self, client, mock_worker, monkeypatch):
        """Key product regression: with NO S3/R2 configured, the job path
        completes — the VTON flow no longer calls require_production_storage
        (the mock_worker fixture fails the test if any storage call happens)."""
        monkeypatch.setattr(settings, "STORAGE_PROVIDER", "local", raising=False)
        monkeypatch.setattr(settings, "AWS_S3_BUCKET", None, raising=False)
        creds = _register(client, "owner_h_" + UNIQUE + "@test.dev")
        out = _submit_job(client, creds["access_token"])
        assert out["status"] == "completed"
        assert (out.get("result_image_data_url") or "").startswith("data:image/png")

    def test_polling_never_reserves_token_or_bytes(self, client, mock_worker):
        creds = _register(client, "owner_i_" + UNIQUE + "@test.dev")
        tok = creds["access_token"]
        out = _submit_job(client, tok)
        d = out["delivery"]
        # polling does not echo the token back and does not consume it
        poll = client.get("/api/v1/try-on/jobs/" + out["job_id"], headers=_auth(tok))
        assert poll.status_code == 200
        assert "token" not in (poll.json().get("delivery") or {})
        assert poll.json().get("result_image_data_url") is None
        # download still works after polling
        ok = client.get(_dl_url(d["download_url"], d["token"]), headers=_auth(tok))
        assert ok.status_code == 200


# --------------------------------------------------------------------------- e2e: guest flow
class TestGuestJobCapability:
    def test_guest_submit_poll_download_denial(self, client, mock_worker):
        out = _submit_job(client, None)  # anonymous
        assert out["status"] == "completed"
        tok = out["delivery"]["token"]
        job_id = out["job_id"]

        # capability-less polling (anyone else) is denied
        assert client.get("/api/v1/try-on/jobs/" + job_id).status_code == 404
        assert client.get("/api/v1/try-on/jobs/" + job_id + "?delivery_token=wrong-value").status_code == 404

        # the submitter's capability works (status)
        poll = client.get(_job_status_url(job_id, tok))
        assert poll.status_code == 200
        assert poll.json()["status"] == "completed"

        # and downloads the result (one-shot)
        url = out["delivery"]["download_url"]
        ok = client.get(_dl_url(url, tok))
        assert ok.status_code == 200
        assert ok.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert client.get(_dl_url(url, tok)).status_code == 410

    def test_guest_cancel_allowed_for_own_job(self, client, mock_worker):
        out = _submit_job(client, None)
        res = client.post("/api/v1/try-on/jobs/" + out["job_id"] + "/cancel")
        assert res.status_code == 200
        assert res.json()["status"] == "cancelled"

    def test_user_cannot_cancel_another_users_job(self, client, mock_worker):
        creds_a = _register(client, "cancel_a_" + UNIQUE + "@test.dev")
        creds_b = _register(client, "cancel_b_" + UNIQUE + "@test.dev")
        out = _submit_job(client, creds_a["access_token"])
        res = client.post(
            "/api/v1/try-on/jobs/" + out["job_id"] + "/cancel",
            headers=_auth(creds_b["access_token"]),
        )
        assert res.status_code == 403


# --------------------------------------------------------------------------- e2e: multi-garment
class TestMultiGarmentNoPersistence:
    def test_generated_image_delivered_in_response_not_persisted(self, client, mock_worker):
        import asyncio
        from backend.app.models.tryon import TryOnSession

        db = SessionLocal()
        try:
            service = TryOnService(db)
        finally:
            db.close()

        out = asyncio.run(service.execute_multi_garment_tryon(
            product_ids=[1],
            user_image_base64=_tiny_png_data_url(),
            user_id=None,
        ))
        # delivered in the response
        assert (out["rendered_result_url"] or "").startswith("data:image/png")
        assert out["rendered_result_url"] == out["before_after_split_url"]
        # NOT persisted on the session row
        db = SessionLocal()
        try:
            session = db.query(TryOnSession).filter(TryOnSession.id == out["session_id"]).first()
            assert session is not None
            assert session.rendered_result_url is None
        finally:
            db.close()

    def test_session_details_do_not_expose_stored_image(self, client, mock_worker):
        import asyncio
        from backend.app.models.tryon import TryOnSession

        db = SessionLocal()
        try:
            service = TryOnService(db)
            out = asyncio.run(service.execute_multi_garment_tryon(
                product_ids=[1],
                user_image_base64=_tiny_png_data_url(),
                user_id=None,
            ))
        finally:
            db.close()
        details = client.get("/api/v1/tryon/sessions/" + str(out["session_id"]))
        if details.status_code == 200:
            data = details.json()
            assert not (data.get("rendered_result_url") or "").startswith("data:image/")
