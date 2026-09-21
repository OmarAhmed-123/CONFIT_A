"""Storage backend contract — the production (S3/R2) backend exercised end to
end with an in-memory S3 client injected in place of boto3's network client.

What this proves (behaviourally, not by reading source):
  * store() returns a URL the same backend can map back to its key
    (``key_for_url`` is the exact inverse of ``store`` for every URL style:
    custom public base, R2 endpoint, AWS virtual-host);
  * URLs the backend did not issue (seeded Unsplash images, other buckets,
    path traversal) are never treated as owned -> never deleted/read;
  * read()/delete() go through the client; delete of an owned object works;
  * the wardrobe service cleans up S3 objects through the backend (the old
    implementation only understood ``/uploads/`` and orphaned every S3 object).
"""
from __future__ import annotations

import pytest

from backend.app.core.config import settings
from backend.app.services import storage_service
from backend.app.services.storage_service import LocalStorageBackend, S3StorageBackend


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict] = []

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = Body
        self.put_calls.append({"Bucket": Bucket, "Key": Key, **kwargs})

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def get_object(self, Bucket, Key):
        import io
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


@pytest.fixture
def s3(monkeypatch):
    """Real S3StorageBackend bound to the fake client (boto3.client patched)."""
    fake = _FakeS3Client()
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "s3", raising=False)
    monkeypatch.setattr(settings, "AWS_S3_BUCKET", "confit-media", raising=False)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "AKIA_TEST", raising=False)
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "secret_test", raising=False)
    monkeypatch.setattr(settings, "AWS_REGION", "eu-central-1", raising=False)
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None, raising=False)
    monkeypatch.setattr(settings, "S3_PUBLIC_URL_BASE", None, raising=False)
    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)
    storage_service.reset_storage()
    yield fake
    storage_service.reset_storage()


@pytest.mark.parametrize(
    "public_base,endpoint,expected_prefix",
    [
        (None, None, "https://confit-media.s3.eu-central-1.amazonaws.com/"),
        (None, "https://acct.r2.cloudflarestorage.com", "https://acct.r2.cloudflarestorage.com/confit-media/"),
        ("https://cdn.confit.app/", None, "https://cdn.confit.app/"),
    ],
    ids=["aws-virtual-host", "r2-endpoint", "custom-public-base"],
)
def test_store_url_round_trips_to_key(s3, monkeypatch, public_base, endpoint, expected_prefix):
    monkeypatch.setattr(settings, "S3_PUBLIC_URL_BASE", public_base, raising=False)
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", endpoint, raising=False)
    backend = S3StorageBackend()
    url = backend.store("wardrobe/7/abc.jpg", b"\xff\xd8bytes")
    assert url == expected_prefix + "wardrobe/7/abc.jpg"
    assert ("confit-media", "wardrobe/7/abc.jpg") in s3.objects
    assert backend.key_for_url(url) == "wardrobe/7/abc.jpg"
    assert backend.owns_url(url)
    assert backend.exists("wardrobe/7/abc.jpg")
    assert backend.read("wardrobe/7/abc.jpg") == b"\xff\xd8bytes"
    assert backend.delete("wardrobe/7/abc.jpg") is True
    assert not backend.exists("wardrobe/7/abc.jpg")


@pytest.mark.parametrize("foreign", [
    "https://images.unsplash.com/photo-1507679799987",
    "https://other-bucket.s3.eu-central-1.amazonaws.com/wardrobe/7/abc.jpg",
    "https://confit-media.s3.eu-central-1.amazonaws.com/../secrets",
    "/uploads/wardrobe/7/abc.jpg",
    "", None,
])
def test_foreign_urls_are_not_owned(s3, foreign):
    backend = S3StorageBackend()
    assert backend.key_for_url(foreign) is None
    assert backend.owns_url(foreign) is False


def test_local_backend_owns_only_its_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_LOCAL_DIR", str(tmp_path), raising=False)
    backend = LocalStorageBackend()
    url = backend.store("wardrobe/1/x.png", b"png")
    assert url == "/uploads/wardrobe/1/x.png"
    assert backend.key_for_url(url) == "wardrobe/1/x.png"
    assert backend.key_for_url("/uploads/../etc/passwd") is None
    assert backend.key_for_url("https://images.unsplash.com/x.jpg") is None
    assert backend.delete("wardrobe/1/x.png") is True


def test_production_storage_gate_accepts_configured_s3(s3):
    """With bucket + credentials + boto3 present, uploads are no longer 501."""
    status = storage_service.storage_status()
    assert status["production_grade"] is True
    assert status["client_installed"] is True
    backend = storage_service.require_production_storage("wardrobe_upload")
    assert isinstance(backend, S3StorageBackend)


def test_wardrobe_cleanup_deletes_s3_object_and_ignores_external(s3):
    from backend.app.services.wardrobe_service import WardrobeService

    backend = storage_service.get_storage()
    url = backend.store("wardrobe/9/gone.jpg", b"jpg")
    svc = WardrobeService.__new__(WardrobeService)  # cleanup does not need a DB session
    svc._delete_owned_image(url)
    assert ("confit-media", "wardrobe/9/gone.jpg") not in s3.objects
    # external/seeded image: nothing happens, nothing raises
    svc._delete_owned_image("https://images.unsplash.com/photo-1")


def test_wardrobe_analysis_reads_bytes_back_through_storage(s3):
    from backend.app.services.wardrobe_service import WardrobeService

    backend = storage_service.get_storage()
    url = backend.store("wardrobe/9/analyze.png", b"\x89PNGfake")
    svc = WardrobeService.__new__(WardrobeService)
    ref = svc._image_ref_for_analysis(url)
    assert ref.startswith("data:image/png;base64,")
    # an external URL is handed to the provider untouched (SSRF guard lives there)
    assert svc._image_ref_for_analysis("https://images.unsplash.com/p.jpg") == "https://images.unsplash.com/p.jpg"


