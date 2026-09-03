# CONFIT — Production Deployment Contract

This document is the **executable** environment contract for the real product
stack. `backend/tests/test_production_parity.py` (CI job `production-parity`)
fails when the repository drifts from it, and `backend/app/core/config.py`
refuses to boot in production when the environment violates it.

## 1. What "production" is

| Layer | Service | How it is deployed |
|---|---|---|
| Frontend | Vercel static build of `frontend/` | `vercel.json` → `npm --prefix frontend ci && npm --prefix frontend run build` |
| API | Vercel Python serverless function `api/index.py` → `backend.app.main:app` (Mangum) | every push to `main`; `/api/*` rewritten to the function |
| Database | Neon PostgreSQL (`sslmode=require`, driver **pg8000**) | schema managed **only** by Alembic (`backend/alembic`) |
| VTON | Modal app `confit-vton-worker` (`services/vton-worker/modal_app.py`, CatVTON on T4) | `modal deploy services/vton-worker/modal_app.py` **from a committed tree** |
| AI providers | NVIDIA → Groq → Gemini → OpenAI (fail-over in `providers/orchestrator.py`) | API keys in Vercel env |
| Background jobs | Celery + Redis (`backend/app/workers`) — **not** present on Vercel | optional; every Vercel code path has an inline fallback or returns 501 |

Render, Docker Compose and the local SQLite database are **not** production.

## 2. Environments are explicit

`ENVIRONMENT` ∈ `development | test | staging | production`. Any other value is
a boot error everywhere. Business logic never branches on it; only the
infrastructure adapters below do.

| Concern | development / test | production |
|---|---|---|
| `DATABASE_URL` | sqlite default allowed | **must be PostgreSQL** |
| Secrets | repository defaults allowed | **must be ≥32 chars and not publicly known** (see §3) |
| Schema gate (`core/schema_gate.py`) | logs drift | **refuses startup** on drift; `/health` reports verdict; middleware blocks data routes |
| `STORAGE_PROVIDER=local` | fine | uploads answer **501 FEATURE_NOT_CONFIGURED**; `/health.checks.storage.production_grade=false` |
| `/api/v1/diagnostic` | available | 404 |
| Seed data | `create_all` + seed on startup | never |

## 3. Required environment variables (Vercel → Project → Environment Variables)

Generate secrets with `python -c "import secrets;print(secrets.token_urlsafe(48))"`.
**Any value that has ever appeared in this repository (defaults, docker-compose,
docs) is refused** — the blocklist is `Settings._INSECURE_DEFAULTS`.

| Variable | Required in prod | Consumer | Notes |
|---|---|---|---|
| `ENVIRONMENT` | yes = `production` | everywhere | see §2 |
| `DATABASE_URL` | yes | `core/database.py`, `alembic/env.py`, `core/schema_gate.py` | Neon DSN **with `sslmode=require`** (selects pg8000; the psycopg2 dialect is not installed on Vercel) |
| `SECRET_KEY` | yes | `core/security.py` — signs **access** tokens | ≥32 chars, unique |
| `JWT_REFRESH_SECRET` | yes | `core/security.py` — signs **refresh** tokens | ≥32 chars, **different** from `SECRET_KEY` |
| `ENCRYPTION_KEY_FOR_BODY_DATA` | yes | `core/security.py` Fernet key (sha256) for `user_style_profiles.encrypted_body_data` | ≥32 chars. Rotating it makes existing ciphertext unreadable — re-encrypt first |
| `CORS_ORIGINS` | yes | `main.py` | JSON list of the real origins; default is localhost dev ports |
| `STORAGE_PROVIDER` | recommended `s3` or `r2` | `services/storage_service.py` | with `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, optional `S3_ENDPOINT_URL`. `boto3` must be in the manifest that installs it. Until configured: wardrobe/moodboard uploads → 501 |
| `VTON_WORKER_URL` | yes for try-on | `services/tryon_service.py`, `/health/vton-contract` | the Modal **`-process`** URL |
| `VTON_WORKER_READINESS_URL` | yes for try-on | same | Modal's readiness label is hash-truncated (`…-r-xxxxxx.modal.run`) and **cannot be derived**; without it the health URL is used for readiness |
| `VTON_WORKER_HEALTH_URL` | optional | same | derived from `-process` → `-health` when unset |
| `VTON_WORKER_ADMIN_TOKEN` (or `CONFIT_WORKER_ADMIN_TOKEN`) | yes for try-on | `tryon_service.py` sends `X-VTON-Admin` | **must equal** the Modal secret `confit-worker-admin-token` (`CONFIT_WORKER_ADMIN_TOKEN` inside the worker). Mismatch → `VTON_AUTH_FAILURE` (503) for every user; verify with the admin endpoint below |
| `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY` | at least one | `providers/orchestrator.py`, `tryon_provider.py` | `AI_PROVIDERS` orders the fail-over |
| `PAYMENTS_LIVE` | `true` for real charges | `commerce_service.py`, payment orchestrator | `false` = `payment_mode="demo"` on every order |
| `EMAIL_PROVIDER` (+ provider keys) | recommended | `auth_service.py` (password reset → 501 without it), `commerce_service.py` notifications | |
| `REDIS_URL` | not on Vercel | `workers/celery_app.py` | default `redis://localhost:6379/0` is only reachable on a developer machine; API code never blocks on it (bounded enqueue with inline fallback) |
| `CONFIT_SCHEMA_GATE` | never in prod | `core/schema_gate.py` | `warn` downgrades the startup refusal to logging — emergency use only, logged loudly |

