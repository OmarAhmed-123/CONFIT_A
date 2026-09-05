"""Application settings — the single environment contract.

Environments are EXPLICIT (``ENVIRONMENT`` = development | test | staging | production).
Business logic never branches on the environment; only infrastructure adapters do
(database driver, storage backend, secret policy, schema-gate strictness).

Production policy (enforced by ``_production_contract`` below, fail-closed):

* no publicly known secret (repository defaults AND every value that was ever
  published in this repository's docs / docker-compose) may sign tokens or
  encrypt body data;
* the database must be PostgreSQL — the SQLite default is a development
  convenience and can never silently become the production store;
* ``STORAGE_PROVIDER=local`` is NOT a production object store (the Vercel
  function filesystem is read-only/ephemeral). It does not block boot — the
  catalogue, auth and orders do not need it — but every upload feature answers
  501 FEATURE_NOT_CONFIGURED (``storage_service.require_production_storage``)
  and ``/health`` reports ``checks.storage`` honestly instead of a PermissionError 500.

Every setting is documented with its consumer in
``docs/PRODUCTION_DEPLOYMENT_CONTRACT.md``; ``backend/tests/test_production_parity.py``
fails when the two drift apart.
"""
import json
from typing import Any, List, Optional
from pydantic import field_validator, model_validator
from pydantic_settings import NoDecode
from typing import Annotated
from pydantic_settings import BaseSettings, SettingsConfigDict


# Every value that was EVER committed to this repository as a default, a
# docker-compose value or a documented "set this in Vercel" example.
# Public == compromised: production refuses all of them (module-level so
# pydantic does not treat it as a private model attribute).
PUBLICLY_KNOWN_SECRET_VALUES = frozenset({
    "set this in Vercel",
    "confit_jwt_signing_key_default_dev",
    "confit_refresh_signing_key_default_dev",
    "confit_body_privacy_key_32bytes_default",
    "confit_super_secret_jwt_encryption_key_2026_production_grade",
    "confit_body_privacy_encryption_secret_key_32bytes!",
    "confit_production_jwt_secret_key_2026_secure",
    "confit_production_refresh_secret_2026_secure",
    "confit_jwt_signing_key_production_2026_secure_key",
    "confit_refresh_signing_key_production_2026_secure_rotation",
})
MIN_SECRET_LENGTH = 32


PRODUCTION_ENVIRONMENTS = {"production"}
KNOWN_ENVIRONMENTS = {"development", "test", "staging", "production"}


# VTON engine registry — the server decides the production engine, and the
# resolved engine/LICENSE is exposed to operators so a non-commercial engine is
# never silently presented as commercially deployable. This is configuration
# + observability, NOT a license grant: commercial legality is the owner's
# responsibility (see docs/VTON_RESEARCH_INTEGRATION_REPORT_20260904.md).
SUPPORTED_VTON_ENGINES = frozenset({"catvton", "fashn_vton_1_5", "fashn_vton_segfee", "leffa"})

# Map engine -> (license_summary, commercially_usable, upstream_source). Values
# reflect the verified upstream terms; they are stated here because a flat
# "Apache-2.0"/"MIT" repo badge does not describe the full model/dependency
# chain (e.g. FASHN's human-parser is a SegFormer/NVIDIA non-commercial work).
VTON_ENGINE_LICENSES: dict[str, dict] = {
    "catvton": {
        "license": "CC BY-NC-SA 4.0 (model weights + repo)",
        "commercial": False,
        "source": "Zheng-Chong/CatVTON",
        "note": "Non-commercial; internal doc previously mislabelled as Apache 2.0.",
    },
    "fashn_vton_1_5": {
        "license": "Apache-2.0 (model/DWPose/YOLOX); NVIDIA Source Code License for "
                    "SegFormer via fashn-human-parser (non-commercial)",
        "commercial": False,
        "source": "fashn-AI/fashn-vton-1.5",
        "note": "Upstream model is Apache-2.0 but hard-depends on the "
                "SegFormer-derived NVIDIA non-commercial human-parser. NOT "
                "commercially clean as-is (REJECTED). Use fashn_vton_segfee.",
    },
    "fashn_vton_segfee": {
        "license": "Apache-2.0 (fork; model/DWPose/YOLOX); the non-commercial "
                    "fashn-human-parser is REMOVED from the runtime",
        "commercial": True,
        "source": "CONFIT_A fork of fashn-AI/fashn-vton-1.5 @ 7c0f10af (vendor/fashn-vton-segfee)",
        "note": "Segmentation-free-only fork: the restricted human-parser import, "
                "init and per-inference predict() are removed; enforces "
                "segmentation_free + flat-lay. Verified on real A10 GPU (see "
                "docs/VTON_COMMERCIAL_MIGRATION_REPORT). Real generated try-on "
                "image produced; parser_pre_import and parser_in_runtime both false.",
    },
    "leffa": {
        "license": "MIT (repo); SCHP / DensePose / Detectron2 chain must be "
                   "verified (not asserted here)",
        "commercial": "unverified",
        "source": "franciszzj/Leffa",
        "note": "~12 GB VRAM + native-build Detectron2/DensePose/SCHP deps; "
                "heavier than FASHN and unverified at the checkpoint level.",
    },
}


