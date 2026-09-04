"""VTON output durability integration.

The GPU worker returns a base64 ``data:image/...`` payload. Historically the
job / session row stored that blob verbatim in a ``Text`` column — multi-MB
string, not a durable object reference, and not authorisable/GC-able by storage
key (§18/§20 of the VTON productionization directive).

These tests prove the persistence contract of ``TryOnService._persist_vton_output``
(built on CONFIT's existing storage abstraction — no second abstraction, no
fake backend):

  * a real ``data:image/png;base64,`` payload is decoded and written to the
    configured storage; the returned reference is owned by the backend and the
    bytes round-trip via ``read`` / ``key_for_url``;
  * external / caller-authored URLs are left untouched and never treated as
    owned (so they are never deleted or read through storage);
  * in production without a durable backend, the call fails closed with
    ``FeatureNotConfiguredError`` (HTTP 501) *before* any bytes are accepted;
  * with a real (S3) backend contract the object is written to the bucket and the
    public URL round-trips.

Tests use the local/S3 backends directly (as ``test_storage_backend_contract``
does), so no GPU worker, no credential and no network is required.
"""
import base64
import io

import pytest
from PIL import Image

from backend.app.core.config import settings
from backend.app.services import storage_service
from backend.app.services.storage_service import FeatureNotConfiguredError
from backend.app.services.tryon_service import TryOnService


def _tiny_png_data_url(color=(180, 60, 60)) -> str:
    img = Image.new("RGB", (32, 32), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    """Local backend only — no network, no S3 client."""
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "local", raising=False)
    monkeypatch.setattr(settings, "STORAGE_LOCAL_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)
    storage_service.reset_storage()
    yield storage_service.get_storage()
    storage_service.reset_storage()


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


@pytest.fixture
def s3(monkeypatch):
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


def test_persist_vton_output_persists_data_url_to_backend(local_storage):
    """A worker data-URL payload is written to storage and the row gets a durable ref."""
    svc = TryOnService.__new__(TryOnService)
    data_url = _tiny_png_data_url()
    url = svc._persist_vton_output(data_url, "vton_job_abc123")
    assert url.startswith("/uploads/vton/vton_job_abc123.png")
    # The reference is owned by the backend (so it can be retrieved / GC'd by key)
    assert local_storage.owns_url(url) is True
    key = local_storage.key_for_url(url)
    assert key == "vton/vton_job_abc123.png"
    # Bytes round-trip and are genuinely the image we persisted
    raw = local_storage.read(key)
    assert raw is not None and raw.startswith(b"\x89PNG")
    img = Image.open(io.BytesIO(raw))
    assert img.size == (32, 32)
    assert img.convert("RGB").getpixel((0, 0)) == (180, 60, 60)


def test_persist_vton_output_leaves_external_url_alone(local_storage):
    """External / caller-authored URLs are NOT re-hosted and are not owned."""
    svc = TryOnService.__new__(TryOnService)
    external = "https://images.unsplash.com/photo-1507679799987?w=600"
    assert svc._persist_vton_output(external, "vton_job_xyz") == external
    assert local_storage.owns_url(external) is False
    assert local_storage.key_for_url(external) is None


def test_persist_vton_output_rejects_empty(local_storage):
    svc = TryOnService.__new__(TryOnService)
    with pytest.raises(ValueError, match="no rendered image"):
        svc._persist_vton_output("", "vton_job_empty")


def test_persist_vton_output_fails_closed_in_production_without_object_storage(monkeypatch, tmp_path):
    """No durable backend in production => 501 before bytes are accepted."""
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "local", raising=False)
    monkeypatch.setattr(settings, "STORAGE_LOCAL_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    storage_service.reset_storage()
    try:
        svc = TryOnService.__new__(TryOnService)
        with pytest.raises(FeatureNotConfiguredError):
            svc._persist_vton_output(_tiny_png_data_url(), "vton_job_prod")
    finally:
        storage_service.reset_storage()


def test_persist_vton_output_round_trips_through_s3(s3):
    """With a real object-storage contract, the image lands in the bucket as a URL."""
    svc = TryOnService.__new__(TryOnService)
    monkeypatch = None  # settings already configured by the s3 fixture
    data_url = _tiny_png_data_url(color=(40, 90, 200))
    url = svc._persist_vton_output(data_url, "vton_job_s3")
    assert url.startswith("https://confit-media.s3.eu-central-1.amazonaws.com/")
    key = storage_service.get_storage().key_for_url(url)
    assert key == "vton/vton_job_s3.png"
    assert ("confit-media", "vton/vton_job_s3.png") in s3.objects
    assert storage_service.get_storage().owns_url(url) is True
