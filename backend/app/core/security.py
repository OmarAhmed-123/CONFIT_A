import base64
import hashlib
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from jose import JWTError, jwt
from cryptography.fernet import Fernet
from backend.app.core.config import settings
from backend.app.core.exceptions import AuthenticationError


def _get_fernet_cipher() -> Fernet:
    key_bytes = settings.ENCRYPTION_KEY_FOR_BODY_DATA.encode()
    derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
    return Fernet(derived)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        # Fallback for plain/legacy hash
        return plain_password == hashed_password


def get_password_hash(password: str) -> str:
    # Truncate to 72 bytes if necessary per bcrypt spec
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as exc:
        raise AuthenticationError(f"Invalid or expired token: {str(exc)}")


def encrypt_sensitive_data(plain_text: str) -> str:
    """Encrypt body measurement and privacy-sensitive data before storing at rest."""
    cipher = _get_fernet_cipher()
    return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_sensitive_data(cipher_text: str) -> str:
    """Decrypt sensitive data for authorized recommendation services."""
    try:
        cipher = _get_fernet_cipher()
        return cipher.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return cipher_text
