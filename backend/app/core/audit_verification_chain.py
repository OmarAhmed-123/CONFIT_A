"""HMAC chain for ``audit_verification_runs`` (migration 0023).

Migration 0022 made both audit tables database-restricted append-only for the
runtime role, but that role legitimately retains INSERT. A stolen runtime DB
credential could therefore INSERT an arbitrary verification row and make it
look like an authentic application verification. This chain separates:

* storage control (0022: history cannot be UPDATE/DELETE/TRUNCATE), and
* provenance/integrity (0023: every supported run insert is HMAC chained; a
  raw/Core/direct SQL insert has no valid hash and is reported as a forgery).

The key is domain-separated from audit-log entries:

    run_key = HMAC(AUDIT_HMAC_KEY_version, "confit-verification-runs-v1")

so the same root secret never signs two canonical domains directly. The same
key-version lifecycle applies: active ``AUDIT_HMAC_KEY``; retired
``AUDIT_HMAC_KEY_V{n}``; missing retired key fails closed.

This remains tamper-evident, not immutable/non-repudiable. Actor I (DB write +
all HMAC keys) can re-forge both chains. External anchoring is still required
to close that boundary.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.core.audit_chain import (
    AuditKeyUnavailableError,
    GENESIS_HASH,
    active_key_version,
    resolve_key,
)

RUN_CANONICAL_VERSION = 1
RUN_GENESIS_HASH = GENESIS_HASH
_RUN_LOCK_KEY = 0x_C0F1_7A0D_17C5
_SEP = "\x1f"
_DOMAIN = b"confit-verification-runs-v1"


def _timestamp(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="microseconds")


def _value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def verification_key(key_version: int) -> bytes:
    root = resolve_key(key_version)
    return hmac.new(root, _DOMAIN, hashlib.sha256).digest()


def canonical_run(row: Any, previous_hash: str) -> str:
    """Fixed-order canonical v1 over every mutable run field."""
    return _SEP.join([
        f"v{RUN_CANONICAL_VERSION}",
        _timestamp(row.run_at),
        _value(row.window_days),
        _value(row.checked_rows),
        _value(row.sampled_rows),
        _value(row.chained_rows),
        _value(row.unchained_rows),
        _value(row.break_count),
        _value(row.verdict),
        _value(row.tamper_evident),
        _value(row.head_hash),
        _value(row.head_row_id),
        _value(row.key_version),
        _value(row.canonical_version),
        _value(row.triggered_by_user_id),
        _value(row.request_id),
        previous_hash,
    ])


def hash_run(row: Any, previous_hash: str, key_version: int) -> str:
    payload = canonical_run(row, previous_hash).encode("utf-8")
    return hmac.new(verification_key(key_version), payload, hashlib.sha256).hexdigest()


def verification_run_before_insert(mapper, connection, target) -> None:
    """Single supported write enforcement point, serialised on PostgreSQL."""
    # Canonical v1 is separator-delimited. Enforce the same invariant as the
    # primary audit chain at the single write point so a caller-controlled
    # request id cannot create two distinct rows with identical canonical
    # bytes by smuggling the separator into a field.
    for field in ("verdict", "head_hash", "request_id"):
        value = getattr(target, field, None)
        if isinstance(value, str) and _SEP in value:
            setattr(target, field, value.replace(_SEP, "\\u001f"))

    if target.run_at is None:
        target.run_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif target.run_at.tzinfo is not None:
        target.run_at = target.run_at.astimezone(timezone.utc).replace(tzinfo=None)

    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _RUN_LOCK_KEY})

    txn = connection.get_transaction()
    cache = connection.info.get("_audit_verification_run_head")
    if cache is not None and cache[0] is txn:
        previous = cache[1]
    else:
        head = connection.execute(text(
            "SELECT run_hash FROM audit_verification_runs "
            "WHERE run_hash IS NOT NULL ORDER BY id DESC LIMIT 1"
        )).fetchone()
        previous = head[0] if head else RUN_GENESIS_HASH

    target.run_prev_hash = previous
    target.run_hmac_key_version = active_key_version()
    target.run_hash = hash_run(target, previous, target.run_hmac_key_version)
    connection.info["_audit_verification_run_head"] = (txn, target.run_hash)


def verification_run_crosslink(audit_row: Any) -> Optional[Dict[str, Any]]:
    """Extract a 0023 run reference from one integrity-check audit event.

    ``None`` means the event predates 0023 (or is not an integrity event), not
    that it is malformed. A present-but-invalid reference is returned as a
    concrete finding so callers never silently skip a damaged cross-link.
    """
    if getattr(audit_row, "action", None) != "ADMIN_AUDIT_INTEGRITY_CHECK":
        return None
    raw = getattr(audit_row, "after_json", None)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {
            "audit_row_id": getattr(audit_row, "id", None),
            "verdict": "malformed_crosslink",
            "detail": "integrity-check audit event has invalid JSON",
        }
    if not isinstance(payload, dict) or "verification_run" not in payload:
        return None  # honest legacy event from before 0023
    reference = payload.get("verification_run")
    run_id = reference.get("id") if isinstance(reference, dict) else None
    run_hash = reference.get("run_hash") if isinstance(reference, dict) else None
    try:
        valid_hash = (
            isinstance(run_hash, str)
            and len(run_hash) == 64
            and int(run_hash, 16) >= 0
        )
    except ValueError:
        valid_hash = False
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1 or not valid_hash:
        return {
            "audit_row_id": getattr(audit_row, "id", None),
            "verdict": "malformed_crosslink",
            "detail": "integrity-check audit event has an invalid verification-run reference",
        }
    return {
        "audit_row_id": getattr(audit_row, "id", None),
        "verdict": "reference_found",
        "run_id": run_id,
        "run_hash": run_hash,
    }


def verify_verification_run_crosslink(
    reference: Optional[Dict[str, Any]], persisted_run: Optional[Any]
) -> Dict[str, Any]:
    """Check the latest audit-chain cross-link to close run-chain tail deletion."""
    if reference is None:
        return {"audit_row_id": None, "run_id": None, "verdict": "no_prior_crosslink"}
    if reference.get("verdict") == "malformed_crosslink":
        return dict(reference)
    if persisted_run is None:
        return {
            "audit_row_id": reference.get("audit_row_id"),
            "run_id": reference.get("run_id"),
            "verdict": "tail_deletion_detected",
            "detail": "the verification run referenced by the audit chain no longer exists",
        }
    if not hmac.compare_digest(str(persisted_run.run_hash or ""), reference["run_hash"]):
        return {
            "audit_row_id": reference.get("audit_row_id"),
            "run_id": reference.get("run_id"),
            "verdict": "crosslink_mismatch",
            "detail": "the persisted verification-run hash differs from its audit-chain reference",
        }
    return {
        "audit_row_id": reference.get("audit_row_id"),
        "run_id": reference.get("run_id"),
        "verdict": "anchored",
    }


def verify_verification_runs(
    rows: List[Any], *, expected_prev: Optional[str] = None
) -> Dict[str, Any]:
    """Verify signed runs in ascending id order; unsigned-after-signed is forged."""
    breaks: List[Dict[str, Any]] = []
    unsigned = 0
    prev = expected_prev
    signed_seen = False

    for row in rows:
        if not row.run_hash or not row.run_prev_hash or not row.run_hmac_key_version:
            unsigned += 1
            if signed_seen:
                breaks.append({
                    "run_id": row.id,
                    "issue": "verification_run_forgery_suspected",
                    "detail": "unsigned verification row appears after signed-run enforcement began",
                })
            continue
        signed_seen = True
        if prev is not None and row.run_prev_hash != prev:
            breaks.append({
                "run_id": row.id,
                "issue": "verification_run_link_mismatch",
                "detail": "run_prev_hash does not match the preceding signed verification run",
            })
        try:
            recomputed = hash_run(row, row.run_prev_hash, int(row.run_hmac_key_version))
        except AuditKeyUnavailableError as exc:
            breaks.append({
                "run_id": row.id,
                "issue": "verification_run_key_unavailable",
                "detail": str(exc),
            })
            prev = row.run_hash
            continue
        if not hmac.compare_digest(recomputed, row.run_hash):
            breaks.append({
                "run_id": row.id,
                "issue": "verification_run_hash_mismatch",
                "detail": "stored run HMAC does not match its persisted content",
            })
        prev = row.run_hash

    return {
        "rows_checked": len(rows),
        "signed_rows": len(rows) - unsigned,
        "unsigned_rows": unsigned,
        "breaks": breaks,
        "intact": not breaks,
        "head_hash": prev,
        "canonical_version": RUN_CANONICAL_VERSION,
    }
