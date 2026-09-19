from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.app.models.user import UserRole


class UserRegister(BaseModel):
    """Public self-service registration.

    SECURITY INVARIANT (P0, production-exploited 2026-09-05): this endpoint
    must NEVER accept a client-supplied role. The `role` field that used to
    live here let any caller create `role=admin` (and brand-staff) accounts
    directly. The field is removed from the contract, and `AuthService.
    register` hard-codes `UserRole.CONSUMER` — the server-side invariant,
    not schema visibility, is the enforcement point.

    `model_config = ignore` (same pattern as `SocialLoginRequest` below)
    silently discards any stray `role` / privilege fields an attacker keeps
    sending, so the endpoint stays 201 for legitimate payloads instead of
    422 — no oracle for probing which fields are rejected.
    """

    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    # Server-side password policy validation is enforced in AuthService.register
    # via validate_password_policy — Pydantic min_length remains the FIRST
    # gate (fast fail, no DB round-trip), the entropy rules the second.
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    phone: Optional[str] = None
    preferred_language: str = "en"
    # What the person is registering FOR ("consumer" | "brand_partner").
    # This is DATA, never a privilege: `AuthService.register` still hard-codes
    # role=consumer and the partner path requires a reviewed application.
    registration_intent: str = Field(default="consumer", max_length=32)


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


class RefreshTokenOptionalRequest(BaseModel):
    """Lenient body for POST /auth/refresh.

    The browser SPA always sends an empty JSON object and relies on the
    httpOnly confit_refresh cookie; a required-field model would turn that
    into a 422 before the handler ever runs. API/mobile clients keep sending
    {"refresh_token": "..."} (validated as a non-empty string when present).
    """

    refresh_token: Optional[str] = None


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
    # Server-authoritative onboarding/lifecycle view (task §4). The SPA routes
    # on `onboarding.next_action`; it is computed server-side so no client
    # state can steer a user into an area they are not authorized for.
    registration_intent: str = "consumer"
    partner_access: Optional[str] = None
    partner_application_status: Optional[str] = None
    onboarding: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class OnboardingStateOut(BaseModel):
    account_state: str
    role: str
    registration_intent: str
    email_verified: bool
    is_active: bool
    profile_completed: bool
    partner_access: str
    partner_application_status: Optional[str] = None
    next_action: Dict[str, Any]
    allowed_areas: List[str] = Field(default_factory=list)
    pending_invitation: Optional[Dict[str, Any]] = None


class EmailDeliveryStatusOut(BaseModel):
    purpose: Optional[str] = None
    status: str
    accepted: bool
    provider: Optional[str] = None
    error_class: Optional[str] = None
    attempts: int = 0
    last_attempt_at: Optional[str] = None


class EmailChangeRequestIn(BaseModel):
    new_email: EmailStr


class EmailChangeConfirmIn(BaseModel):
    token: str = Field(min_length=8, max_length=512)


# --- partner onboarding ------------------------------------------------------

class PartnerApplicationCreate(BaseModel):
    """Applicant-supplied facts only.

    Deliberately absent: `role`, `brand_id`, `status`, `user_id` — every
    authorization-bearing field is server-side (task §0.12).
    """

    model_config = ConfigDict(extra="ignore")

    brand_name: str = Field(min_length=2, max_length=255)
    legal_name: Optional[str] = Field(default=None, max_length=255)
    website: Optional[str] = Field(default=None, max_length=500)
    market: str = Field(default="EG", max_length=8)
    category: Optional[str] = Field(default=None, max_length=120)
    catalogue_size: Optional[str] = Field(default=None, max_length=40)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    message: Optional[str] = Field(default=None, max_length=4000)


class PartnerApplicationOut(BaseModel):
    id: int
    status: str
    brand_name: str
    market: str
    category: Optional[str] = None
    contact_name: str
    website: Optional[str] = None
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    brand_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class PartnerApplicationDecision(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


# --- invitations -------------------------------------------------------------

class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="brand_staff", max_length=32)
    # Optional so a brand owner's own tenant is used by default; an admin
    # inviting into another brand must name it explicitly.
    brand_id: Optional[int] = None


class InvitationOut(BaseModel):
    id: int
    email: str
    role: str
    brand_id: int
    status: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvitationPreviewOut(BaseModel):
    status: str
    valid: bool
    email_masked: Optional[str] = None
    brand_name: Optional[str] = None
    role: Optional[str] = None
    expires_at: Optional[str] = None


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    # Only required when the invited address has no CONFIT account yet.
    full_name: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=72)


class GDPRExportResponse(BaseModel):
    user: UserOut
    profile: Optional[Dict[str, Any]]
    wardrobe_items_count: int
    orders_count: int
    tryon_sessions_count: int
    exported_at: datetime
    data_retention_policy: str
