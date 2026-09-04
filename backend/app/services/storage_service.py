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
import uuid
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.exceptions import ValidationDomainError, FeatureNotConfiguredError


def storage_status() -> dict:
    """Configuration-only view of where persisted files would go (no network).

    ``production_grade`` is True only for object storage. The local backend is
    a development convenience: on Vercel the function filesystem is read-only
    (and ephemeral on every other serverless host), so every write would 500
    with PermissionError or vanish on the next cold start.
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
    bucket = getattr(settings, "AWS_S3_BUCKET", None) or getattr(settings, "S3_BUCKET", None)
    creds = bool(getattr(settings, "AWS_ACCESS_KEY_ID", None) and getattr(settings, "AWS_SECRET_ACCESS_KEY", None))
    try:
        import boto3  # noqa: F401
        boto_ok = True
    except ImportError:
        boto_ok = False
    configured = bool(bucket and creds and boto_ok)
    return {
        "provider": provider,
        "production_grade": configured,
        "bucket_configured": bool(bucket),
        "credentials_configured": creds,
        "client_installed": boto_ok,
        "detail": "object storage configured" if configured else
                  "object storage selected but incomplete (bucket / credentials / boto3 missing)",
    }


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
        # Support both AWS S3 and Cloudflare R2
        self.bucket = getattr(settings, 'AWS_S3_BUCKET', None) or getattr(settings, 'S3_BUCKET', None)
        self.region = getattr(settings, 'AWS_REGION', 'us-east-1')
        self.access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
        self.secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        self.endpoint_url = getattr(settings, 'S3_ENDPOINT_URL', None)  # For R2
        self.public_url_base = getattr(settings, 'S3_PUBLIC_URL_BASE', None)

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
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                endpoint_url=self.endpoint_url,  # None for AWS, set for R2
            )
        except ImportError:
            raise ValidationDomainError(
                "boto3 not installed. Install with: pip install boto3"
            )

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

    def store(self, relative_path: str, data: bytes) -> str:
        if ".." in relative_path:
            raise ValidationDomainError(f"Invalid storage path: {relative_path}")

        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=relative_path,
                Body=data,
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
    """For testing - reset singleton"""
    global _storage_backend
    _storage_backend = None