Settings that exist but are **not consumed by any code path** (documented so
nobody believes setting them changes behaviour): `PROJECT_NAME`, `PORT`,
`EMAIL_FROM_ADDRESS`, `SMTP_*`, `KLING_API_KEY`, `NVIDIA_VISION_KEY`,
`NVIDIA_EMBED_KEY`, `NVIDIA_EMBED_KEY_2`, `NVIDIA_RERANK_KEY`,
`NVIDIA_TRANSLATE_KEY`, `NVIDIA_IMAGE_KEY`, `AI_STYLIST_PROVIDER`,
`VTON_PROVIDER`, `FULFILL_PACE`, `PAYMENT_DEFAULT_PROVIDER`,
`STRIPE_WEBHOOK_SECRET`, `PAYMOB_API_KEY`, `POLICY_VERSION`,
`ANALYTICS_K_MIN`, `TRYON_ANONYMOUS_EXPIRY_HOURS`.

## 4. Deployment sequence (every release)

1. Merge to `main` only with CI green: `backend`, `postgres-migrations`,
   `production-parity`, `frontend`, `gitleaks`.
2. **Migrate Neon before or together with the deploy** (`alembic upgrade head`)
   — Vercel does not run Alembic; run it from a machine/CI job with
   `backend/requirements.txt` installed:
   ```bash
   ALEMBIC_DATABASE_URL="$NEON_DSN" python3 -m alembic -c backend/alembic.ini upgrade head
   PYTHONPATH=. python3 -m backend.app.core.schema_gate "$NEON_DSN" --env production   # exit 0 == ok
   ```
   If the code is deployed ahead of the migration, production **refuses to
   serve data routes** (schema gate) instead of returning 500s or fake data.
3. Vercel builds `main` automatically; verify `GET /api/v1/health` →
   `checks.schema.verdict == "ok"`, `checks.storage`, and the git SHA.
4. Deploy the GPU worker **from the same commit**:
   `cd services/vton-worker && modal deploy modal_app.py`; verify
   `GET <health URL>` → `git_sha` equals the deployed backend commit,
   `model_loaded=true`, `segmentation_model` set, `cuda_available=true`.
5. As an admin: `GET /api/v1/health/vton-contract` → `contract == "consistent"`
   (a `token_mismatch` verdict means the Vercel token ≠ Modal secret; the
   endpoint never reveals either value).
6. Black-box the previously failing routes: `brand/analytics`,
   `brand/placements`, `admin/analytics`, `orders/{n}`,
   `tryon/validate-image`, `tryon/visual-search`.

## 5. Things that are deliberately absent

* No Celery task renders try-ons. The **only** renderer is the CatVTON
  pipeline in `services/vton-worker`; unavailability is an honest
  `503 VTON_ENGINE_UNAVAILABLE`, never a fake "completed".
* No `if table_missing: pretend_success()`; schema drift is a refusal.
* No secrets in `docker-compose.yml` or docs — only `${VAR:?}` placeholders.
* No order-level revenue attribution fallback: the ledger joins through
  `brand_analytics_events.order_item_id` (migration 0014).
