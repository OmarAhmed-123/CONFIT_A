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
import os
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


def _env_files() -> tuple:
    """Dotenv files to load — EMPTY when the test suite is running.

    The suite must be hermetic. Until 2026-09-27 these settings always read
    ``backend/.env``, which meant a developer's local file silently changed
    BUSINESS behaviour under pytest, not just infrastructure wiring.

    MEASURED the first time a populated backend/.env existed: 13 tests across
    five files flipped to red — mood-board upload, wardrobe upload validation,
    commerce settlement currency and the health-readiness contract — purely
    because the file set STORAGE_PROVIDER=s3 and a real DATABASE_URL. The same
    commit was green on a clean checkout. A suite whose result depends on an
    untracked, gitignored file is not a suite you can trust, and "works on my
    machine" is exactly the failure mode it is supposed to prevent.

    ``conftest.py`` sets CONFIT_IGNORE_DOTENV=1 before importing this module, so
    tests read ONLY explicit environment variables and the defaults declared
    here. Production and development are unaffected.
    """
    if os.environ.get("CONFIT_IGNORE_DOTENV") == "1":
        return ()
    return ("backend/.env", ".env")


PRODUCTION_ENVIRONMENTS = {"production"}
KNOWN_ENVIRONMENTS = {"development", "test", "staging", "production"}


