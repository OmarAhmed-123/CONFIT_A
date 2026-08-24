from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from backend.app.models.user import UserRole


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    phone: Optional[str] = None
    role: UserRole = UserRole.CONSUMER
    preferred_language: str = "en"


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


class SocialLoginRequest(BaseModel):
    provider: str = Field(description="google, apple, facebook")
    access_token: str
    email: EmailStr
    full_name: str


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
    backup_codes: List[str]


class MFAVerifyRequest(BaseModel):
    code: str


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
