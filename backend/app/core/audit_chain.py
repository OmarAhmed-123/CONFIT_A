"""Tamper-evident audit chain (closes P0 from the 2026-09-22 admin audit).

The finding: ``audit_logs`` had no persisted hash chain, so the integrity
endpoint honestly reported ``tamper_evident: false`` — a writer with direct
database access could alter or delete historical rows undetected.

This module closes that gap with an HMAC-SHA256 hash chain:

* every row stores ``prev_hash`` (the ``entry_hash`` of the previous row,
  or the 64-zero genesis value for the first row) and ``entry_hash`` =
  HMAC-SHA256(key, canonical_string(row)),
* the canonical string covers every mutable audit field **and** the
  ``prev_hash`` link, so editing any historical row breaks its own HMAC,
  and deleting or reordering rows breaks the linkage of the row after it,
* the HMAC key is a **dedicated** secret (``AUDIT_HMAC_KEY``), separate from
  the JWT signing key, with an explicit version column
  (``chain_key_version``) so the key can be rotated without invalidating
  history — verification resolves the key per row version.

Enforcement is a single SQLAlchemy ``before_insert`` listener on the
``AuditLog`` mapper (registered in ``models/user.py``): *every* insert, from
every call site — ``UserRepository.log_audit``, the partner-lead writer, the
catalog-import writer, or any future one — is chained. There is no unchained
write path to forget (DRY: one enforcement point, not N call-site contracts).

Concurrency: on PostgreSQL the append takes a transaction-scoped advisory
lock (``pg_advisory_xact_lock``) so two concurrent inserts cannot both read
the same head and fork the chain. SQLite serialises writers natively.

Honest limits (stated, not hidden — same policy as the rest of the codebase):

* An attacker who obtains BOTH direct database write access AND the active
  HMAC key can re-forge the chain from the point of tampering forward.
  Key separation narrows this to a full-secrets compromise; it cannot
  eliminate it without external anchoring (WORM storage / signed Merkle
  roots), which is documented as the next hardening step.
* Truncation of the newest rows (deleting the tail) is only detectable
  across verification runs by comparing the persisted head; single-run
  verification proves the *surviving* prefix is intact.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from backend.app.core.config import settings

# 64 zeros: the genesis ``prev_hash`` for the first row in the chain.
GENESIS_HASH = "0" * 64

# Canonical-string layout version. Bump ONLY with a new chain_key_version
# handler in ``resolve_key`` — old rows must stay verifiable forever.
CANONICAL_VERSION = 1

# Stable advisory-lock key for the single global chain (fits signed int64).
_PG_ADVISORY_LOCK_KEY = 0x_C0F1_7A0D_17C4  # "CONFIT AUDIT Chain"

_FIELD_SEPARATOR = "\x1f"  # ASCII unit separator: cannot appear in the fields


def _derived_fallback_key() -> bytes:
    """Deterministic fallback when AUDIT_HMAC_KEY is unset (dev/test).

    Derived from SECRET_KEY with a fixed info label so it is (a) never equal
    to the JWT key itself and (b) reproducible across processes of the same
    deployment. Production should always set a dedicated AUDIT_HMAC_KEY.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        b"confit-audit-chain-v1",
        hashlib.sha256,
    ).digest()


def active_key_version() -> int:
    return int(getattr(settings, "AUDIT_CHAIN_KEY_VERSION", 1) or 1)


class AuditKeyUnavailableError(LookupError):
    """No key material exists for a requested ``chain_key_version``.

    Raised instead of silently falling back to the wrong key: a row whose
    key cannot be resolved must be reported as *unverifiable*, never as
    intact (fail closed).
    """


