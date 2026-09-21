"""
C24 FIX: Production Storage Abstraction

Local filesystem is ephemeral on Render/Vercel/Modal - files disappear on restart.
This service provides pluggable storage backend with honest failure handling.

- local: development only, stores under STORAGE_LOCAL_DIR, warns in production
- s3: production-ready, requires AWS_S3_BUCKET + credentials, fails honestly if missing
- r2: Cloudflare R2 compatible (S3 API), requires R2_* env vars

All callers use this service instead of direct os.path operations for persistence.
"""
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.exceptions import ValidationDomainError, FeatureNotConfiguredError


def storage_status() -> dict:
    """Configuration-only view of where persisted files would go (no network).

    ``production_grade`` is True only for object storage. The local backend is
    a development convenience: on Vercel the function filesystem is read-only
    (and ephemeral on every other serverless host), so every write would 500
    with PermissionError or vanish on the next cold start.

    When ``STORAGE_PROBE_ENABLED`` is set (production), the returned status also
    carries the last LIVE probe verdict (put/get/delete round trip against the
    real bucket). Configuration presence is not proof of reachability — a
    bucket in another region, a revoked credential and a typo'd endpoint all
    report "configured" while every user upload 500s. The probe is what makes
    /health tell the truth about storage instead of restating the env file.
    """
    provider = (getattr(settings, "STORAGE_PROVIDER", "local") or "local").lower()
    if provider == "local":
        root = os.path.abspath(settings.STORAGE_LOCAL_DIR)
        writable = os.path.isdir(root) and os.access(root, os.W_OK)
        return {
            "provider": "local",
            "production_grade": False,
            "writable": writable,
            "detail": (
                "local filesystem is development-only: files are ephemeral/read-only on serverless hosts; "
                "set STORAGE_PROVIDER=s3|r2 with AWS_S3_BUCKET + credentials for shared, durable uploads"
            ),
        }
    bucket = settings.s3_bucket
    creds = bool(settings.s3_access_key and settings.s3_secret_key)
    try:
        import boto3  # noqa: F401
        boto_ok = True
    except ImportError:
        boto_ok = False
    configured = bool(bucket and creds and boto_ok)
    out = {
        "provider": provider,
        "production_grade": configured,
        "bucket_configured": bool(bucket),
        "credentials_configured": creds,
        "client_installed": boto_ok,
        "endpoint_configured": bool(settings.s3_endpoint_url),
        "server_side_encryption": (getattr(settings, "S3_SERVER_SIDE_ENCRYPTION", None) or "AES256"),
        "detail": "object storage configured" if configured else
                  "object storage selected but incomplete (bucket / credentials / boto3 missing)",
    }
    if getattr(settings, "STORAGE_PROBE_ENABLED", False):
        probe = probe_storage(force=False)
        out["live_probe"] = probe
        # A configured-but-unreachable bucket is NOT production grade: uploads
        # would fail at request time, which is exactly the class of failure
        # this field exists to prevent operators from being surprised by.
        out["production_grade"] = bool(configured and probe.get("ok"))
        if configured and not probe.get("ok"):
            out["detail"] = (
                "object storage is configured but the live probe failed: "
                + str(probe.get("error") or probe.get("verdict") or "unknown")
            )
    return out


# ---------------------------------------------------------------------------
# Live storage probe (network). Cached, bounded, and never raises.
# ---------------------------------------------------------------------------
_probe_cache: Dict[str, Any] = {}
_probe_lock = threading.Lock()


