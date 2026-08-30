from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "CONFIT"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000

    # Security
    SECRET_KEY: str = "confit_jwt_signing_key_default_dev"
    JWT_REFRESH_SECRET: str = "confit_refresh_signing_key_default_dev"
    ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "confit"
    JWT_AUDIENCE: str = "confit.api"
    # Group 1 spec §9: avoid unnecessary 24h access-token lifetimes.
    # Short-lived access tokens (15 min) + persistent refresh tokens (30d)
    # is the correct dual-token pattern.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ENCRYPTION_KEY_FOR_BODY_DATA: str = "confit_body_privacy_key_32bytes_default"

    # OAuth 2.0 client configuration — Group 1 §7 real provider verification.
    # Missing values cause social-login to return 501 FEATURE_NOT_CONFIGURED
    # rather than silently trusting the client-supplied identity.
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = None
    APPLE_OAUTH_CLIENT_ID: Optional[str] = None
    APPLE_OAUTH_JWKS_URL: str = "https://appleid.apple.com/auth/keys"
    FACEBOOK_OAUTH_APP_ID: Optional[str] = None
    FACEBOOK_OAUTH_APP_SECRET: Optional[str] = None

    # Email provider — Group 1 §12. When unset, password-reset & verification
    # endpoints return 501 FEATURE_NOT_CONFIGURED (never a fake success).
    EMAIL_PROVIDER: Optional[str] = None  # "smtp" | "sendgrid" | None
    EMAIL_FROM_ADDRESS: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # Database & Redis
    DATABASE_URL: str = "sqlite:///./backend/data/confit.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS (Explicit Origins only when credentials enabled)
    CORS_ORIGINS: List[str] = [
        "https://confit-a.vercel.app",
        "https://confit.vercel.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:8000"
    ]

    # Live Server-Side AI API Keys (Loaded from .env/Environment)
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GROK_API_KEY: Optional[str] = None
    KLING_API_KEY: Optional[str] = None
    # Gemini model ids — verified live (2026-08): 'gemini-flash-latest' serves
    # text but 503s under vision load; the lite alias answers vision calls
    # fast and correctly, so it is the vision default. The 2.5 flash line is
    # closed to new keys; the 3.1 lite preview 503s — neither is a default.
    GEMINI_TEXT_MODEL: str = "gemini-flash-latest"
    VISION_MODEL: str = "gemini-flash-lite-latest"

    # NVIDIA Build Master & Slot Keys
    NVIDIA_API_KEY: Optional[str] = None
    NVIDIA_CHAT_KEY_2: Optional[str] = None
    NVIDIA_VISION_KEY: Optional[str] = None
    NVIDIA_EMBED_KEY: Optional[str] = None
    NVIDIA_EMBED_KEY_2: Optional[str] = None
    NVIDIA_RERANK_KEY: Optional[str] = None
    NVIDIA_TRANSLATE_KEY: Optional[str] = None
    NVIDIA_IMAGE_KEY: Optional[str] = None

    # AI Failover Configuration
    AI_PROVIDERS: str = "nvidia,groq,gemini,openai"
    AI_STYLIST_PROVIDER: str = "hybrid"
    VTON_PROVIDER: str = "hybrid"
    VTON_WORKER_URL: Optional[str] = None
    CHAT_COOLDOWN_MS: int = 600000

    # Weather (G2-S5) — disabled by default; never fabricate weather data.
    OPENWEATHER_ENABLED: bool = False
    OPENWEATHER_API_KEY: Optional[str] = None
    OPENWEATHER_BASE_URL: str = "https://api.openweathermap.org"
    OPENWEATHER_TIMEOUT_SECONDS: float = 10.0
    OPENWEATHER_UNITS: str = "metric"

    # Market & Commerce defaults
    MARKET: str = "EG"
    FULFILL_PACE: str = "demo"
    BNPL_DEFAULT_PROVIDER: str = "tabby"
    PAYMENT_DEFAULT_PROVIDER: str = "mock"
    STORAGE_PROVIDER: str = "local"
    STORAGE_LOCAL_DIR: str = "./backend/data/uploads"

    # Privacy & Retention
    POLICY_VERSION: int = 3
    ANALYTICS_K_MIN: int = 20
    TRYON_ANONYMOUS_EXPIRY_HOURS: int = 24
    DUPLICATE_ALERT_SIMILARITY_THRESHOLD: float = 0.82

    model_config = SettingsConfigDict(
        env_file=("backend/.env", ".env"),
        extra="allow",
        case_sensitive=True
    )

    # Well-known insecure defaults that ship with the public repository.
    _INSECURE_DEFAULTS = {
        "confit_jwt_signing_key_default_dev",
        "confit_refresh_signing_key_default_dev",
        "confit_body_privacy_key_32bytes_default",
    }

    @model_validator(mode="after")
    def _forbid_default_secrets_in_production(self) -> "Settings":
        """S2: refuse to boot in production with the publicly known default
        secrets — with them, anyone who can read this repo can forge admin
        JWTs. Development/test environments keep working as before."""
        if self.ENVIRONMENT.lower() == "production":
            weak = [
                name
                for name in ("SECRET_KEY", "JWT_REFRESH_SECRET", "ENCRYPTION_KEY_FOR_BODY_DATA")
                if getattr(self, name) in self._INSECURE_DEFAULTS
            ]
            if weak:
                raise ValueError(
                    f"Refusing to start in production with default secrets: {', '.join(weak)}. "
                    "Set strong random values via environment variables."
                )
        return self


settings = Settings()
