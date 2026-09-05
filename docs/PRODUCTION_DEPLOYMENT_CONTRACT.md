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
docs) is refused** — the blocklist is `PUBLICLY_KNOWN_SECRET_VALUES` in `core/config.py`.

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
| `VTON_WORKER_PROCESS_URL` | optional | same | overrides the derived process URL when Modal exposes the process endpoint at its **own hostname root** (a label that does not end in `-process` and that the generic derivation would otherwise wrongly append `/process` to) |
| `VTON_WORKER_READINESS_URL` | yes for try-on | same | Modal's readiness label is hash-truncated (`…-r-xxxxxx.modal.run`) and **cannot be derived**; without it the health URL is used for readiness |
| `VTON_WORKER_HEALTH_URL` | optional | same | derived from `-process` → `-health` when unset |
| `VTON_WORKER_EXPECTED_GIT_SHA` | recommended | `/health/vton-contract` (T4 gate) | the commit `modal deploy` ran from; falls back to Vercel's `VERCEL_GIT_COMMIT_SHA`, i.e. **backend and worker are expected to be deployed from the same commit**. Verdicts: `match` (pass) / `mismatch` / `worker_unknown` / `dirty_deploy` / `no_expected_sha` |
| `VTON_WORKER_TIMEOUT_SECONDS` | default 90 | `tryon_service.py` | **Vercel function `maxDuration` is 60 s** (`vercel.json`). Measured on the deployed T4 worker (2026-09-03): ≈12–13 s per garment layer + cold start up to ≈85 s. Single/two-garment requests fit; 3+ garments or a cold worker exceed the Vercel budget and surface as `504 VTON_TIMEOUT` / function timeout. Set this ≤ 55 on Vercel and keep the worker warm (Modal `scaledown_window`) or move multi-garment rendering to the async job route — see §6 |
| `VTON_WORKER_ADMIN_TOKEN` (or `CONFIT_WORKER_ADMIN_TOKEN`) | yes for try-on | `tryon_service.py` sends `X-VTON-Admin` | **must equal** the Modal secret `confit-worker-admin-token` (`CONFIT_WORKER_ADMIN_TOKEN` inside the worker). Mismatch → `VTON_AUTH_FAILURE` (503) for every user; verify with the admin endpoint below |
| `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY` | at least one | `providers/orchestrator.py`, `tryon_provider.py` | `AI_PROVIDERS` orders the fail-over |
| `PAYMENTS_LIVE` | `true` for real charges | `commerce_service.py`, payment orchestrator | `false` = `payment_mode="demo"` on every order |
| `EMAIL_PROVIDER` (+ provider keys) | recommended | `auth_service.py` (password reset → 501 without it), `commerce_service.py` notifications | |
| `REDIS_URL` | not on Vercel | `workers/celery_app.py` | default `redis://localhost:6379/0` is only reachable on a developer machine; API code never blocks on it (bounded enqueue with inline fallback) |
| `CONFIT_SCHEMA_GATE` | never in prod | `core/schema_gate.py` | `warn` downgrades the startup refusal to logging — emergency use only, logged loudly |

Settings that exist but are **not consumed by any code path** (documented so
nobody believes setting them changes behaviour): `PROJECT_NAME`, `PORT`,
`EMAIL_FROM_ADDRESS`, `SMTP_*`, `KLING_API_KEY`, `AI_STYLIST_PROVIDER`,
`VTON_PROVIDER`, `FULFILL_PACE`, `PAYMENT_DEFAULT_PROVIDER`,
`STRIPE_WEBHOOK_SECRET`, `PAYMOB_API_KEY`, `POLICY_VERSION`,
`ANALYTICS_K_MIN`, `TRYON_ANONYMOUS_EXPIRY_HOURS`.

> The NVIDIA embedding/rerank/vision/translate/image keys
> (`NVIDIA_EMBED_KEY`, `NVIDIA_EMBED_KEY_2`, `NVIDIA_RERANK_KEY`,
> `NVIDIA_VISION_KEY`, `NVIDIA_TRANSLATE_KEY`, `NVIDIA_IMAGE_KEY`) were removed
> from `config.py`/`.env.example` as dead config — no code path consumed them
> (search is deterministic, visual search is vision+scoring). Only
> `NVIDIA_API_KEY` and `NVIDIA_CHAT_KEY_2` are wired to the NVIDIA chat provider.

## 4. Deployment sequence (every release)

1. Merge to `main` only with CI green: `backend`, `postgres-migrations`,
   `production-parity`, `frontend`, `gitleaks`.