def probe_storage(force: bool = False, backend: Optional["StorageBackend"] = None) -> Dict[str, Any]:
    """Real put/get/delete round trip against the configured object store.

    Returns a JSON-safe verdict — never raises, never leaks credentials:

        {"ok": bool, "verdict": "ok"|"failed", "error": str|None,
         "probe_key": str, "age_seconds": float, "probe_ms": float}

    Cached for ``STORAGE_PROBE_TTL_SECONDS`` so /health does not hammer the
    bucket on every scrape. ``force=True`` bypasses the cache (used by the
    storage self-check script and by tests).
    """
    ttl = float(getattr(settings, "STORAGE_PROBE_TTL_SECONDS", 300.0))
    if ttl is None or ttl < 0:
        ttl = 300.0
    now = time.time()
    with _probe_lock:
        cached = _probe_cache.get("result")
        if cached and not force and (now - float(_probe_cache.get("at", 0.0))) < ttl:
            out = dict(cached)
            out["age_seconds"] = round(now - float(_probe_cache.get("at", 0.0)), 1)
            return out

    backend = backend or _safe_backend_for_probe()
    if backend is None:
        result = {
            "ok": False,
            "verdict": "failed",
            "error": "no usable storage backend (provider/bucket/credentials/boto3 incomplete)",
            "probe_key": None,
        }
    else:
        probe_key = f"__confit_storage_probe/{uuid.uuid4().hex}.txt"
        payload = b"confit-storage-probe"
        started = time.time()
        try:
            url = backend.store(probe_key, payload)
            if not backend.exists(probe_key):
                raise RuntimeError("object written by the probe is not readable back (exists() false)")
            read_back = backend.read(probe_key)
            if read_back != payload:
                raise RuntimeError("probe object read back with different bytes")
            deleted = backend.delete(probe_key)
            if backend.exists(probe_key):
                raise RuntimeError("probe object still present after delete()")
            result = {
                "ok": True,
                "verdict": "ok",
                "error": None,
                "probe_key": probe_key,
                "deleted": bool(deleted),
                "url_prefix_ok": bool(url),
                "probe_ms": round((time.time() - started) * 1000, 1),
            }
        except Exception as exc:  # noqa: BLE001 - a probe must never raise
            logger.warn("storage_probe_failed", error=str(exc)[:200])
            # Best-effort cleanup so a failed probe never orphans an object.
            try:
                backend.delete(probe_key)
            except Exception:  # noqa: BLE001
                pass
            result = {
                "ok": False,
                "verdict": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:180]}",
                "probe_key": probe_key,
                "probe_ms": round((time.time() - started) * 1000, 1),
            }
    with _probe_lock:
        _probe_cache["result"] = result
        _probe_cache["at"] = time.time()
    out = dict(result)
    out["age_seconds"] = 0.0
    return out


def _safe_backend_for_probe() -> Optional["StorageBackend"]:
    try:
        return get_storage_backend()
    except Exception as exc:  # noqa: BLE001
        logger.warn("storage_probe_backend_unavailable", error=str(exc)[:160])
        return None


def require_production_storage(feature: str) -> "StorageBackend":
    """Storage for user-facing upload features.

    Outside production the local backend is fine (explicit development
    convenience). In production, a non-durable or unwritable backend raises
    FeatureNotConfiguredError (HTTP 501) BEFORE any bytes are accepted — never a
    PermissionError 500 and never a URL to a file that will not exist on the
    next request.
    """
    status = storage_status()
    if settings.is_production and not status.get("production_grade"):
        raise FeatureNotConfiguredError(
            feature,
            hint=(
                "Persistent object storage is required in production: set STORAGE_PROVIDER=s3 (or r2), "
                "AWS_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (and S3_ENDPOINT_URL for R2)."
            ),
        )
    if status["provider"] == "local" and not status.get("writable"):
        raise FeatureNotConfiguredError(
            feature,
            hint=f"STORAGE_LOCAL_DIR ({settings.STORAGE_LOCAL_DIR}) is not writable.",
        )
    return get_storage()


class StorageBackend(ABC):
    @abstractmethod
    def store(self, relative_path: str, data: bytes) -> str:
        """Store data at relative_path, return public URL"""
        pass

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        pass

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        pass

    @abstractmethod
    def read(self, relative_path: str) -> Optional[bytes]:
        pass

    def key_for_url(self, public_url: Optional[str]) -> Optional[str]:
        """Inverse of ``store``: the storage key behind a public URL this backend
        issued, or None when the URL was not issued by this backend (seeded /
        external images must never be deleted or read through storage)."""
        return None

    def owns_url(self, public_url: Optional[str]) -> bool:
        return self.key_for_url(public_url) is not None


