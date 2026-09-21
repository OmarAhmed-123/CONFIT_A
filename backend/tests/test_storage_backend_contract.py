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
        self.presigned_calls: list[dict] = []

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def get_object(self, Bucket, Key):
        import io
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.presigned_calls.append(
            {"operation": operation, "Params": Params, "ExpiresIn": ExpiresIn}
        )
        # Mimic SigV4 output shape: same host as the public URL + signature.
        return (
            f"https://signed.confit.test/{Params['Bucket']}/{Params['Key']}"
            f"?X-Confit-Signature=test&Expires={ExpiresIn}"
        )


@pytest.fixture
def s3(monkeypatch):
    """Real S3StorageBackend bound to the fake client (boto3.client patched).

    ``client_kwargs`` records what the backend passed to boto3.client so the
    addressing-style contract (path-style for S3-compatible stores) can be
    asserted behaviourally.
    """
    fake = _FakeS3Client()
    fake.client_kwargs: dict = {}

    def _capture(*args, **kwargs):
        fake.client_kwargs.update(kwargs)
        return fake

    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "s3", raising=False)
    monkeypatch.setattr(settings, "AWS_S3_BUCKET", "confit-media", raising=False)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "AKIA_TEST", raising=False)
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "secret_test", raising=False)
    monkeypatch.setattr(settings, "AWS_REGION", "eu-central-1", raising=False)
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None, raising=False)
    monkeypatch.setattr(settings, "AWS_ENDPOINT_URL_S3", None, raising=False)
    monkeypatch.setattr(settings, "S3_PUBLIC_URL_BASE", None, raising=False)
    monkeypatch.setattr(settings, "S3_PRESIGN_EXPIRY_SECONDS", 3600, raising=False)
    import boto3
    monkeypatch.setattr(boto3, "client", _capture)
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


# ────────────── PR1: S3-compatible addressing + private-bucket reads ─────────

def test_s3_client_uses_path_style_addressing(s3):
    """G-S3A: non-AWS S3-compatible stores (Neon Object Storage, R2) require
    path-style addressing. Without it boto3 rewrites the bucket into a
    subdomain that does not resolve and EVERY operation fails with
    NoSuchBucket — the production upload pipeline could never have worked.
    Asserted behaviourally through the kwargs the backend passes to boto3."""
    S3StorageBackend()  # (re)build the client, recording kwargs
    cfg = s3.client_kwargs.get("config")
    assert cfg is not None, "S3StorageBackend must pass a boto3 Config"
    assert cfg.s3.get("addressing_style") == "path"
    assert cfg.signature_version == "s3v4"


def test_endpoint_falls_back_to_aws_sdk_env_name(s3, monkeypatch):
    """Neon Object Storage injects AWS_ENDPOINT_URL_S3 (AWS-SDK convention);
    the app-level S3_ENDPOINT_URL must keep winning when both are set."""
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None, raising=False)
    monkeypatch.setattr(
        settings, "AWS_ENDPOINT_URL_S3",
        "https://br-xyz.storage.c-6.eu-central-1.aws.neon.tech", raising=False,
    )
    backend = S3StorageBackend()
    url = backend.store("wardrobe/1/n.jpg", b"j")
    assert url == "https://br-xyz.storage.c-6.eu-central-1.aws.neon.tech/confit-media/wardrobe/1/n.jpg"
    assert backend.key_for_url(url) == "wardrobe/1/n.jpg"

    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "https://explicit.example/s3", raising=False)
    backend2 = S3StorageBackend()
    assert backend2._url_prefix() == "https://explicit.example/s3/confit-media/"


def test_presign_url_for_owned_object(s3):
    """G-S3B: private buckets 403 anonymous GETs, so the API must hand the
    browser a signed URL. The signature is computed locally (no network) and
    the database keeps the canonical URL, not the signed one."""
    backend = S3StorageBackend()
    stored = backend.store("wardrobe/42/photo.jpg", b"\xff\xd8jpeg")
    assert "X-Confit-Signature" not in stored  # DB-facing URL stays canonical

    signed = backend.presign_url("wardrobe/42/photo.jpg")
    assert signed is not None
    assert signed != stored
    assert "wardrobe/42/photo.jpg" in signed
    assert s3.presigned_calls[-1]["operation"] == "get_object"
    assert s3.presigned_calls[-1]["Params"] == {
        "Bucket": "confit-media", "Key": "wardrobe/42/photo.jpg"
    }
    assert s3.presigned_calls[-1]["ExpiresIn"] == 3600

    # invalid paths never produce a signature
    assert backend.presign_url("../escape.jpg") is None
    assert backend.presign_url("/abs.jpg") is None


def test_storage_public_url_presigns_owned_and_passes_foreign(s3):
    """The API-boundary helper: owned S3 URLs become presigned; local-dev and
    external URLs (seeded Unsplash imagery, other buckets) pass through."""
    from backend.app.services.storage_service import storage_public_url

    backend = S3StorageBackend()
    owned = backend.store("moodboards/u5/b1/tile.png", b"png")
    out = storage_public_url(owned)
    assert out is not None and "X-Confit-Signature=test" in out

    external = "https://images.unsplash.com/photo-1507679799987"
    assert storage_public_url(external) == external
    other_bucket = "https://other-bucket.s3.eu-central-1.amazonaws.com/wardrobe/1/x.jpg"
    assert storage_public_url(other_bucket) == other_bucket
    assert storage_public_url(None) is None
    assert storage_public_url("") == ""


def test_wardrobe_serialization_presigns_owned_images(s3):
    """Wiring check: WardrobeItemOut.image_url is browser-ready when the item
    lives in S3, and seeded external URLs are untouched."""
    from types import SimpleNamespace
    from backend.app.services.wardrobe_service import WardrobeService

    svc = WardrobeService.__new__(WardrobeService)
    backend = S3StorageBackend()
    owned = backend.store("wardrobe/3/piece.jpg", b"jpeg")
    item = SimpleNamespace(
        id=3, user_id=3, title="Navy Shirt", category="Tops", subcategory=None,
        color_name="Navy", color_hex="#1B2A4A", pattern="Solid",
        brand_name="Own Collection", image_url=owned,
        ai_tags="[]", occasions="[]", secondary_colors="[]",
        seasonality="All-Season", wear_frequency="regular", wear_count=0,
        is_favorite=False, processing_status="ready", processing_error=None,
        ai_confidence=None, created_at=None,
    )
    d = svc._to_dict(item)
    assert "X-Confit-Signature=test" in d["image_url"]
    assert d["image_url"] != owned  # DB value stays canonical

    item.image_url = "https://images.unsplash.com/photo-1"
    d2 = svc._to_dict(item)
    assert d2["image_url"] == "https://images.unsplash.com/photo-1"
