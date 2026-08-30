from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.app.models.user import UserRole


class UserRegister(BaseModel):
    email: EmailStr
    # Server-side password policy validation is enforced in AuthService.register
    # via validate_password_policy — Pydantic min_length remains the FIRST
    # gate (fast fail, no DB round-trip), the entropy rules the second.
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    phone: Optional[str] = None
    role: UserRole = UserRole.CONSUMER
    preferred_language: str = "en"


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


class SocialLoginRequest(BaseModel):
    """Only the provider name and the provider-issued token cross the wire.

    Previously accepted `email` and `full_name` from the client — that
    field pair was the auth-bypass surface (audit finding G1.SEC-02). The
    identity is now taken exclusively from the provider's verified
    response inside `AuthService.social_login`.

    `model_config = ignore` deliberately silently discards any extra
    fields (e.g. an attacker who keeps sending `email` / `full_name`) so
    the endpoint stays a 200 for a legit provider_token, not a 422 that
    would train attackers to try harder. The identity path never reads
    those extra fields.
    """
    provider: str = Field(description="One of: google, apple, facebook")
    provider_token: str = Field(min_length=8, description="ID token (Google/Apple) or access token (Facebook).")

    model_config = ConfigDict(extra="ignore")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserOut"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class MFASetupResponse(BaseModel):
    secret: str
    qr_uri: str
    # Empty at setup time; the plaintext codes come back from /mfa/verify.
    backup_codes: List[str] = Field(default_factory=list)


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    phone: Optional[str]
    preferred_language: str
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    created_at: datetime
    brand_id: Optional[int] = None
    has_profile: bool = False

    model_config = ConfigDict(from_attributes=True)


class GDPRExportResponse(BaseModel):
    user: UserOut
    profile: Optional[Dict[str, Any]]
    wardrobe_items_count: int
    orders_count: int
    tryon_sessions_count: int
    exported_at: datetime
    data_retention_policy: str
