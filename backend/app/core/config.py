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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ENCRYPTION_KEY_FOR_BODY_DATA: str = "confit_body_privacy_key_32bytes_default"

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
