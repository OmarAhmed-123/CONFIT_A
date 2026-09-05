"""Temporary (non-persistent) delivery for generated VTON images.

Product requirement (2026-09-05 closure directive):

* the generated try-on image must be deliverable to the authenticated
  requesting user (display + download);
* it must NOT be permanently stored — not in PostgreSQL, not in R2/S3, not on
  local disk, not in the repository, not in any durable object store or
  frontend asset.

Design (smallest mechanism that satisfies the contract on Vercel serverless):

* **Primary vehicle — in-response delivery.** The image bytes travel inside
  the authenticated HTTP response that completed the render
  (``result_image_data_url`` on the job payload, ``rendered_result_url`` on
  the multi-garment payload). Nothing is written to disk, to a database
  column, or to object storage. This vehicle is guaranteed regardless of
  serverless instance affinity.

* **Secondary vehicle — one-shot temporary download.** When a job completes,
  the bytes are additionally staged in a **process-local**, TTL-bounded,
  capacity-bounded cache under a fresh high-entropy one-time token.
  ``GET /try-on/jobs/{job_id}/result?delivery_token=*** claims the bytes
  exactly once (destructive read) for the job owner. The only delivery
  metadata persisted on the job row is the token's SHA-256 hash and the
  expiry timestamp — never the token itself, never the image bytes.

* **Honest serverless limit.** The cache is process-local: on Vercel, a
  recycled or different function instance does not hold the bytes and the
  download endpoint answers 410 GONE. The in-response vehicle is the
  guaranteed one; the download endpoint is best-effort convenience within
  the TTL on a warm instance. This limitation is documented, never faked.

* **Cleanup.** Entries are removed on first delivery (one-shot), on TTL
  expiry (lazy purge on every access + at staging time), on explicit owner
  revocation (DELETE endpoint), and on job cancellation. Failed jobs stage
  nothing, so there is nothing to clean up on the failure path.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from backend.app.core.config import settings
from backend.app.core.logging import logger

# Content types the download endpoint may emit (image bytes only, ever).
_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}


def data_url_to_bytes(data_url: str) -> Tuple[bytes, str]:
    """Decode a ``data:image/...;base64,...`` payload into ``(raw, mime)``.

    Raises ``ValueError`` with a stable ``VTON_DELIVERY_INVALID`` prefix for
    anything that is not a decodable image data URL.
    """
    if not data_url or not isinstance(data_url, str) or not data_url.startswith("data:"):
        raise ValueError("VTON_DELIVERY_INVALID: payload is not a data URL")
    header, _, b64 = data_url.partition(",")
    meta = header[len("data:"):]
    mime = (meta.split(";", 1)[0] or "").strip().lower()
    if mime not in _ALLOWED_MIME:
        raise ValueError(f"VTON_DELIVERY_INVALID: unsupported or missing image mime {mime!r}")
    if "base64" not in meta:
        raise ValueError("VTON_DELIVERY_INVALID: only base64 data URLs are accepted")
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as exc:  # noqa: BLE001 - normalise to a stable error
        raise ValueError(f"VTON_DELIVERY_INVALID: cannot decode image payload: {exc}") from exc
    if not raw:
        raise ValueError("VTON_DELIVERY_INVALID: empty image payload")
    return raw, mime


def ext_for_mime(mime: str) -> str:
    return {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")


@dataclass
class _Entry:
    token_hash: str
    job_id: str
    payload: bytes
    mime: str
    expires_at: float
    staged_at: float


class TemporaryImageStore:
    """In-process, TTL- and capacity-bounded, one-shot image delivery cache.

    Thread-safe (the Vercel Python runtime is single-process; the lock is
    belt-and-braces for uvicorn workers and tests). Entries are keyed by the
    SHA-256 of a 192-bit one-time token — the plaintext token exists only in
    the staging response and in the caller's memory.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, _Entry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _purge_expired_locked(self, now: float) -> int:
        stale = [h for h, e in self._entries.items() if e.expires_at <= now]
        for h in stale:
            del self._entries[h]
        return len(stale)

    def _evict_to_capacity_locked(self) -> int:
        """Evict oldest entries until count/byte budgets are respected."""
        evicted = 0
        max_images = max(1, int(getattr(settings, "VTON_DELIVERY_MAX_IMAGES", 16)))
        max_bytes = max(1, int(getattr(settings, "VTON_DELIVERY_MAX_BYTES", 64 * 1024 * 1024)))
        while True:
            over_count = len(self._entries) > max_images
            over_bytes = sum(len(e.payload) for e in self._entries.values()) > max_bytes
            if not over_count and not over_bytes:
                break
            if not self._entries:
                break
            oldest = min(self._entries.values(), key=lambda e: (e.staged_at, e.token_hash))
            del self._entries[oldest.token_hash]
            evicted += 1
        return evicted

    # ------------------------------------------------------------------ ops
    def new_delivery_credentials(self) -> Tuple[str, str]:
        """Issue a fresh one-time delivery credential for a job.

        Returns ``(token, token_hash)``. The token is a 192-bit capability:
        it is returned to the submitter in the job (completion) response and
        only its SHA-256 hash is persisted. Issued at job CREATION (before
        inference) so that guest submitters can poll their job's status
        across serverless instances; the image bytes are attached later, at
        staging time.
        """
        token = secrets.token_urlsafe(32)
        return token, self._token_hash(token)

    def stage(
        self,
        token_hash: str,
        job_id: str,
        data_url: str,
        ttl_seconds: Optional[float] = None,
    ) -> Dict[str, object]:
        """Attach a rendered image to an existing delivery credential.

        Returns ``{token_hash, expires_at, content_type, byte_size}``.
        The TTL starts at staging (completion) time — a slow/cold GPU call
        never eats into the user's download window.
        """
        if not token_hash:
            raise ValueError("VTON_DELIVERY_INVALID: missing credential hash")
        raw, mime = data_url_to_bytes(data_url)
        if ttl_seconds is None:
            ttl_seconds = float(getattr(settings, "VTON_DELIVERY_TTL_SECONDS", 900.0))
        now = time.time()
        with self._lock:
            self._purge_expired_locked(now)
            entry = _Entry(
                token_hash=token_hash,
                job_id=job_id,
                payload=raw,
                mime=mime,
                expires_at=now + max(1.0, ttl_seconds),
                staged_at=now,
            )
            self._entries[token_hash] = entry
            evicted = self._evict_to_capacity_locked()
        if evicted:
            logger.info("vton_delivery_evicted", evicted=evicted, job_id=job_id)
        return {
            "token_hash": token_hash,
            "expires_at": entry.expires_at,
            "content_type": mime,
            "byte_size": len(raw),
        }

    def claim(self, token: str, job_id: str) -> Optional[Tuple[bytes, str]]:
        """One-shot destructive fetch.

        Returns ``(payload, mime)`` on success and removes the entry; returns
        ``None`` when the token is unknown, expired, already claimed, or bound
        to a different job.
        """
        if not token:
            return None
        now = time.time()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._entries.get(self._token_hash(token))
            if entry is None or entry.job_id != job_id:
                return None
            del self._entries[entry.token_hash]
            return entry.payload, entry.mime

    def is_live(self, token: str, job_id: str) -> bool:
        """Non-destructive availability probe (same instance only)."""
        if not token:
            return False
        now = time.time()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._entries.get(self._token_hash(token))
            return entry is not None and entry.job_id == job_id

    def purge_by_hash(self, token_hash: Optional[str], job_id: str) -> bool:
        """Explicit deletion (owner revocation / job cancellation)."""
        if not token_hash:
            return False
        with self._lock:
            entry = self._entries.get(token_hash)
            if entry is None or entry.job_id != job_id:
                return False
            del self._entries[entry.token_hash]
            return True

    def purge_job(self, job_id: str) -> int:
        """Delete every staged entry for a job (best-effort sweep)."""
        with self._lock:
            stale = [h for h, e in self._entries.items() if e.job_id == job_id]
            for h in stale:
                del self._entries[h]
            return len(stale)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            self._purge_expired_locked(time.time())
            return {
                "entries": len(self._entries),
                "bytes": sum(len(e.payload) for e in self._entries.values()),
            }

    def reset(self) -> None:
        """Test helper."""
        with self._lock:
            self._entries.clear()


# Process-local singleton — the ONLY place generated VTON image bytes live
# outside of the in-flight request. Bounded by TTL and capacity.
temporary_image_store = TemporaryImageStore()


def stage_vton_delivery(job_id: str, token_hash: str, rendered_data_url: str) -> Dict[str, object]:
    """Service-layer wrapper used by TryOnService. Returns the staging dict
    plus the TTL for the API response."""
    out = dict(temporary_image_store.stage(token_hash, job_id, rendered_data_url))
    out["ttl_seconds"] = float(getattr(settings, "VTON_DELIVERY_TTL_SECONDS", 900.0))
    return out
