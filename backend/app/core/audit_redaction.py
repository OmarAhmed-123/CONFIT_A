"""Audit-payload redaction — the enforcement half of the audit contract.

``UserRepository.log_audit`` has always carried a docstring telling callers not
to write passwords, tokens or OTPs into ``details`` / ``before`` / ``after``
(G-06). A docstring is not a control: there are 30 call sites across 6 modules,
and a single new caller that splats a request body into ``before`` writes a
plaintext secret into a table that is readable by every platform admin and
exportable for compliance.

This module turns the comment into a mechanism. It is deliberately:

* **Key-driven, not value-driven first.** A secret is identified by the name of
  the field that carries it, which is deterministic and explainable. Value
  patterns are a second net for secrets smuggled inside free-form strings.
* **Lossy on purpose.** A redacted value becomes ``[REDACTED:key=password]``
  so an auditor can still see *that* a credential field was part of the change
  without ever seeing it.
* **Non-raising.** Redaction must never turn a successful business action into
  a 500. The caller gets the count back so it can be logged/asserted.

Scalars that are *flags* rather than *values* are preserved: ``password`` with
the boolean ``true`` means "the password field changed", which is exactly what
an auditor wants and carries no secret.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Tuple

REDACTED_PREFIX = "[REDACTED"

# Key substrings that mark a field as secret-bearing. Lowercased substring match
# so ``hashed_password``, ``userPassword``, ``JWT_REFRESH_SECRET`` all hit.
SECRET_KEY_FRAGMENTS: Tuple[str, ...] = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "access_key",
    "accesskey",
    "private_key",
    "privatekey",
    "credential",
    "authorization",
    "cookie",
    "session_id",
    "otp",
    "mfa_secret",
    "totp",
    "recovery_code",
    "encryption_key",
    "signing_key",
    "card_number",
    "cardnumber",
    "cvv",
    "cvc",
    "iban",
    "ssn",
    "national_id",
    "passport",
    "refresh",
    "bearer",
    "webhook_secret",
    "dsn",
    "connection_string",
    "database_url",
)

# Keys that look like the above but are legitimately safe to keep.
SAFE_KEY_OVERRIDES: Tuple[str, ...] = (
    "token_type",
    "token_issued_at",
    "token_expires_at",
    "cookie_name",
    "cookie_secure",
    "cookie_httponly",
    "password_updated",
    "password_changed_at",
    "password_policy",
    "requires_password_change",
    "session_id_hash",
)

# High-signal value patterns: a JWT, a bearer token, a PEM block, a PAN.
_VALUE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("bearer", re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._\-]{16,}\b")),
    ("pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("pan", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("pg_dsn", re.compile(r"\bpostgres(?:ql)?://[^\s'\"]+:[^\s'\"@]+@[^\s'\"]+\b")),
)

# A PAN-shaped run of digits is only a card if it passes Luhn; otherwise we
# would redact every order id and timestamp in the system.
def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def is_secret_key(key: Any) -> bool:
    """True when a field name marks its value as secret-bearing."""
    name = str(key).lower()
    if any(name == safe or name.endswith(safe) for safe in SAFE_KEY_OVERRIDES):
        return False
    return any(fragment in name for fragment in SECRET_KEY_FRAGMENTS)


def _mask_freeform(value: str) -> "tuple[str, int]":
    """Mask secrets smuggled inside an otherwise free-form string.

    Returns the masked text and the number of substitutions actually made, so
    the caller's redaction counter reflects reality rather than a boolean.
    """
    out = value
    hits = 0
    for label, pattern in _VALUE_PATTERNS:
        if label == "pan":
            replaced = 0

            def _pan_sub(match: "re.Match[str]") -> str:
                nonlocal replaced
                raw = re.sub(r"[ -]", "", match.group(0))
                if _luhn_ok(raw):
                    replaced += 1
                    return f"[REDACTED:{label}]"
                return match.group(0)

            out = pattern.sub(_pan_sub, out)
            hits += replaced
        else:
            out, count = pattern.subn(f"[REDACTED:{label}]", out)
            hits += count
    return out, hits


def scrub(value: Any, _depth: int = 0) -> Tuple[Any, int]:
    """Recursively redact a JSON-ish payload.

    Returns ``(scrubbed_value, redaction_count)``. Depth-capped so a
    self-referential or pathological payload cannot recurse the function to
    death — beyond the cap the whole subtree is replaced wholesale.
    """
    if _depth > 12:
        return "[REDACTED:depth]", 1

    if isinstance(value, dict):
        out, hits = {}, 0
        for key, item in value.items():
            if is_secret_key(key):
                if (
                    isinstance(item, bool)
                    or item in (None, "", [], {})
                    or (isinstance(item, str) and item.startswith(REDACTED_PREFIX))
                ):
                    # A boolean/flag is safe AND informative — `password: true`
                    # means "the password field changed", which is exactly what
                    # an auditor needs. Empty values carry no secret either.
                    #
                    # Redaction must also be IDEMPOTENT. Integrity verification
                    # scans already-scrubbed persisted rows by calling scrub()
                    # again. Treating `[REDACTED:key=credential_state]` as a new
                    # secret made compliant rows report
                    # `unredacted_secret_in_payload`; the marker is proof the
                    # write path removed the value, not a value to redact twice.
                    out[key] = item
                else:
                    out[key] = f"{REDACTED_PREFIX}:key={str(key).lower()}]"
                    hits += 1
                continue
            scrubbed, sub_hits = scrub(item, _depth + 1)
            out[key] = scrubbed
            hits += sub_hits
        return out, hits

    if isinstance(value, (list, tuple)):
        out_list, hits = [], 0
        for item in value:
            scrubbed, sub_hits = scrub(item, _depth + 1)
            out_list.append(scrubbed)
            hits += sub_hits
        return out_list, hits

    if isinstance(value, str):
        masked, hits = _mask_freeform(value)
        return masked, hits

    return value, 0


def scrub_text(text: Any) -> Tuple[Any, int]:
    """Redact secrets inside a free-form string (``AuditLog.details_json``)."""
    if not isinstance(text, str) or not text:
        return text, 0
    return _mask_freeform(text)


def contains_secret(value: Any) -> bool:
    """Convenience predicate used by tests and by callers that want to refuse
    rather than silently rewrite."""
    _, hits = scrub(value)
    return hits > 0


def scan_keys(mapping: Any) -> List[str]:
    """Every secret-bearing key present in a mapping — used by the write-path
    test to prove the scrubber sees the field before it is persisted."""
    found: List[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if is_secret_key(key):
                    found.append(str(key))
                _walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)

    _walk(mapping)
    return found
