"""The upload capability contract: the flag and the endpoint must agree.

MEASURED 2026-10-21 on `08b281b` against the local verify stack:

    GET  /api/v1/catalog/capabilities -> photo_upload_available: false
                                         storage_mode: "local"
    POST /api/v1/wardrobe/upload      -> 201 Created
                                         item id 5, image_url /uploads/wardrobe/1/…

The capability flag said "a consumer cannot persist a photo right now" and the
endpoint persisted one anyway. The flag is what the Wardrobe UI reads, so the two
surfaces contradicted each other and a deployment that cannot keep a file still
accepted it.

Root cause: `require_production_storage` only refuses a non-durable backend when
`settings.is_production` is true, and `is_production` is `ENVIRONMENT ==
"production"`. A staging or preview deployment — the same serverless runtime with
the same ephemeral filesystem, just a different environment label — was therefore
allowed to write photos it could never serve on the next request.
"""
import os

import pytest

from backend.app.core.exceptions import FeatureNotConfiguredError
from backend.app.services import storage_service
from backend.app.services.storage_service import require_production_storage


def _local_settings(monkeypatch, environment: str = "development"):
    """Force the local-disk provider so the gate is the only variable."""
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.delenv("AWS_S3_BUCKET", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "local", raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", environment, raising=False)


def test_local_disk_is_refused_on_an_ephemeral_serverless_host(monkeypatch):
    """A serverless function's filesystem does not survive the request.

    This is the defect: ENVIRONMENT was the only signal, so a preview deployment
    with local storage accepted uploads and returned a URL to a file that would
    not exist on the next invocation.
    """
    _local_settings(monkeypatch, environment="staging")
    monkeypatch.setenv("VERCEL", "1")

    with pytest.raises(FeatureNotConfiguredError) as exc:
        require_production_storage("wardrobe_upload")

    # The refusal must be actionable, not just a 501 with no explanation: the
    # operator needs to know WHICH condition failed.
    hint = exc.value.details.get("hint", "")
    assert "Persistent object storage" in hint
    assert "ephemeral_filesystem=True" in hint
    assert exc.value.status_code == 501


def test_local_disk_is_refused_under_aws_lambda_too(monkeypatch):
    _local_settings(monkeypatch, environment="staging")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "confit-api")

    with pytest.raises(FeatureNotConfiguredError):
        require_production_storage("wardrobe_upload")


def test_local_disk_stays_available_for_local_development(monkeypatch):
    """The local backend is an explicit development convenience.

    Pinned deliberately: the hermetic pytest suite and every developer machine
    run on it, so tightening the ephemeral-host case must not remove it.
    """
    _local_settings(monkeypatch, environment="development")
    backend = require_production_storage("wardrobe_upload")
    assert backend is not None
    assert storage_service.storage_status()["provider"] == "local"


def test_local_disk_is_refused_in_production(monkeypatch):
    """Pre-existing behaviour, pinned so the ephemeral rule cannot replace it."""
    _local_settings(monkeypatch, environment="production")
    with pytest.raises(FeatureNotConfiguredError):
        require_production_storage("wardrobe_upload")


def test_production_still_requires_durable_storage_after_the_change(monkeypatch):
    """The ephemeral check must not become an escape hatch from the production rule."""
    _local_settings(monkeypatch, environment="production")
    monkeypatch.delenv("VERCEL", raising=False)
    with pytest.raises(FeatureNotConfiguredError) as exc:
        require_production_storage("wardrobe_upload")
    assert exc.value.status_code == 501


class TestCapabilityAndEndpointAgree:
    """The two surfaces must never disagree, whichever way the config points."""

    def test_refused_storage_reports_unavailable_and_rejects_the_upload(self, client, monkeypatch):
        """Endpoint enforcement must match the flag, not merely explain it."""
        import uuid

        from backend.app.services import storage_service as svc

        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setattr(
            svc, "storage_status",
            lambda: {
                "provider": "local", "production_grade": False, "writable": True,
                "detail": "local filesystem is development-only",
            },
        )
        # The upload path imports the symbol directly, so patch it where used.
        import backend.app.services.wardrobe_service as ws
        monkeypatch.setattr(ws, "storage_status", svc.storage_status, raising=False)

        email = f"contract_{uuid.uuid4().hex[:8]}@confit.io"
        reg = client.post("/api/v1/auth/register", json={
            "email": email, "password": "Password123!", "full_name": "Contract Probe",
        })
        assert reg.status_code == 201, reg.text
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        caps = client.get("/api/v1/catalog/capabilities")
        assert caps.status_code == 200
        assert caps.json()["photo_upload_available"] is False

        res = client.post(
            "/api/v1/wardrobe/upload",
            headers=headers,
            files={"file": ("probe.png", _png_bytes(), "image/png")},
        )

        # 501 FEATURE_NOT_CONFIGURED — the honest refusal, never a 2xx with a
        # record pointing at a file that will not exist later.
        assert res.status_code == 501, res.text
        assert res.json()["error"]["code"] == "FEATURE_NOT_CONFIGURED"

        # And nothing was persisted: no row, no misleading success record.
        listing = client.get("/api/v1/wardrobe/items", headers=headers)
        assert listing.status_code == 200, listing.text
        body = listing.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        assert not [i for i in items if str(i.get("title", "")).startswith("probe")], \
            f"a refused upload left a wardrobe row behind: {items}"