# ---------------------------------------------------------------------------
# Audit closure 2026-09-21 (VTON/Photo-Match gap: "storage is local,
# production_grade=false, writable=false"). Three real defects fixed here:
#   1. the documented .env.example aliases were accepted by nothing;
#   2. objects were written unencrypted (personal photos);
#   3. /health reported storage from configuration only, so a configured but
#      unreachable bucket looked production-ready.
# ---------------------------------------------------------------------------


def test_documented_env_aliases_resolve_to_the_same_backend(monkeypatch):
    """backend/.env.example ships S3_ENDPOINT / S3_ACCESS_KEY / S3_SECRET_KEY /
    S3_BUCKET_PUBLIC. Before this fix an operator who filled in exactly that
    file still booted with production_grade=False — the aliases bound to
    fields no reader consulted."""
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "s3", raising=False)
    monkeypatch.setattr(settings, "AWS_S3_BUCKET", None, raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET", None, raising=False)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", None, raising=False)
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", None, raising=False)
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None, raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET_PUBLIC", "confit-a-media", raising=False)
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "alias-key", raising=False)
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "alias-secret", raising=False)
    monkeypatch.setattr(settings, "S3_ENDPOINT", "https://br-x.storage.neon.tech/", raising=False)
    storage_service.reset_storage()
    try:
        assert settings.s3_bucket == "confit-a-media"
        assert settings.s3_access_key == "alias-key"
        assert settings.s3_secret_key == "alias-secret"
        # trailing slash normalised — otherwise the URL prefix doubles it
        assert settings.s3_endpoint_url == "https://br-x.storage.neon.tech"
        assert storage_service.storage_status()["production_grade"] is True
        backend = storage_service.require_production_storage("wardrobe_upload")
        assert isinstance(backend, S3StorageBackend)
        assert backend.bucket == "confit-a-media"
    finally:
        storage_service.reset_storage()


def test_aws_names_still_win_over_aliases(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "s3", raising=False)
    monkeypatch.setattr(settings, "AWS_S3_BUCKET", "primary-bucket", raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET_PUBLIC", "fallback-bucket", raising=False)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "primary-key", raising=False)
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "fallback-key", raising=False)
    try:
        assert settings.s3_bucket == "primary-bucket"
        assert settings.s3_access_key == "primary-key"
    finally:
        storage_service.reset_storage()


def test_every_write_is_server_side_encrypted(s3):
    backend = S3StorageBackend()
    backend.store("wardrobe/7/private-photo.jpg", b"\xff\xd8bytes")
    call = s3.put_calls[-1]
    assert call["ServerSideEncryption"] == "AES256"
    assert call["ContentType"] == "image/jpeg"
    assert "no-store" not in call["CacheControl"]  # private cache, not a stale one


def test_encryption_is_never_silently_dropped(s3, monkeypatch):
    monkeypatch.setattr(settings, "S3_SERVER_SIDE_ENCRYPTION", "aws:kms", raising=False)
    backend = S3StorageBackend()
    backend.store("moodboard/1/x.png", b"\x89PNG")
    assert s3.put_calls[-1]["ServerSideEncryption"] == "aws:kms"


def test_live_probe_verdict_is_reported_and_gates_production_grade(s3, monkeypatch):
    """A configured bucket that cannot round-trip an object must NOT be
    reported as production grade."""
    monkeypatch.setattr(settings, "STORAGE_PROBE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "STORAGE_PROBE_TTL_SECONDS", 0.0, raising=False)
    storage_service.reset_storage()
    try:
        ok = storage_service.storage_status()
        assert ok["production_grade"] is True
        assert ok["live_probe"]["ok"] is True
        assert ok["live_probe"]["verdict"] == "ok"

        # break the bucket: every write now raises (revoked creds / wrong region)
        def _boom(**kwargs):
            raise RuntimeError("AccessDenied")
        s3.put_object = _boom
        bad = storage_service.storage_status()
        assert bad["production_grade"] is False
        assert bad["live_probe"]["ok"] is False
        assert "AccessDenied" in bad["live_probe"]["error"]
        # and the upload gate fails closed BEFORE accepting any bytes.
        # The gate only exists in production (development keeps the local
        # convenience), so the environment must be production for this to be
        # a meaningful assertion.
        monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
        from backend.app.core.exceptions import FeatureNotConfiguredError
        with pytest.raises(FeatureNotConfiguredError):
            storage_service.require_production_storage("wardrobe_upload")
    finally:
        storage_service.reset_storage()


def test_probe_cache_is_bounded_by_ttl(s3, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_PROBE_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "STORAGE_PROBE_TTL_SECONDS", 300.0, raising=False)
    storage_service.reset_storage()
    try:
        first = storage_service.probe_storage(force=True)
        before = len(s3.put_calls)
        storage_service.probe_storage()          # cached -> no new network call
        assert len(s3.put_calls) == before
        storage_service.probe_storage(force=True)  # forced -> new call
        assert len(s3.put_calls) == before + 1
        assert first["ok"] is True
    finally:
        storage_service.reset_storage()


def test_probe_never_raises_when_backend_is_unusable(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "s3", raising=False)
    monkeypatch.setattr(settings, "AWS_S3_BUCKET", None, raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET", None, raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET_PUBLIC", None, raising=False)
    storage_service.reset_storage()
    try:
        out = storage_service.probe_storage(force=True)
        assert out["ok"] is False
        assert "no usable storage backend" in out["error"]
    finally:
        storage_service.reset_storage()