# VTON engine registry — the server decides the production engine, and the
# resolved engine/LICENSE is exposed to operators so a non-commercial engine is
# never silently presented as commercially deployable. This is configuration
# + observability, NOT a license grant: commercial legality is the owner's
# responsibility (see docs/VTON_RESEARCH_INTEGRATION_REPORT_20260904.md).
SUPPORTED_VTON_ENGINES = frozenset({"catvton", "fashn_vton_1_5", "fashn_vton_segfee", "fashn_v15", "leffa"})

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
    "fashn_v15": {
        "license": "Apache-2.0 (pipeline/DWPose/YOLOX); NVIDIA Source Code License "
                   "for SegFormer via fashn-human-parser (non-commercial)",
        "commercial": False,
        "multigarment": True,
        "source": "pristine fashn-AI/fashn-vton-1.5 @ 7c0f10af (vendor/fashn-vton-1.5)",
        "note": "Feature 03 multi-garment engine (tops+bottoms composed in one "
                "worker call; parser-masked overlays; on-model garment photos "
                "supported via parser segmentation). OWNER DECISION 2026-10-01: "
                "ship the non-commercial parser while the project is early-stage; "
                "SWAP to a licensed parser before commercial scale — the swap "
                "seam is engine/fashn_v15.py parser_impl (one class, zero "
                "upstream modification). Reported honestly as non-commercial "
                "until that swap lands.",
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

    # Tamper-evident audit chain (P0 closure, 2026-09-22 admin audit).
    # A DEDICATED HMAC key — deliberately separate from SECRET_KEY so a JWT
    # key leak alone cannot re-forge the audit chain (key separation).
    # When unset, core/audit_chain.py derives a dev/test fallback from
    # SECRET_KEY via HMAC with a fixed label (never equal to SECRET_KEY
    # itself). Production deployments must set a real value.
    # AUDIT_CHAIN_KEY_VERSION is persisted per row (chain_key_version) so the
    # key can rotate without invalidating history: bump the version, keep the
    # retired key resolvable in audit_chain.resolve_key.
    AUDIT_HMAC_KEY: Optional[str] = None
    AUDIT_CHAIN_KEY_VERSION: int = 1

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
    # When set (smtp), a REAL transport must be reachable (see
    # services/email_service.py) — a provider flag without SMTP_HOST is a
    # configuration error and refuses to boot in production (validator below).
    EMAIL_PROVIDER: Optional[str] = None  # "smtp" | "brevo_api" | None
    EMAIL_FROM_ADDRESS: Optional[str] = None
    # Brevo transactional HTTP API (https://api.brevo.com/v3/smtp/email).
    # WHY IT EXISTS (measured 2026-09-30 → 2026-10-06): Brevo's SMTP relay
    # enforces an IP allow-list and Vercel sends from a rotating pool —
    # smtp-relay.brevo.com answered `525 5.7.1 Unauthorized IP address` to
    # every production send while the SAME account's HTTP API accepted
    # requests. The HTTP path authenticates by key, not source IP, so it is
    # the transport that actually works from serverless.
    BREVO_API_KEY: Optional[str] = None
    PARTNER_LEAD_NOTIFY_EMAIL: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # Where the SPA lives — used to build action links (reset/verify) inside
    # transactional emails. No default magic-prod value: previews and local
    # dev point at themselves; production MUST set it explicitly.
    FRONTEND_BASE_URL: str = "http://localhost:43123"

    # Database & Redis
    DATABASE_URL: str = "sqlite:///./backend/data/confit.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    #: Where the rate limiter keeps its counters.
    #:
    #: Deliberately ``None``. The honest default is the in-process store, because
    #: that is what this deployment actually has: a value here would be a claim
    #: about infrastructure, and MEASURED 2026-09-24 there is no managed Redis
    #: provisioned for this project. A synthesised ``redis://…`` default would
    #: make the limiter look global while every instance still kept its own
    #: counters — a fake distributed limiter, which is forbidden.
    #:
    #: Set it to a real endpoint (``redis://``/``rediss://``) and the limiter's
    #: counters become shared by every instance. When the shared store is
    #: unreachable the limiter degrades to the in-process store rather than
    #: failing requests, and ``/health`` reports that state — see
    #: ``core.rate_limit.rate_limit_store_report``.
    RATE_LIMIT_STORAGE_URL: Optional[str] = None

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
    # `local_gpu` leads the chain so a self-hosted model is PREFERRED the
    # moment one exists. It is skipped with zero cost while
    # LOCAL_LLM_BASE_URL is unset, so listing it first costs nothing today
    # and needs no code change on the day the GPU subscription renews.
    AI_PROVIDERS: str = "local_gpu,nvidia,groq,gemini,openai,unorouter"

    # ── Self-hosted stylist inference (activates on GPU renewal) ──────────
    #
    # Point this at any OpenAI-compatible server and the stylist starts
    # using it. vLLM exposes exactly that surface, so:
    #
    #   python -m vllm.entrypoints.openai.api_server \
    #     --model Qwen/Qwen2.5-7B-Instruct --served-model-name qwen-stylist \
    #     --max-model-len 8192 --port 8001
    #   LOCAL_LLM_BASE_URL=http://<host>:8001/v1
    #
    # Empty = the leg is skipped. That is the whole activation mechanism:
    # one environment variable, no redeploy of application logic, and no
    # dead code sitting in the request path while it is unset.
    LOCAL_LLM_BASE_URL: str = ""
    LOCAL_LLM_MODEL: str = "qwen-stylist"
    LOCAL_LLM_API_KEY: str = "EMPTY"  # vLLM ignores it; header must exist
    #: Self-hosted means no queue and no egress, so a tight budget is right:
    #: if the box is slow the hosted chain is a better answer than waiting.
    LOCAL_LLM_TIMEOUT_SECONDS: float = 12.0

    # ── Visual search embeddings (activates on GPU renewal) ──────────────
    #
    # HopitAI/moda-fashion-distilled, a SigLIP model distilled for fashion
    # retrieval. torch + open_clip + weights is ~3 GB against a 250 MB
    # serverless limit, so the model runs behind an HTTP endpoint and the
    # app holds only a client.
    #
    #   MODA_EMBED_BASE_URL=http://<gpu-host>:8002
    #
    # Unset = visual search keeps its existing keyword behaviour, and
    # nothing in this path executes. One variable is the whole switch.
    MODA_EMBED_BASE_URL: str = ""
    #: Shared secret for the embedding worker. Falls back to the try-on
    #: worker token so one rotation covers both rather than drifting.
    MODA_EMBED_TOKEN: Optional[str] = None
    #: Embedding is one forward pass (0.34s measured on CPU, faster on GPU).
    #: A tight budget so an unhealthy box falls back instead of stalling.
    MODA_EMBED_TIMEOUT_SECONDS: float = 15.0

    # AI readiness probe (2026-09-23). `ai_stylist_live` was `bool(key)`, which
    # is configuration, not reachability. The probe reads each provider's model
    # catalogue (free — no chat completion, no tokens, no quota burn) to verify
    # DNS/TLS/status and that the credential is accepted. It runs in the
    # background off a TTL cache, so no request waits on it, and its snapshot is
    # WITHDRAWN past the max age so a stale "ready" can never be reported.
    AI_PROBE_ENABLED: bool = True
    AI_PROBE_TTL_SECONDS: float = 300.0
    #: Hard maximum age: past this the verdict becomes `not_probed`, not `ready`.
    #: 30 min = 2x the 15-minute uptime-monitor cadence that refreshes it, so a
    #: single missed cycle does not withdraw a verdict that is still good.
    AI_PROBE_MAX_AGE_SECONDS: float = 1800.0
    #: Per-provider attempt budget. Deliberately short: /health must not wait.
    AI_PROBE_TIMEOUT_SECONDS: float = 3.0
    #: TOTAL budget for the inline refresh /health performs when its cached
    #: verdict is missing or stale. Providers not attempted inside the budget
    #: are reported as unmeasured, never guessed.
    AI_PROBE_SYNC_BUDGET_SECONDS: float = 5.0
    #: Floor between background refresh attempts started from a CONSUMER read
    #: path (seconds). The shopper-facing capability contract may ask this
    #: instance to establish its own AI-readiness verdict; without a floor a
    #: provider that is down would be retried by page traffic, which is the
    #: self-inflicted burst services/ai_readiness.py refuses to create.
    AI_PROBE_MIN_RETRY_SECONDS: float = 30.0
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
    # StyleList Mode A (multi-image styling). When False, image turns are refused
    # with a 503 instead of being analysed; text-only Mode B is unaffected.
    STYLIST_VISION_ENABLED: bool = True
    # Per-attempt budget for the vision call. Vision is slower than text: the
    # registry measured nano-omni at 24.6s, diffusiongemma at ~1-3s.
    STYLIST_VISION_TIMEOUT_SECONDS: float = 15.0
    # Image-carrying stylist turns per caller per hour (cost control, STY-08).
    STYLIST_IMAGE_TURNS_PER_HOUR: int = 5
    AI_STYLIST_PROVIDER: str = "hybrid"
    VTON_PROVIDER: str = "hybrid"
    # Server-decided production VTON engine (the frontend never selects this).
    # Only engines in SUPPORTED_VTON_ENGINES are accepted. Wired to the worker
    # via the VTONJobRequest -> rendered_image_data_url contract, so swapping the
    # engine is a config change, not a re-platform of CONFIT_A.
    # Production default is the COMMERCIAL segmentation-free FASHN fork; the
    # non-commercial CatVTON engine is never the production default.
    VTON_ENGINE: str = "fashn_vton_segfee"

    # Which licence class of try-on engine may serve traffic.
    #
    #   pilot      -> research weights (CC BY-NC-SA) are permitted. Correct
    #                 while CONFIT is evaluating: no custom domain, no trading.
    #   commercial -> ONLY engines whose whole dependency chain is cleared for
    #                 commercial use, i.e. fashn_vton_segfee.
    #
    # Flipping this one value retires every non-commercial engine from the
    # routing chain (see providers/vton/registry.resolve_chain). It filters
    # rather than reorders, so a research engine cannot survive as a
    # "temporary" fallback once the platform starts trading.
    VTON_LICENSE_TIER: str = "pilot"
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
    # Optional Authorization header VALUE for the GPU worker's platform
    # gateway (e.g. "Api-Key <key>" when the worker runs on Baseten, whose
    # router requires its own credential on every route IN ADDITION to our
    # X-VTON-Admin token). Unset for a directly-exposed worker (Modal).
    VTON_WORKER_GATEWAY_AUTHORIZATION: Optional[str] = None
    # Live worker observability + fail-fast circuit (audit closure 2026-09-21).
    # Before this, /health and /try-on/capabilities derived "available" from the
    # presence of env vars, and every request paid ~39 s of readiness retries
    # before failing. The probe is cached and refreshed in the background; the
    # circuit makes the Nth user fail in milliseconds instead of ~39 s.
    VTON_WORKER_PROBE_TTL_SECONDS: float = 60.0
    VTON_WORKER_PROBE_TIMEOUT_SECONDS: float = 6.0
    VTON_CIRCUIT_FAILURE_THRESHOLD: int = 2
    VTON_CIRCUIT_OPEN_SECONDS: float = 120.0

    # Feature 04 — Smart Wardrobe extraction worker (Modal CPU app
    # `confit-wardrobe-worker`: SCHP-ATR-18 parsing + BiRefNet_lite matting,
    # both MIT). WARDROBE_WORKER_URL is the full /extract endpoint URL
    # (Modal exposes each web endpoint at its own hostname root — same
    # reason VTON_WORKER_URL/PROCESS_URL are set explicitly).
    WARDROBE_WORKER_URL: Optional[str] = None
    WARDROBE_WORKER_HEALTH_URL: Optional[str] = None
    # Dedicated credential (Modal secret `confit-wardrobe-admin-token`, env
    # VTON_WORKER_ADMIN_TOKEN inside that worker). Separate from the VTON
    # token on purpose: the VTON workers are frozen (GPU gate) and must keep
    # serving with the shared secret, while this one can be rotated freely.
    # Sent as the X-VTON-Admin header, mirroring the other worker shells.
    WARDROBE_WORKER_ADMIN_TOKEN: Optional[str] = None
    # CPU extraction is real but slow: parse ~1s + ~10-15s matting per
    # garment (measured live 2026-10-02: 29-45s for 3 garments, plus cold
    # start). 180s covers a 6-garment extraction with margin.
    WARDROBE_WORKER_TIMEOUT_SECONDS: float = 180.0

    # Feature 05 — body measurements from a photo (Modal CPU app
    # `confit-anthropometry-worker`: MediaPipe pose_landmarker_heavy +
    # vendored Landmarks2Anthropometry VISAPP-2024 Bayesian ridge, upstream
    # license null -> unlicensed-research-only pilot tier, disclosed in every
    # response). ANTHROPOMETRY_WORKER_URL is the full /estimate endpoint URL.
    ANTHROPOMETRY_WORKER_URL: Optional[str] = None
    # Dedicated credential (Modal secret `confit-anthropometry-admin-token`,
    # env ANTHROPOMETRY_WORKER_ADMIN_TOKEN inside that worker) — rotatable
    # independently of the wardrobe/VTON workers.
    ANTHROPOMETRY_WORKER_ADMIN_TOKEN: Optional[str] = None
    # CPU pose ~0.1-3s + linear predict (measured live 2026-10-02: ~0.6s
    # warm; cold start adds ~10-20s). 120s leaves generous margin.
    ANTHROPOMETRY_WORKER_TIMEOUT_SECONDS: float = 120.0

    # Feature 07 — Brand Portal product auto-tagging (Modal CPU app
    # `confit-tagging-worker`: FashionCLIP patrickjohncyh/fashion-clip MIT
    # + GLiNER urchade/gliner_multi-v2.1 Apache-2.0, both commercial-safe).
    # TAGGING_WORKER_URL is the full /tag endpoint URL.
    TAGGING_WORKER_URL: Optional[str] = None
    # Dedicated credential (Modal secret `confit-tagging-admin-token`, env
    # TAGGING_WORKER_ADMIN_TOKEN inside that worker) — rotatable
    # independently of the other workers.
    TAGGING_WORKER_ADMIN_TOKEN: Optional[str] = None
    # Measured live 2026-10-03: ~2.1s warm; cold start ~15-30s (both models
    # load at container start). 90s covers cold start with margin.
    TAGGING_WORKER_TIMEOUT_SECONDS: float = 90.0

    # Feature 06 — Outfit Builder compatibility (Modal CPU app
    # `confit-outfit-worker`: OutfitTransformer OutfitCLIPTransformer —
    # frozen FashionCLIP encoder + 6-layer transformer, Polyvore-trained,
    # MIT; TATTOO (arXiv:2509.23242) pinned as the type-aware eval rubric).
    # Each Modal web endpoint has its own URL (stable via endpoint labels),
    # so — exactly like TAGGING_WORKER_URL — the config holds FULL endpoint
    # URLs. COMPAT_URL is required for the model path; FITB_URL enables
    # fill-in-the-blank on top.
    OUTFIT_WORKER_COMPAT_URL: Optional[str] = None
    OUTFIT_WORKER_FITB_URL: Optional[str] = None
    # Dedicated credential (Modal secret `confit-outfit-admin-token`, env
    # OUTFIT_WORKER_ADMIN_TOKEN inside that worker) — rotatable
    # independently of the other workers.
    OUTFIT_WORKER_ADMIN_TOKEN: Optional[str] = None
    # CPU inference ~2-5s warm; cold start adds ~20-40s (769MB checkpoint
    # from the Modal volume; the complementary model loads lazily on the
    # first fill-in-the-blank call). 120s covers a cold start with margin.
    OUTFIT_WORKER_TIMEOUT_SECONDS: float = 120.0

    # Self-hosted Qwen2.5-VL vision worker (LOCAL FALLBACK). When
    # QWEN_VL_WORKER_URL is set, VisualSearchAIProvider.fallback uses the local
    # Qwen worker when Gemini is exhausted/unavailable. Unset => unchanged.
    QWEN_VL_ENABLED: bool = True
    QWEN_VL_WORKER_URL: Optional[str] = None
    QWEN_VL_WORKER_TOKEN: Optional[str] = None
    QWEN_VL_MODEL_ID: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    QWEN_VL_TIMEOUT_SECONDS: float = 90.0
    # Transport to the local Qwen worker. "web" = stateless HTTP web endpoint
    # (VTON-style; requires a Modal tier that sustains a warm container for this
    # 16.6 GB model). "remote" = the backend calls the deployed Modal Function
    # `vlm_analyze` via .remote() (server-to-server; the container is held for the
    # call, so the heavy cold start is fine — the robust path when a warm container
    # is unavailable). Default "web" keeps the existing httpx behaviour. "remote"
    # authenticates with MODAL_TOKEN_ID / MODAL_TOKEN_SECRET (server-side only,
    # never committed).
    QWEN_VL_TRANSPORT: str = "web"
    QWEN_VL_REMOTE_APP: str = "confit-vlm-worker"
    QWEN_VL_REMOTE_FN: str = "vlm_analyze"
    # Temporary (NON-persistent) delivery of generated try-on images.
    # Product requirement (2026-09-05): the generated image is downloadable by
    # the authenticated requesting user but must NEVER be stored permanently
    # (no Postgres, no R2/S3, no local disk, no repo/frontend asset). The image
    # travels in the authenticated completion response (guaranteed vehicle) and
    # is staged in a process-local TTL cache for the one-shot download endpoint
    # (best effort on serverless; 410 GONE when the instance no longer holds
    # it). Only the token hash + expiry are persisted, on the job row.
    VTON_DELIVERY_TTL_SECONDS: float = 900.0
    VTON_DELIVERY_MAX_IMAGES: int = 16
    VTON_DELIVERY_MAX_BYTES: int = 64 * 1024 * 1024
    CHAT_COOLDOWN_MS: int = 600000

    # Visual Search Enhancement
    # Feature flag for deterministic scoring improvements.
    # OFF (default): baseline token-matching scoring.
    # ON: enhanced scoring with synonym normalization, category hierarchy,
    #     LAB color similarity, style weighting.
    USE_ENHANCED_VISUAL_SEARCH_SCORING: bool = False

    # UnoRouter — unified AI gateway (api.unorouter.com).
    # OpenAI-compatible endpoint to many models (Gemini, GLM, DeepSeek, Qwen, etc.)
    # Free-tier rate limit: ~1 req/min per account. Integrated as additional
    # fallback AFTER the existing direct providers (NVIDIA, Groq, Gemini, OpenAI).
    UNOROUTER_API_KEY: Optional[str] = None
    # Error tracking (core/error_tracking.py). GlitchTip is Sentry-SDK
    # compatible, so this DSN also accepts a Sentry DSN unchanged. Unset =
    # tracking silently disabled (local dev and CI must not need a DSN).
    GLITCHTIP_DSN: Optional[str] = None
    UNOROUTER_CHAT_MODEL: str = "glm-5.3-flash:free"
    UNOROUTER_VISION_MODEL: str = "qwen2.5-vl-7b-instruct-awq:free"
    UNOROUTER_TIMEOUT_SECONDS: float = 30.0

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
    # The currency the storefront DISPLAYS when the shopper has expressed no
    # preference and the market gives no stronger signal. EGP because CONFIT's
    # home market is Egypt; it is deliberately SEPARATE from PRICING_CURRENCY,
    # which is the denomination the price book is stored in. Conflating them
    # would mean re-denominating every product row to change a default.
    DEFAULT_DISPLAY_CURRENCY: str = "EGP"
    # Live FX (services/fx_rates.py). Disable to pin the storefront to the
    # static MARKET_FX_RATES table — e.g. during a treasury freeze.
    FX_LIVE_RATES_ENABLED: bool = True
    FX_RATE_TTL_SECONDS: int = 21600
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
    # AWS-SDK-standard name for the S3 endpoint. Neon Object Storage (and the
    # AWS SDK env chain) injects AWS_ENDPOINT_URL_S3, so it is accepted as a
    # fallback; an explicit S3_ENDPOINT_URL always wins.
    AWS_ENDPOINT_URL_S3: Optional[str] = None
    # Private buckets (Neon Object Storage's default access level) reject
    # anonymous browser reads of plain endpoint URLs. The API layer therefore
    # swaps owned-object URLs for time-limited presigned GET URLs at response
    # time. The database keeps the canonical URL forever; the signature TTL
    # applies to API responses only.
    S3_PRESIGN_EXPIRY_SECONDS: int = 3600


    # Audit closure 2026-09-21 (VTON/Photo-Match, gap "storage is local"):
    # the documented aliases in backend/.env.example (S3_ENDPOINT /
    # S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET_PRIVATE) never bound to
    # anything the storage backend read, so an operator who filled in the
    # example file exactly as written still booted with production_grade=
    # False. They are accepted as aliases here (see Settings.s3_* properties)
    # instead of silently ignored.
    S3_ENDPOINT: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_BUCKET_PRIVATE: Optional[str] = None
    S3_BUCKET_PUBLIC: Optional[str] = None
    # Server-side encryption enforced on every PUT (AES256 unless the bucket
    # policy requires KMS). A bucket that refuses an encrypted PUT is a
    # configuration error we surface loudly instead of retrying unencrypted.
    S3_SERVER_SIDE_ENCRYPTION: str = "AES256"
    # Live (network) bucket probe used by /health. Off by default so tests and
    # local runs stay deterministic; production enables it via env.
    STORAGE_PROBE_ENABLED: bool = False
    STORAGE_PROBE_TIMEOUT_SECONDS: float = 5.0
    STORAGE_PROBE_TTL_SECONDS: float = 300.0


    # Privacy & Retention
    POLICY_VERSION: int = 3
    ANALYTICS_K_MIN: int = 20
    TRYON_ANONYMOUS_EXPIRY_HOURS: int = 24
    # Group 4 §30: duplicate-purchase thresholds, centralized. Strict means
    # near-exact duplicate (type + color required by the scorer, 90/100);
    # loose means similar style/category (65/100: type + one more signal).
    DUPLICATE_ALERT_SIMILARITY_THRESHOLD: float = 0.90
    DUPLICATE_ALERT_LOOSE_THRESHOLD: float = 0.65

    # Wardrobe AI analysis execution mode (G-ASYNC remediation):
    #   auto  - probe the broker with a hard 1s budget; take the async
    #           (Celery) path ONLY if a broker is actually reachable,
    #           otherwise run analysis inline in the request. Serverless-safe
    #           default: the upload response already carries the final item
    #           state, so nothing can sit in 'processing' invisibly.
    #   sync  - always inline (no broker contact at all).
    #   async - always enqueue; the operator MUST run a worker for the queue
    #           (and a stale-processing guard, below, is the safety net).
    WARDROBE_ANALYSIS_MODE: str = "auto"
    # Self-healing window: an item stuck in 'processing' longer than this
    # (minutes) is marked 'failed' (retryable) on the next wardrobe read.
    # A lost worker, a killed serverless function, or a crash mid-analysis
    # must never leave a customer's photo in a permanent in-between state.
    WARDROBE_PROCESSING_STALE_MINUTES: int = 10

    model_config = SettingsConfigDict(
        env_file=_env_files(),
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

    # ------------------------------------------------------------------
    # Object-storage resolution (single source of truth for every caller).
    #
    # Rationale (audit closure 2026-09-21): the storage backend, the health
    # probe and the delivery staging all need the SAME bucket/credential
    # resolution. Three call sites reading ``getattr(settings, "X")`` in
    # slightly different orders is how the documented .env.example aliases
    # ended up ignored. These properties are the only resolution point.
    # ------------------------------------------------------------------
    @property
    def s3_bucket(self) -> Optional[str]:
        for value in (self.AWS_S3_BUCKET, self.S3_BUCKET, self.S3_BUCKET_PUBLIC):
            if value and value.strip():
                return value.strip()
        return None

    @property
    def s3_endpoint_url(self) -> Optional[str]:
        # Explicit settings win; AWS_ENDPOINT_URL_S3 is the AWS-SDK-standard
        # name (Neon Object Storage's docs and the AWS SDK env chain use it),
        # accepted as a fallback so operators using that name are not
        # silently dropped.
        for value in (self.S3_ENDPOINT_URL, self.S3_ENDPOINT, self.AWS_ENDPOINT_URL_S3):
            if value and value.strip():
                return value.strip().rstrip("/")
        return None

    @property
    def s3_access_key(self) -> Optional[str]:
        for value in (self.AWS_ACCESS_KEY_ID, self.S3_ACCESS_KEY):
            if value and value.strip():
                return value.strip()
        return None

    @property
    def s3_secret_key(self) -> Optional[str]:
        for value in (self.AWS_SECRET_ACCESS_KEY, self.S3_SECRET_KEY):
            if value and value.strip():
                return value.strip()
        return None

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

        # CYCLE 4 (email honesty gate): EMAIL_PROVIDER=smtp without a real
        # transport config would let the API answer "queued" while nothing is
        # sent — the exact fake-success class this codebase forbids.
        if (self.EMAIL_PROVIDER or "").lower() == "smtp":
            if not self.SMTP_HOST:
                problems.append("EMAIL_PROVIDER=smtp requires SMTP_HOST (refusing to boot: sends would be fake)")
            if not self.EMAIL_FROM_ADDRESS:
                problems.append("EMAIL_PROVIDER=smtp requires EMAIL_FROM_ADDRESS")
        if (self.EMAIL_PROVIDER or "").lower() == "brevo_api":
            if not self.BREVO_API_KEY:
                problems.append("EMAIL_PROVIDER=brevo_api requires BREVO_API_KEY (refusing to boot: sends would be fake)")
            if not self.EMAIL_FROM_ADDRESS:
                problems.append("EMAIL_PROVIDER=brevo_api requires EMAIL_FROM_ADDRESS")
            if not self.FRONTEND_BASE_URL.startswith("https://"):
                problems.append("FRONTEND_BASE_URL must be https:// in production (email links)")

        for name in ("SECRET_KEY", "JWT_REFRESH_SECRET", "ENCRYPTION_KEY_FOR_BODY_DATA"):
            value = getattr(self, name) or ""
            if value in PUBLICLY_KNOWN_SECRET_VALUES:
                problems.append(f"{name} is a publicly known value (repository default or published in docs)")
            elif len(value) < MIN_SECRET_LENGTH:
                problems.append(f"{name} is shorter than {MIN_SECRET_LENGTH} characters")

        # Audit-chain key separation (P0 closure): production must sign the
        # audit chain with a DEDICATED key. The dev fallback (derived from
        # SECRET_KEY) would make a JWT-key leak sufficient to re-forge the
        # chain, which silently voids the tamper-evidence claim — so refuse
        # to boot rather than claim a guarantee that does not hold.
        audit_key = self.AUDIT_HMAC_KEY or ""
        if not audit_key:
            problems.append(
                "AUDIT_HMAC_KEY is required in production (tamper-evident audit "
                "chain needs a key separate from SECRET_KEY)"
            )
        elif audit_key in PUBLICLY_KNOWN_SECRET_VALUES:
            problems.append("AUDIT_HMAC_KEY is a publicly known value")
        elif len(audit_key) < MIN_SECRET_LENGTH:
            problems.append(f"AUDIT_HMAC_KEY is shorter than {MIN_SECRET_LENGTH} characters")
        elif audit_key == (self.SECRET_KEY or ""):
            problems.append("AUDIT_HMAC_KEY must differ from SECRET_KEY (key separation)")

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
