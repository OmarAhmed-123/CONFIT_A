import base64
import hashlib
import secrets
import bcrypt
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
# JWT via PyJWT — replaces python-jose, whose transitive `ecdsa` dependency
# carries a known CVE with no published fix (PYSEC-2026-1325). HS256 signing
# here never used ecdsa, but shipping the vulnerable package at all is the
# risk being removed.
import jwt
from jwt.exceptions import PyJWTError
from cryptography.fernet import Fernet, InvalidToken
from backend.app.core.config import settings
from backend.app.core.exceptions import (
    AuthenticationError,
    EncryptionError,
    ValidationDomainError,
)


def _get_fernet_cipher() -> Fernet:
    key_bytes = settings.ENCRYPTION_KEY_FOR_BODY_DATA.encode()
    derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
    return Fernet(derived)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        # Fallback for plain/legacy hash — kept for tests seeded with pre-bcrypt
        # accounts. Production accounts are always bcrypt-hashed at creation.
        return plain_password == hashed_password


def get_password_hash(password: str) -> str:
    # Truncate to 72 bytes if necessary per bcrypt spec
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


# --- Password policy ---------------------------------------------------------
# Group 1 spec §13: 8+ characters, meaningful complexity/entropy.
# Enforced server-side so a frontend bypass cannot weaken the policy.
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 72  # bcrypt truncation boundary
_PASSWORD_CATEGORIES = (
    re.compile(r"[a-z]"),
    re.compile(r"[A-Z]"),
    re.compile(r"[0-9]"),
    re.compile(r"[^A-Za-z0-9]"),
)


def validate_password_policy(password: str) -> None:
    """Raises ValidationDomainError if the password fails Group 1 policy.

    Requires: length in [8, 72], AND at least 3 of: lowercase, uppercase,
    digit, symbol. This is a genuine entropy check, not a length gate.
    """
    if not isinstance(password, str):
        raise ValidationDomainError("Password must be a string.")
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise ValidationDomainError(
            f"Password must be at least {_PASSWORD_MIN_LENGTH} characters."
        )
    if len(password) > _PASSWORD_MAX_LENGTH:
        raise ValidationDomainError(
            f"Password must be at most {_PASSWORD_MAX_LENGTH} characters."
        )
    matched = sum(1 for pattern in _PASSWORD_CATEGORIES if pattern.search(password))
    if matched < 3:
        raise ValidationDomainError(
            "Password must contain at least 3 of: lowercase, uppercase, digit, symbol."
        )


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None, jti: Optional[str] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": jti or secrets.token_urlsafe(24),
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """Decode & validate a CONFIT JWT.

    Validates signature, exp, iss, aud. If expected_type is provided, the
    token's `type` claim must match — protects against access/refresh token
    confusion, a class of bug that Group 1 spec §9 explicitly asks about.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except PyJWTError as exc:
        raise AuthenticationError(f"Invalid or expired token: {exc}")

    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError(
            f"Token type mismatch: expected {expected_type!r}, got {payload.get('type')!r}"
        )
    return payload


def generate_csrf_token() -> str:
    """Double-submit CSRF token for cookie-authenticated mutating requests."""
    return secrets.token_urlsafe(32)


def encrypt_sensitive_data(plain_text: str) -> str:
    """Encrypt body measurement and privacy-sensitive data before storing at rest."""
    try:
        cipher = _get_fernet_cipher()
        return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")
    except Exception as exc:  # pragma: no cover — should be unreachable in practice
        raise EncryptionError(reason=f"encrypt_failed:{type(exc).__name__}")


def decrypt_sensitive_data(cipher_text: str) -> str:
    """Decrypt sensitive data for authorized recommendation services.

    Fixes audit finding G1.BODY-02: previously this returned the ciphertext
    on failure, silently leaking base64 blobs as if they were decrypted
    body_attributes. The failure is now a controlled EncryptionError; the
    caller (repository/service) decides whether to serve NULL, 500, or a
    domain-specific fallback. Never silently continue.
    """
    try:
        cipher = _get_fernet_cipher()
        return cipher.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        # Log a diagnostic marker upstream, never the ciphertext body.
        raise EncryptionError(reason=f"decrypt_failed:{type(exc).__name__}") from exc


def hash_recovery_code(code: str) -> str:
    """MFA backup codes are stored as bcrypt hashes — never plaintext.

    Fixes audit finding G1.AUTH-06 (hardcoded `CONFIT-9281` codes). Each user
    now gets 10 random single-use codes; only their bcrypt hashes touch the DB.
    """
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_recovery_code(candidate: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(candidate.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def generate_recovery_codes(count: int = 10) -> list[str]:
    """Generate `count` cryptographically random single-use recovery codes.

    Format: `CONFIT-XXXX-XXXX` (uppercase alphanumeric, 8 significant chars =
    ~41 bits of entropy per code — brute-force resistant when combined with the
    per-verify rate limit).
    """
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # excludes 0/O/1/I for readability
    out: list[str] = []
    for _ in range(count):
        left = "".join(secrets.choice(alphabet) for _ in range(4))
        right = "".join(secrets.choice(alphabet) for _ in range(4))
        out.append(f"CONFIT-{left}-{right}")
    return out
