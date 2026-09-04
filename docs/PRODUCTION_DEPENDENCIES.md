# CONFIT — Production Dependencies & Availability Matrix

What each production feature needs, which manifest installs it, and what the
user sees when the dependency is missing. "Degrades to" is the **implemented**
behaviour, not an aspiration; every row that says 501/503 is exercised by a
test.

## 1. Manifests (they are NOT interchangeable)

| Manifest | Installed by | Contents that matter |
|---|---|---|
| `requirements.txt` == `api/requirements.txt` (byte-identical, tested) | **Vercel** | fastapi, sqlalchemy, **pg8000** (no psycopg2), mangum, httpx, **Pillow**, **boto3** (S3/R2 uploads), redis client, pydantic-settings — **no** alembic (migrations run from CI/operator), celery worker, psycopg2, rembg, torch |
| `backend/requirements.txt` | Docker / CI `backend` job | superset incl. psycopg2-binary, celery, redis |
| `services/vton-worker` image (`modal_app.py`) | Modal build | torch/diffusers/CatVTON weights, rembg + baked u2net_human_seg/isnet weights |

`backend/scripts/check_runtime_imports.py` and
`backend/tests/test_deployment_dependency_manifest.py` model the Vercel
install; CI job `production-parity` imports `api/index.py` with **only**
`requirements.txt` installed.

## 2. External services

| Service | Used for | Configured via | If unavailable |
|---|---|---|---|
| **Neon** PostgreSQL | everything persistent | `DATABASE_URL` (`sslmode=require` → pg8000) | API refuses to start in production (contract) / schema gate blocks data routes when behind head |
| **Vercel** | frontend + API function (60 s max duration) | project settings | — |
| **Modal** `confit-vton-worker` | CatVTON inference, segmentation (rembg), health/readiness | `VTON_WORKER_URL`, `VTON_WORKER_READINESS_URL`, `VTON_WORKER_ADMIN_TOKEN` | `503 VTON_ENGINE_UNAVAILABLE` / `VTON_AUTH_FAILURE`; no fallback renderer exists |
| **Gemini** (vision + text) | stylist chat, wardrobe auto-tag, visual-search analysis, try-on image validation | `GEMINI_API_KEY` | orchestrator fails over to the next provider in `AI_PROVIDERS`; with none configured: visual search returns `analysis_available=false` (200), wardrobe items marked `failed` (retryable), stylist falls back to the deterministic composer |
| **NVIDIA** NIM | first LLM in the fail-over chain | `NVIDIA_API_KEY` | next provider |
| **Groq / OpenAI** | further fail-over | `GROQ_API_KEY`, `OPENAI_API_KEY` | next provider / deterministic fallback |
| **Redis + Celery** | wardrobe auto-tag queue, catalog import queue, GDPR purge beat | `REDIS_URL` | **not deployed on Vercel**: wardrobe processes inline; catalog import runs synchronously; purge task must be run by an operator (`purge_expired_sessions_task`) or a scheduled job |
| **Object storage** (S3/R2) | wardrobe images, moodboard uploads, return authorisation artefacts | `STORAGE_PROVIDER=s3|r2` + `AWS_S3_BUCKET` + `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (+ `S3_ENDPOINT_URL`/`S3_PUBLIC_URL_BASE` for R2); boto3 ships in every manifest | `501 FEATURE_NOT_CONFIGURED` on upload endpoints; `/health.checks.storage.production_grade=false` |
| **Email provider** | password reset, order/return notifications | `EMAIL_PROVIDER` + keys | forgot-password → 501; notifications logged only |
| **Payment providers** (Stripe/Paymob/Tabby/Tamara) | live capture/refund | `PAYMENTS_LIVE=true` + provider keys | `payment_mode="demo"` recorded on the order; webhooks still verified |

## 3. Feature availability matrix (production, after this remediation)

| Feature | Needs | Without it |
|---|---|---|
| Auth, catalogue, cart, checkout, orders, tracking, returns | Neon + secrets | n/a (hard requirement) |
| Brand / admin analytics, attribution | Neon at migration head (0014) | schema gate refusal (no empty arrays / fake zeros) |
| Virtual try-on | Modal worker + matching admin token | 503, honest error code |
| Visual search | Gemini/NVIDIA vision key | 200 with `analysis_available=false` and heuristic matches |
| Wardrobe upload / moodboard upload | object storage | 501 |
| Password reset e-mail | email provider | 501 |
| Live payments | `PAYMENTS_LIVE` + provider keys | demo mode |
| Background auto-tagging | Redis/Celery | inline processing |

## 4. Operational checks

* `GET /api/v1/health` — `checks.schema`, `checks.storage`, git SHA.
* `GET /api/v1/health/vton-contract` (admin) — worker health metadata
  (`git_sha`, `model`, `segmentation_model`, `device`) and the token contract
  verdict without exposing the token.
* `python3 -m backend.app.core.schema_gate "$DSN" --env production` — exit 0/1/2.
* `backend/scripts/check_migration_chain_postgres.py "$DSN"` — empty→head, head→base→head on a scratch PostgreSQL.