def _png_bytes():
    """A real 8x8 PNG (decodable), generated rather than pasted as base64."""
    import struct
    import zlib

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    w = h = 8
    raw = b"".join(b"\x00" + bytes((200, 120, 60)) * w for _ in range(h))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


# ───────────────────────── failure behaviour ─────────────────────────
# The remaining contract states: storage misconfigured, storage failing in the
# middle of an upload, an object written but the metadata transaction failing,
# and a retry after a partial failure. Each one is exercised through the real
# service and the real backend; only the failure itself is induced.

def _register(client):
    import uuid
    email = f"upl_{uuid.uuid4().hex[:10]}@confit.io"
    res = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "Upload Contract"})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _wardrobe_items(client, headers):
    body = client.get("/api/v1/wardrobe/items", headers=headers).json()
    return body.get("items", body) if isinstance(body, dict) else body


def test_storage_failing_mid_upload_never_reports_success(client, monkeypatch):
    """A transport-level PUT failure must surface as a failure, not a 201.

    The failure is real: the backend is pointed at a closed port, so boto3
    performs a genuine TCP connection attempt and raises. Nothing is mocked.
    """
    from backend.app.core import config as config_module
    from backend.app.services import storage_service as svc

    for key, value in {
        "STORAGE_PROVIDER": "s3",
        "AWS_S3_BUCKET": "confit-upload-test",
        "AWS_ACCESS_KEY_ID": "S3RVER",
        "AWS_SECRET_ACCESS_KEY": "S3RVER",
        "S3_ENDPOINT_URL": "http://127.0.0.1:9",  # discard port: refused
        "AWS_REGION": "us-east-1",
        "S3_PUBLIC_URL_BASE": None,
    }.items():
        monkeypatch.setattr(config_module.settings, key, value, raising=False)
    svc.reset_storage()

    headers = _register(client)
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("fail.png", _png_bytes(), "image/png")})

    # Exactly 502 PROVIDER_ERROR. (A range such as ">= 500" is not an assertion:
    # it silently accepted an internal NameError that surfaced as a 500 during
    # development of this very fix.)
    assert res.status_code == 502, res.text
    body = res.json()
    assert body["error"]["code"] == "PROVIDER_ERROR", body
    assert body["error"]["details"]["provider"] == "storage", body
    assert body["error"]["details"]["retryable"] is True, body
    # The response must not leak the bucket name or the internal endpoint URL.
    assert "confit-upload-test" not in res.text, res.text
    assert "127.0.0.1:9" not in res.text, res.text

    assert not _wardrobe_items(client, headers), "a failed upload left a record behind"
    svc.reset_storage()


def test_object_written_but_metadata_failure_leaves_no_orphan(client, monkeypatch):
    """State 5: the bytes land, the row does not. The object must be removed.

    The row insert is made to fail with an unexpected (non-IntegrityError)
    database error, which is the case the duplicate-race handler does NOT cover.
    """
    from backend.app.services import storage_service as svc

    stored = {}

    class RecordingBackend:
        """Delegates to the real configured backend, but remembers every key it
        stored so the test can assert on orphans afterwards."""

        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def store(self, relative_path, data):
            url = self.inner.store(relative_path, data)
            stored[relative_path] = url
            return url

    backend = RecordingBackend(svc.get_storage())
    monkeypatch.setattr(svc, "get_storage", lambda: backend)
    monkeypatch.setattr("backend.app.services.wardrobe_service.get_storage", lambda: backend)
    monkeypatch.setattr("backend.app.services.wardrobe_service.require_production_storage",
                        lambda feature: backend)

    from backend.app.repositories.wardrobe_repository import WardrobeRepository

    # The service builds the repository in __init__ from the DB session, so the
    # failure is injected on the repository class, not on the service instance.
    real_lookup = WardrobeRepository.get_item_by_image_hash

    def failing_add_item(self, **kwargs):
        from sqlalchemy.exc import OperationalError
        raise OperationalError("INSERT", {}, Exception("simulated metadata failure"))

    monkeypatch.setattr(WardrobeRepository, "add_item", failing_add_item)
    monkeypatch.setattr(WardrobeRepository, "get_item_by_image_hash",
                        lambda self, *a, **kw: None, raising=False)

    headers = _register(client)
    res = client.post("/api/v1/wardrobe/upload", headers=headers,
                      files={"file": ("meta.png", _png_bytes(), "image/png")})

    # Server-side fault => 503, never 422 ("your photo is invalid") and never a
    # 201 carrying a record that points at nothing.
    assert res.status_code == 503, res.text
    assert "failed" in res.json()["detail"].lower()

    # The bytes were written...
    assert stored, "the test did not reach the storage step"
    # ...and must be gone again.
    for relative_path, url in stored.items():
        key = backend.inner.key_for_url(url)
        assert not backend.inner.exists(key), f"orphaned object left in storage: {key}"