def vton_engine_metadata() -> dict:
    """Resolve the configured engine + its (honest) license/commercial status.

    Returns ``valid: False`` for an unknown engine (startup should refuse it),
    otherwise the registry entry plus the resolved engine name. Never returns
    the worker auth token.
    """
    engine = (getattr(settings, "VTON_ENGINE", None) or "fashn_vton_segfee").strip().lower()
    entry = VTON_ENGINE_LICENSES.get(engine)
    if entry is None or engine not in SUPPORTED_VTON_ENGINES:
        return {
            "engine": engine,
            "valid": False,
            "supported": sorted(SUPPORTED_VTON_ENGINES),
            "license": "UNKNOWN",
            "commercial": None,
            "source": None,
            "note": "Unsupported VTON_ENGINE value.",
        }
    return {"engine": engine, "valid": True, **entry}


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

    # CORS (Explicit Origins only when credentials enabled).
    # Vercel/Modal/docker inject plain strings; accepted forms are a JSON array
    # ('["https://a","https://b"]'), a comma-separated list ("https://a,https://b")
    # or a single origin. Parsed by _parse_cors_origins below (NoDecode stops
    # pydantic-settings from insisting on JSON and crashing at import).
    CORS_ORIGINS: Annotated[List[str], NoDecode] = [
        "https://confit-a.vercel.app",
        "https://confit.vercel.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:43123",
        "http://127.0.0.1:43123",
    ]

    # Live Server-Side AI API Keys (Loaded from .env/Environment)
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    # The provider called here is api.groq.com (Groq), not xAI's Grok. Both
    # spellings are accepted because the repository contradicted itself:
    # .env.example, backend/.env.example, README and this class said
    # GROK_API_KEY, while docs/PRODUCTION_DEPLOYMENT_CONTRACT.md and
    # docs/PRODUCTION_DEPENDENCIES.md both instruct operators to set
    # GROQ_API_KEY. An operator who followed the deployment contract therefore
    # silently disabled the one AI provider verified working end to end, and
    # every stylist request fell through to the deterministic engine while
    # looking healthy. Use the `groq_api_key` property, not either field.
    GROK_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
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

    # AI Failover Configuration
    AI_PROVIDERS: str = "nvidia,groq,gemini,openai"
    # Per-provider HTTP budget. Measured live 2026-09-04: Groq 0.48-0.56s,
    # OpenAI 1.46s, gemini-3.8-flash 2.9s when it answers and >4s when it 503s.
    # One shared 4.0s literal was generous for Groq and marginal for a thinking
    # model, so Gemini gets its own budget.
    AI_PROVIDER_TIMEOUT_SECONDS: float = 4.0
    GEMINI_TIMEOUT_SECONDS: float = 10.0
    # Completion budget for the OpenAI-compatible providers. A reasoning model
    # (openai/gpt-oss-120b) writes `message.reasoning` first and it counts
    # against the SAME budget, so the previous 300 regularly produced
    # finish_reason="length" with empty content.
    AI_MAX_TOKENS: int = 900
    AI_STYLIST_PROVIDER: str = "hybrid"
    VTON_PROVIDER: str = "hybrid"
    # Server-decided production VTON engine (the frontend never selects this).
    # Only engines in SUPPORTED_VTON_ENGINES are accepted. Wired to the worker
    # via the VTONJobRequest -> rendered_image_data_url contract, so swapping the
    # engine is a config change, not a re-platform of CONFIT_A.
    # Production default is the COMMERCIAL segmentation-free FASHN fork; the
    # non-commercial CatVTON engine is never the production default.
    VTON_ENGINE: str = "fashn_vton_segfee"
    # GPU worker (Modal). VTON_WORKER_URL is the /process endpoint. Modal
    # generates one hostname per web endpoint and hash-truncates long labels,
    # so health/readiness cannot always be derived — set them explicitly.
    # VTON_WORKER_PROCESS_URL overrides the derived /process URL when Modal
    # exposes the process endpoint at its own hostname root (a label that does
    # not end in "-process" and that the generic derivation would wrongly append
    # "/process" to).
    VTON_WORKER_URL: Optional[str] = None
    VTON_WORKER_HEALTH_URL: Optional[str] = None
    VTON_WORKER_READINESS_URL: Optional[str] = None
    VTON_WORKER_PROCESS_URL: Optional[str] = None
    # Shared secret sent as X-VTON-Admin; must equal the Modal secret
    # `confit-worker-admin-token` (env CONFIT_WORKER_ADMIN_TOKEN inside the
    # worker). Either name is accepted on the API side; VTON_WORKER_ADMIN_TOKEN wins.
    VTON_WORKER_ADMIN_TOKEN: Optional[str] = None
    CONFIT_WORKER_ADMIN_TOKEN: Optional[str] = None
    # T4 revision-consistency gate: the Git SHA the Modal worker is EXPECTED to
    # run (the commit `modal deploy` was executed from). /health/vton-contract
    # compares it with the worker's reported git_sha. Defaults to the API's own
    # deployment SHA (Vercel injects VERCEL_GIT_COMMIT_SHA) when unset.
    VTON_WORKER_EXPECTED_GIT_SHA: Optional[str] = None
    VTON_WORKER_TIMEOUT_SECONDS: float = 90.0
    VTON_WORKER_HEALTH_TIMEOUT_SECONDS: float = 5.0
    VTON_WORKER_MAX_RETRIES: int = 3
    CHAT_COOLDOWN_MS: int = 600000

    # Weather (G2-S5) — disabled by default; never fabricate weather data.
    OPENWEATHER_ENABLED: bool = False
    OPENWEATHER_API_KEY: Optional[str] = None
    OPENWEATHER_BASE_URL: str = "https://api.openweathermap.org"
    OPENWEATHER_TIMEOUT_SECONDS: float = 10.0
    OPENWEATHER_UNITS: str = "metric"

    # Market & Commerce defaults
    MARKET: str = "EG"
    # Money: the currency the CATALOG PRICE BOOK is denominated in (every
    # seeded/migrated product carries currency='USD'), and the optional FX
    # table used to settle a market in its own currency instead.
    # MARKET_FX_RATES is a JSON object of CURRENCY -> rate FROM
    # PRICING_CURRENCY, e.g. {"EGP": "48.5", "AED": "3.6725"}. Rates are a
    # treasury input: with no rate configured for a market's currency the
    # resolver settles in PRICING_CURRENCY (today's behaviour) and logs
    # market_fx_rate_not_configured, because stamping a market currency on an
    # amount that was never priced in it would mislabel money.
    PRICING_CURRENCY: str = "USD"
    MARKET_FX_RATES: str = ""
    FULFILL_PACE: str = "demo"
    BNPL_DEFAULT_PROVIDER: str = "tabby"
    PAYMENT_DEFAULT_PROVIDER: str = "mock"
    PAYMENTS_LIVE: bool = False
    TABBY_API_KEY: Optional[str] = None
    TAMARA_API_KEY: Optional[str] = None
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    PAYMOB_API_KEY: Optional[str] = None
    TAX_RATE: float = 0.05
    FREE_SHIPPING_THRESHOLD: float = 250.0
    STANDARD_SHIPPING_FEE: float = 15.0
    EXPRESS_SHIPPING_FEE: float = 35.0
    RETURN_WINDOW_DAYS: int = 30
    STORAGE_PROVIDER: str = "local"
    STORAGE_LOCAL_DIR: str = "./backend/data/uploads"
    # C24 FIX: Production storage - S3/R2 for persistence
    AWS_S3_BUCKET: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: Optional[str] = None
    S3_PUBLIC_URL_BASE: Optional[str] = None

    # Privacy & Retention
    POLICY_VERSION: int = 3
    ANALYTICS_K_MIN: int = 20
    TRYON_ANONYMOUS_EXPIRY_HOURS: int = 24
    # Group 4 §30: duplicate-purchase thresholds, centralized. Strict means
    # near-exact duplicate (type + color required by the scorer, 90/100);
    # loose means similar style/category (65/100: type + one more signal).
    DUPLICATE_ALERT_SIMILARITY_THRESHOLD: float = 0.90
    DUPLICATE_ALERT_LOOSE_THRESHOLD: float = 0.65

    model_config = SettingsConfigDict(
        env_file=("backend/.env", ".env"),
        extra="allow",
        case_sensitive=True
    )

    # Secrets that are PUBLIC KNOWLEDGE: the repository defaults plus every value
    # that was ever published in this repository (docs/CONFIT_Production_Run_and_
    # Environment_Guide.md, PRODUCTION_KEYS_AND_ENV_CONFIG.md, DEPLOYMENT_GUIDE_
    # FREE_HOSTING.md, docker-compose.yml). On 2026-09-03 the production
    # deployment was found signing JWTs with the docker-compose value — anyone
    # with the repo could forge an admin token. Listing them here makes that
    # state a boot failure instead of a silent compromise.

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"CORS_ORIGINS is not valid JSON: {exc}") from exc
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON must be a list of origins")
                value = parsed
            else:
                value = text.split(",")
        origins: List[str] = []
        for item in value:
            origin = str(item).strip().strip('"').strip("'").rstrip("/")
            if not origin:
                continue
            if origin != "*" and not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin {origin!r} must start with http:// or https://")
            if origin not in origins:
                origins.append(origin)
        return origins

    @field_validator("VTON_ENGINE", mode="after")
    @classmethod
    def _validate_vton_engine(cls, value: str) -> str:
        """Fail closed on an unknown VTON_ENGINE rather than silently falling
        back to a different model at runtime (no uncontrolled model selection).
        """
        engine = (value or "").strip().lower()
        if engine not in SUPPORTED_VTON_ENGINES:
            raise ValueError(
                f"VTON_ENGINE={value!r} is not supported; "
                f"expected one of {sorted(SUPPORTED_VTON_ENGINES)}"
            )
        return engine

    @property
    def groq_api_key(self) -> Optional[str]:
        """The Groq key under whichever spelling the operator used.

        GROQ_API_KEY (correct vendor name, and what the production deployment
        contract documents) wins; GROK_API_KEY is kept as a backwards-compatible
        alias so existing deployments keep working. Empty strings from a
        partially-filled .env are treated as unset.
        """
        for value in (self.GROQ_API_KEY, self.GROK_API_KEY):
            if value and value.strip():
                return value.strip()
        return None

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in PRODUCTION_ENVIRONMENTS

    @model_validator(mode="after")
    def _production_contract(self) -> "Settings":
        """Fail closed in production. Development/test keep their conveniences,
        but ONLY because ENVIRONMENT says so explicitly."""
        env = self.ENVIRONMENT.lower()
        if env not in KNOWN_ENVIRONMENTS:
            raise ValueError(
                f"ENVIRONMENT={self.ENVIRONMENT!r} is not one of {sorted(KNOWN_ENVIRONMENTS)}"
            )
        if env not in PRODUCTION_ENVIRONMENTS:
            return self

        problems: List[str] = []
        for name in ("SECRET_KEY", "JWT_REFRESH_SECRET", "ENCRYPTION_KEY_FOR_BODY_DATA"):
            value = getattr(self, name) or ""
            if value in PUBLICLY_KNOWN_SECRET_VALUES:
                problems.append(f"{name} is a publicly known value (repository default or published in docs)")
            elif len(value) < MIN_SECRET_LENGTH:
                problems.append(f"{name} is shorter than {MIN_SECRET_LENGTH} characters")

        db = (self.DATABASE_URL or "").lower()
        if not db.startswith(("postgresql://", "postgres://", "postgresql+")):
            problems.append(
                "DATABASE_URL must be PostgreSQL in production (the sqlite default is development-only)"
            )

        if problems:
            raise ValueError(
                "Refusing to start in production: " + "; ".join(problems)
                + ". Set strong random values / production services via environment variables."
            )
        return self


settings = Settings()