def resolve_key(key_version: Optional[int]) -> bytes:
    """Key bytes for a given ``chain_key_version``.

    * ``key_version`` equal to the ACTIVE version (or ``None`` for new rows)
      resolves to ``AUDIT_HMAC_KEY`` (or the derived dev/test fallback).
    * A RETIRED version ``n`` resolves ONLY from the explicit environment
      variable ``AUDIT_HMAC_KEY_V{n}`` — there is deliberately no fallback,
      so a missing retired key makes verification fail closed rather than
      quietly verifying old rows with the wrong key.

    Rotation runbook: docs/ADMIN_GOVERNANCE_AUDIT_OPERATIONS.md.
    """
    version = int(key_version) if key_version is not None else active_key_version()
    if version == active_key_version():
        configured = getattr(settings, "AUDIT_HMAC_KEY", None)
        if configured:
            return str(configured).encode("utf-8")
        return _derived_fallback_key()
    retired = os.environ.get(f"AUDIT_HMAC_KEY_V{version}")
    if retired:
        return retired.encode("utf-8")
    raise AuditKeyUnavailableError(
        f"no key material for retired chain_key_version={version}: "
        f"set AUDIT_HMAC_KEY_V{version} (see key lifecycle runbook)"
    )


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _norm_timestamp(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="microseconds")


def canonical_string(
    *,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    ip_address: Optional[str],
    details_json: Optional[str],
    before_json: Optional[str],
    after_json: Optional[str],
    request_id: Optional[str],
    timestamp: Optional[datetime],
    prev_hash: str,
) -> str:
    """Versioned canonical serialisation of one audit row.

    Field order and separator are frozen for CANONICAL_VERSION=1. The row id
    is deliberately excluded (it is not assigned until INSERT executes);
    ordering integrity comes from the prev_hash linkage itself.
    """
    parts = [
        f"v{CANONICAL_VERSION}",
        _norm(user_id),
        _norm(action),
        _norm(resource_type),
        _norm(resource_id),
        _norm(ip_address),
        _norm(details_json),
        _norm(before_json),
        _norm(after_json),
        _norm(request_id),
        _norm_timestamp(timestamp),
        prev_hash,
    ]
    return _FIELD_SEPARATOR.join(parts)


def compute_entry_hash(canonical: str, key: bytes) -> str:
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def entry_hash_for_row(row: Any, prev_hash: str, key: bytes) -> str:
    """HMAC for an ORM row / row-like object against a given prev link."""
    return compute_entry_hash(
        canonical_string(
            user_id=row.user_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            ip_address=row.ip_address,
            details_json=row.details_json,
            before_json=row.before_json,
            after_json=row.after_json,
            request_id=row.request_id,
            timestamp=row.timestamp,
            prev_hash=prev_hash,
        ),
        key,
    )


# --------------------------------------------------------------------------
# Write path: single enforcement point (SQLAlchemy before_insert listener)
# --------------------------------------------------------------------------