2. **Migrate Neon before or together with the deploy** (`alembic upgrade head`)
   — Vercel does not run Alembic; run it from a machine/CI job with
   `backend/requirements.txt` installed. Current head:
   **`0016_vton_temporary_delivery`** (additive + idempotent: three nullable
   columns and one non-unique index on `tryon_jobs` — no row rewrites):
   ```bash
   ALEMBIC_DATABASE_URL="$NEON_DSN" python3 -m alembic -c backend/alembic.ini upgrade head
   PYTHONPATH=. python3 -m backend.app.core.schema_gate "$NEON_DSN" --env production   # exit 0 == ok
   ```
   If the code is deployed ahead of the migration, production **refuses to
   serve data routes** (schema gate) instead of returning 500s or fake data.
3. Vercel builds `main` automatically; verify `GET /api/v1/health` →
   `checks.schema.verdict == "ok"`, `checks.storage`, and the git SHA.
4. Deploy the COMMERCIAL GPU worker **from the same commit**:
   `cd services/vton-worker && modal deploy modal_app_segfee.py`; verify
   `GET <health URL>` → `git_sha` equals the deployed backend commit,
   `model_loaded=true`, `engine == "fashn_vton_segfee"`, `commercial=true`,
   `parser_present=false` (the non-commercial human-parser is provably absent),
   `cuda_available=true`. The canonical production engine is the
   segmentation-free FASHN fork; the legacy CatVTON `modal_app.py` is a
   non-production artifact and must NOT be deployed.
5. As an admin: `GET /api/v1/health/vton-contract` → `contract == "consistent"`
   (a `token_mismatch` verdict means the Vercel token ≠ Modal secret; the
   endpoint never reveals either value).
6. Black-box the previously failing routes: `brand/analytics`,
   `brand/placements`, `admin/analytics`, `orders/{n}`,
   `tryon/validate-image`, `tryon/visual-search`.

## 5. Known production limitations (measured, not assumed)

| Limitation | Evidence | Impact | Mitigation |
|---|---|---|---|
| Multi-garment latency vs Vercel `maxDuration=60` | deployed T4 worker, git_sha `c928544…`: 1 garment 14.9 s, 2 → 25.3 s, 3 → 38.6 s, 5 → 65.1 s (plus ≈85 s cold start) | 3+ garments or a cold worker cannot complete inside one Vercel invocation | keep worker warm; `VTON_WORKER_TIMEOUT_SECONDS ≤ 55`; async job route for outfits |
| Modal container preemption | 5-garment large-input run: container preempted at layer 4 → HTTP 500 `Server has lost track of input` from the Modal edge (not from worker code) | request fails; API maps it to `502 VTON_WORKER_UNAVAILABLE` — never a fake success | client retry; Modal restarts the container automatically |
| Segmentation fallback on non-photographic input | flat synthetic figure → `engine=humanparsing-otsu-skin-v2-fallback`, `fallback_used=true` (plausibility gate rejected the deep mask); real photo → `rembg-u2net_human_seg`, `fallback_used=false` | masks on illustrations are heuristic; the response says so | none needed — honest reporting is the contract |
| Live payments | `PAYMENTS_LIVE=true` fails closed (`live_psp_adapter_not_implemented`) — no PSP SDK is integrated | no real card/wallet/BNPL charge can be taken; COD unaffected | integrate a PSP adapter before enabling live mode |
| Object storage | Vercel FS is ephemeral; until `STORAGE_PROVIDER=s3\|r2` is set uploads return `501 FEATURE_NOT_CONFIGURED` | wardrobe/moodboard uploads disabled in prod | configure S3/R2 (boto3 is in the Vercel manifest). **Generated try-on images do NOT need object storage** — they are delivered inline + one-shot download and never persisted (§6) |

## 6. Things that are deliberately absent

* **No permanent storage of generated try-on images.** By product requirement
  (2026-09-05) a rendered image is **never** written to PostgreSQL, R2/S3,
  local disk, the repository, or any durable object/frontend asset. Delivery is
  (a) the inline `result_image_data_url` in the authenticated completion
  response, and (b) a best-effort one-shot, owner-only, TTL-bounded download
  (`GET /tryon/jobs/{job_id}/result?delivery_token=*** backed by a process-local
  TTL cache. The VTON flow never calls `require_production_storage` — a
  deployment with **no** object storage still completes try-on jobs (covered by
  `test_vton_temporary_delivery.py::TestJobDeliveryE2E`). Only three nullable
  metadata columns are persisted (migration 0016): `delivery_token_hash`
  (SHA-256 of the one-time token — the token itself is never stored),
  `delivery_expires_at`, `delivery_content_type`. `tryon_jobs.output_image_url`
  stays `NULL` for VTON jobs.
* No Celery task renders try-ons. The **only** renderer is the CatVTON
  pipeline in `services/vton-worker`; unavailability is an honest
  `503 VTON_ENGINE_UNAVAILABLE`, never a fake "completed".
* No `if table_missing: pretend_success()`; schema drift is a refusal.
* No secrets in `docker-compose.yml` or docs — only `${VAR:?}` placeholders.
* No order-level revenue attribution fallback: the ledger joins through
  `brand_analytics_events.order_item_id` (migration 0014).