class LocalStorageBackend(StorageBackend):
    """Local filesystem - development only. Ephemeral in production!"""

    def __init__(self):
        self.root = os.path.abspath(settings.STORAGE_LOCAL_DIR)
        if settings.ENVIRONMENT == "production":
            logger.warn(
                "STORAGE_PROVIDER=local in production - files are EPHEMERAL and will be lost on restart! "
                "Set STORAGE_PROVIDER=s3 and configure AWS_S3_BUCKET for persistent storage."
            )

    def _safe_path(self, relative_path: str) -> str:
        # Prevent path traversal
        if ".." in relative_path or relative_path.startswith("/"):
            raise ValidationDomainError(f"Invalid storage path: {relative_path}")
        full = os.path.abspath(os.path.join(self.root, relative_path))
        if not full.startswith(self.root + os.sep):
            raise ValidationDomainError(f"Path traversal detected: {relative_path}")
        return full

    def store(self, relative_path: str, data: bytes) -> str:
        dest = self._safe_path(relative_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return f"/uploads/{relative_path}"

    def key_for_url(self, public_url: Optional[str]) -> Optional[str]:
        if not public_url or not public_url.startswith("/uploads/"):
            return None
        key = public_url[len("/uploads/"):]
        try:
            self._safe_path(key)
        except ValidationDomainError:
            return None
        return key

    def exists(self, relative_path: str) -> bool:
        try:
            return os.path.isfile(self._safe_path(relative_path))
        except ValidationDomainError:
            return False

    def delete(self, relative_path: str) -> bool:
        try:
            path = self._safe_path(relative_path)
            if os.path.isfile(path):
                os.remove(path)
                return True
        except Exception as e:
            logger.warn(f"Failed to delete local file {relative_path}: {e}")
        return False

    def read(self, relative_path: str) -> Optional[bytes]:
        try:
            path = self._safe_path(relative_path)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.warn(f"Failed to read local file {relative_path}: {e}")
        return None


class S3StorageBackend(StorageBackend):
    """S3/R2 production storage - persistent, requires credentials"""

    def __init__(self):
        # Support both AWS S3 and Cloudflare R2. Resolution goes through the
        # Settings.s3_* properties so the documented .env aliases
        # (S3_ENDPOINT / S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET_PUBLIC) are
        # honoured exactly like the AWS_* names — one resolution rule, not two.
        self.bucket = settings.s3_bucket
        self.region = getattr(settings, 'AWS_REGION', 'us-east-1')
        self.access_key = settings.s3_access_key
        self.secret_key = settings.s3_secret_key
        self.endpoint_url = settings.s3_endpoint_url  # For R2 / S3-compatible
        self.public_url_base = getattr(settings, 'S3_PUBLIC_URL_BASE', None)
        self.server_side_encryption = (
            getattr(settings, "S3_SERVER_SIDE_ENCRYPTION", None) or "AES256"
        ).strip()

        if not self.bucket:
            raise ValidationDomainError(
                "S3 storage requires AWS_S3_BUCKET env var. "
                "Set STORAGE_PROVIDER=local for development, or configure S3 for production."
            )
        if not self.access_key or not self.secret_key:
            raise ValidationDomainError(
                "S3 storage requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars."
            )

        try:
            import boto3
        except ImportError:
            raise ValidationDomainError(
                "boto3 not installed. Install with: pip install boto3"
            )
        # Explicit s3v4 + a short retry budget: an S3-compatible endpoint
        # (Neon storage / R2 / MinIO) rejects v2 signatures, and boto3's default
        # retry storm makes a failing probe look like a 30 s hang. botocore is
        # a transitive dependency of boto3, but the deployment dependency gate
        # (backend/scripts/check_runtime_imports.py) treats every imported name
        # as a declaration — so it is imported OPTIONALLY and the client simply
        # falls back to boto3's defaults when it is unavailable.
        client_kwargs: Dict[str, Any] = {
            "region_name": self.region,
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "endpoint_url": self.endpoint_url,  # None for AWS, set for R2
        }
        try:
            from botocore.config import Config
            client_kwargs["config"] = Config(
                signature_version="s3v4", retries={"max_attempts": 2}
            )
        except ImportError:  # pragma: no cover - boto3 without botocore
            logger.warn("botocore_unavailable_using_boto3_defaults")
        self.s3_client = boto3.client("s3", **client_kwargs)

    def _url_prefix(self) -> str:
        if self.public_url_base:
            return f"{self.public_url_base.rstrip('/')}/"
        if self.endpoint_url:
            # R2 public URL
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket}/"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/"

    def key_for_url(self, public_url: Optional[str]) -> Optional[str]:
        prefix = self._url_prefix()
        if not public_url or not public_url.startswith(prefix):
            return None
        key = public_url[len(prefix):]
        if not key or ".." in key or key.startswith("/"):
            return None
        return key

    @staticmethod
    def _content_type_for(key: str) -> str:
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        return {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif", "avif": "image/avif",
            "json": "application/json", "txt": "text/plain",
        }.get(ext, "application/octet-stream")

    def store(self, relative_path: str, data: bytes) -> str:
        if ".." in relative_path:
            raise ValidationDomainError(f"Invalid storage path: {relative_path}")

        # Server-side encryption is declared on EVERY write. User photos
        # (wardrobe / mood-board) are personal data: an unencrypted object in
        # a mis-configured bucket is a reportable exposure, and a bucket
        # policy that requires SSE would reject the write anyway — better to
        # state the intent explicitly than to rely on the bucket default.
        extra = {
            "ContentType": self._content_type_for(relative_path),
            "CacheControl": "private, max-age=31536000, immutable",
            "Metadata": {"written-by": "confit-api"},
        }
        if self.server_side_encryption:
            extra["ServerSideEncryption"] = self.server_side_encryption
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=relative_path,
                Body=data,
                **extra,
            )
            return self._url_prefix() + relative_path
        except Exception as e:
            logger.error(f"S3 upload failed for {relative_path}: {e}")
            raise ValidationDomainError(f"Storage upload failed: {str(e)}")

    def exists(self, relative_path: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=relative_path)
            return True
        except Exception:
            return False

    def delete(self, relative_path: str) -> bool:
        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=relative_path)
            return True
        except Exception as e:
            logger.warn(f"S3 delete failed for {relative_path}: {e}")
            return False

    def read(self, relative_path: str) -> Optional[bytes]:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=relative_path)
            return response['Body'].read()
        except Exception as e:
            logger.warn(f"S3 read failed for {relative_path}: {e}")
            return None


def get_storage_backend() -> StorageBackend:
    """Factory - returns configured backend based on STORAGE_PROVIDER env var"""
    provider = getattr(settings, 'STORAGE_PROVIDER', 'local').lower()

    if provider == 'local':
        return LocalStorageBackend()
    elif provider in ('s3', 'aws', 'r2', 'cloudflare'):
        return S3StorageBackend()
    else:
        raise ValidationDomainError(
            f"Unsupported STORAGE_PROVIDER '{provider}'. "
            f"Allowed: local, s3, r2. Got: {provider}"
        )


# Singleton for process-wide use
_storage_backend: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    global _storage_backend
    if _storage_backend is None:
        _storage_backend = get_storage_backend()
    return _storage_backend


def reset_storage():
    """For testing - reset singleton AND the live-probe cache.

    The probe cache is part of the observable state: leaving it behind made a
    test that reconfigured the bucket still see the previous verdict.
    """
    global _storage_backend
    _storage_backend = None
    with _probe_lock:
        _probe_cache.clear()