def chain_before_insert(mapper, connection, target) -> None:
    """Compute prev_hash/entry_hash for every AuditLog insert, anywhere.

    Registered on the AuditLog mapper in ``models/user.py``. Runs inside the
    INSERT's transaction on the INSERT's connection, so the SELECT for the
    current head sees rows already flushed in this transaction, and the
    advisory lock (PostgreSQL) serialises concurrent appenders until commit.
    """
    # Canonical v1 joins fields with \x1f, which is only unambiguous if the
    # separator can never appear INSIDE a field. json.dumps escapes control
    # characters, but free-text columns (notably ip_address, which can be
    # influenced by X-Forwarded-For) could smuggle a raw \x1f and craft two
    # different rows with identical canonical bytes. Enforce the invariant
    # at the single write path: no stored field ever contains the separator.
    for field in (
        "action", "resource_type", "resource_id", "ip_address",
        "details_json", "before_json", "after_json", "request_id",
    ):
        value = getattr(target, field, None)
        if isinstance(value, str) and _FIELD_SEPARATOR in value:
            setattr(target, field, value.replace(_FIELD_SEPARATOR, "\\u001f"))

    # The ORM column default for ``timestamp`` resolves at statement-compile
    # time — after this listener — so pin it here to include it in the HMAC.
    if target.timestamp is None:
        target.timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    elif target.timestamp.tzinfo is not None:
        target.timestamp = target.timestamp.astimezone(timezone.utc).replace(tzinfo=None)

    if connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _PG_ADVISORY_LOCK_KEY}
        )

    # SQLAlchemy may flush several AuditLog rows in ONE batch: every
    # before_insert fires before any INSERT executes, so a bare SELECT would
    # hand the same head to all of them and fork the chain. The in-flight
    # head is therefore cached on the connection, keyed by the CURRENT root
    # transaction object — a new transaction (or a rollback) gets a fresh
    # SELECT, never a stale cache from a pooled connection's previous life.
    txn = connection.get_transaction()
    cache = connection.info.get("_audit_chain_head")
    if cache is not None and cache[0] is txn:
        prev_hash = cache[1]
    else:
        head = connection.execute(
            text(
                "SELECT entry_hash FROM audit_logs "
                "WHERE entry_hash IS NOT NULL ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
        prev_hash = head[0] if head else GENESIS_HASH

    target.prev_hash = prev_hash
    target.chain_key_version = active_key_version()
    target.entry_hash = entry_hash_for_row(
        target, prev_hash, resolve_key(target.chain_key_version)
    )
    connection.info["_audit_chain_head"] = (txn, target.entry_hash)


# --------------------------------------------------------------------------
# Verification (read path)
# --------------------------------------------------------------------------

def verify_chain(rows: List[Any], *, expected_prev: Optional[str] = None) -> Dict[str, Any]:
    """Recompute the chain over ``rows`` (must be in ascending id order).

    Returns concrete per-row breaks, never a bare boolean — "the chain is
    fine" must be checkable, not assertable.

    ``expected_prev``: the anchor for the first row. ``None`` accepts the
    first row's stored prev_hash as the anchor (window-scoped verification);
    pass ``GENESIS_HASH`` for a full-history scan from the origin.
    """
    breaks: List[Dict[str, Any]] = []
    unchained = 0
    prev = expected_prev

    for row in rows:
        if row.entry_hash is None or row.prev_hash is None:
            # Row was never chained (legacy pre-migration row, or a write
            # that bypassed the mapper listener — the caller classifies
            # which; see AuditService.verify_integrity). Unchained rows do
            # NOT advance the chain head, so ``prev`` is deliberately kept:
            # the next chained row must still link to the last chained
            # entry_hash, otherwise an attacker could hide a deletion by
            # interleaving an unchained row.
            unchained += 1
            continue
        if prev is not None and row.prev_hash != prev:
            breaks.append(
                {
                    "row_id": row.id,
                    "issue": "chain_link_mismatch",
                    "detail": "prev_hash does not match the entry_hash of the "
                              "preceding row — a row was altered, deleted or "
                              "reordered at or before this point.",
                }
            )
        try:
            key = resolve_key(row.chain_key_version)
        except AuditKeyUnavailableError as exc:
            # Fail closed: a row we cannot check is a finding, not a pass.
            breaks.append(
                {
                    "row_id": row.id,
                    "issue": "key_unavailable",
                    "detail": str(exc),
                }
            )
            prev = row.entry_hash
            continue
        recomputed = entry_hash_for_row(row, row.prev_hash, key)
        if not hmac.compare_digest(recomputed, row.entry_hash):
            breaks.append(
                {
                    "row_id": row.id,
                    "issue": "entry_hash_mismatch",
                    "detail": "stored HMAC does not match the row content — "
                              "the row was modified after it was written.",
                }
            )
        prev = row.entry_hash

    return {
        "rows_verified": len(rows) - unchained,
        "unchained_rows": unchained,
        "breaks": breaks,
        "intact": not breaks,
        "head_hash": prev,
        "key_version": active_key_version(),
        "canonical_version": CANONICAL_VERSION,
    }
