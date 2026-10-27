# CONFIT (كونفيت)
### AI-Powered Luxury Fashion Technology Platform

[![Backend CI](https://github.com/OmarAhmed-123/CONFIT_A/actions/workflows/ci.yml/badge.svg)](https://github.com/OmarAhmed-123/CONFIT_A/actions/workflows/ci.yml)
[![Secret Scan](https://github.com/OmarAhmed-123/CONFIT_A/actions/workflows/gitleaks.yml/badge.svg)](https://github.com/OmarAhmed-123/CONFIT_A/actions/workflows/gitleaks.yml)

> "Where Style Meets Your Character in Every Moment"

CONFIT is a luxury fashion platform: an AI stylist grounded strictly in the real
catalog, a multi-garment virtual try-on pipeline, a smart wardrobe, and a B2B
brand portal — with a browse-freely / authenticate-at-checkout access model.

---

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  frontend/  React 18 + TS   │  HTTPS │  backend/   FastAPI (MVC)     │
│  Vite 8 · Tailwind · MVVM   │ ─────► │  controllers → services →     │
│  (Vercel static hosting)    │  /api  │  repositories → SQLAlchemy    │
└─────────────────────────────┘        └──────────────┬───────────────┘
                                                      │
                        ┌─────────────────────────────┼──────────────────────────┐
                        ▼                             ▼                          ▼
              PostgreSQL (Neon, prod)       AI providers (Groq, Gemini,   services/vton-worker/
              SQLite (local dev, zero       OpenAI — live failover with   Modal GPU (CatVTON)
              config) or any DATABASE_URL   quarantine memory + grounded  Optional until deployed;
                                            deterministic fallback)       try-on fails honestly
                                                                          (503) without it.
```

- **Backend** (`backend/app`): FastAPI, SQLAlchemy 2, PyJWT, slowapi rate
  limiting, httpOnly cookie sessions + CSRF double-submit, structlog logging.
- **Frontend** (`frontend/src`): React 18 + TypeScript, MVVM
  (`models/` · `viewmodels/` · `views/`), zustand stores, i18n (EN/AR, RTL).
- **GPU worker** (`services/vton-worker`): Modal serverless service that bakes
  CatVTON weights into the image at build time. See "Virtual try-on" below.
- **CI/CD**: `.github/workflows/ci.yml` (backend tests + pip-audit + import
  guard; frontend type-check + build + npm audit), `gitleaks.yml` (secret
  scanning), `uptime-monitor.yml` (production health ping every 15 min).
  Branch protection on `main` requires the `backend` and `frontend` checks.

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | ≥ 3.11 |
| Node.js + npm | ≥ 20 |
| Neon (managed Postgres) | production only — local dev uses SQLite, zero setup |
| Modal account | only if you deploy the GPU try-on worker |
| AI provider keys (Groq / Gemini / OpenAI) | optional locally — without them the stylist uses its deterministic grounded fallback |

## Local setup (from a clean clone)

```bash
git clone https://github.com/OmarAhmed-123/CONFIT_A.git
cd CONFIT_A

# 1. Backend
pip install -r backend/requirements.txt
# The dev DB (backend/data/confit.db) is intentionally NOT tracked; the app
# self-seeds when the database is empty — no manual seed step is needed.
# To reset the demo data intentionally:
#     PYTHONPATH=. python3 backend/app/seed_data.py --force
# (seed_data.py refuses to wipe a populated database without --force and
# refuses outright when ENVIRONMENT=production.)
PYTHONPATH=. uvicorn backend.app.main:app --reload --port 8000

# 2. Frontend (second terminal)
cd frontend
npm ci
npm run dev                                            # http://localhost:43123
```

- API docs: `http://localhost:8000/docs` · Health: `http://localhost:8000/api/v1/health`
- On startup the API creates tables automatically and seeds the catalogue
  **only if the database is empty** — it never touches existing rows.
- Demo accounts after seeding: `shopper@confit.io`, `admin@confit.io`,
  `brand@confit.io` — password `Password123!`.

### Environment variables

Copy `backend/.env.example` to `backend/.env` and fill what you need. All
secrets are read from the environment only — **never commit real keys**
(CI scans for them). The full list with descriptions lives in
`backend/.env.example`; the important ones:

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | prod | Postgres DSN (Neon). Absent → local SQLite file. |
| `SECRET_KEY`, `JWT_REFRESH_SECRET`, `ENCRYPTION_KEY_FOR_BODY_DATA` | prod | Refuse-to-boot in production while left at defaults. |
| `GROK_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` | optional | Live AI stylist providers (failover order in `AI_PROVIDERS`). |
| `VTON_WORKER_URL` | for real try-on | Deployed Modal worker URL. |
| `PAYMENTS_LIVE` | no (default false) | When false, card/BNPL use the labelled demo adapter. When true, missing PSP secrets fail the charge — they never fabricate success. |
| `TABBY_API_KEY` / `TAMARA_API_KEY` / `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | live payments only | Server-side PSP credentials. Webhooks are rejected if the provider secret is unset. |

### Database migrations

Managed by **Alembic** (`backend/alembic/`). Migrations are idempotent
(inspector-guarded) and reversible — every migration provides a `downgrade()`.

```bash
# Local dev (SQLite) — usually a no-op since the app self-creates on startup
PYTHONPATH=. python3 -m alembic -c backend/alembic.ini upgrade head

# Production (Postgres / Neon)
DATABASE_URL="postgresql+psycopg2://..." \
  PYTHONPATH=. python3 -m alembic -c backend/alembic.ini upgrade head

# Historical create_all databases (e.g. an environment predating Alembic) —
# stamp the baseline first, then upgrade:
DATABASE_URL="postgresql+psycopg2://..." \
  PYTHONPATH=. python3 -m alembic -c backend/alembic.ini stamp 0001_baseline
DATABASE_URL="postgresql+psycopg2://..." \
  PYTHONPATH=. python3 -m alembic -c backend/alembic.ini upgrade head
```

Every migration MUST use portable defaults (`sa.true()` / `sa.false()` for
boolean columns, not `sa.text("1")` — the latter crashes on Postgres with
`DatatypeMismatch`).

### Database integrity validator

`backend/scripts/validate_database.py` is a **read-only** tool that walks the
integrity invariants the application depends on (FK orphans, domain
validity, uniqueness, numeric bounds — including the Group 4
`(user_id, image_hash)` invariant). Safe to run against any environment.

```bash
# Against the local dev DB
PYTHONPATH=. python3 backend/scripts/validate_database.py

# Against a specific database (production or otherwise)
DATABASE_URL="postgresql+psycopg2://..." \
  PYTHONPATH=. python3 backend/scripts/validate_database.py
```

Exit code: `0` = healthy, `1` = one or more violations, `2` = could not
connect. Coverage is exercised by `backend/tests/test_database_integrity.py`.

## IBM watsonx.ai wardrobe stylist (Granite)

CONFIT's **Smart Wardrobe → AI Stylist** tab implements the flow from IBM's
[Build an AI stylist with Granite](https://www.ibm.com/think/tutorials/build-ai-stylist-with-granite-python-watsonx-ai)
tutorial on top of the existing wardrobe pipeline:

```
photo upload ─► validation (MIME/size/Pillow decode) ─► storage + sha256 dedupe
     ─► vision model (watsonx.ai) ─► strict-JSON parse ─► taxonomy normaliser
     ─► wardrobe_items row (analysis_source = model id that answered)
user picks occasion · time of day · season · location · preferences
     ─► POST /api/v1/wardrobe/outfit-recommendation
     ─► Granite (watsonx.ai) with the versioned CONFIT Stylist system prompt
     ─► JSON validated: every wardrobe_item_id must exist in the caller's closet,
        no duplicates, roles derived from stored categories, images resolved
        from trusted rows ─► one outfit + a reason per garment
"Save this look" ─► POST /api/v1/wardrobe/outfits (ids re-validated against the
        caller's closet, roles from stored categories, provenance kept verbatim)
     ─► My Looks → "Saved wardrobe looks" (GET /wardrobe/outfits; binned garments
        are omitted and counted, never shown stale)
```

Key modules: `backend/app/providers/watsonx/` (`client.py` IAM + chat,
`prompts.py` versioned prompts, `vision.py`), `backend/app/services/
wardrobe_stylist_service.py`, `backend/app/schemas/wardrobe_stylist.py`,
`frontend/src/components/wardrobe/WardrobeStylistPanel.tsx`,
`SavedWardrobeLooks.tsx`, `backend/app/services/wardrobe_outfit_service.py`
(migration `0048_wardrobe_outfits`). Audit & gap analysis:
`docs/IBM_WATSONX_STYLIST_AUDIT.md`; journey: `docs/STYLE_LIST_WORKFLOW.md`;
Granite Vision availability: `docs/GRANITE_VISION_AVAILABILITY_INVESTIGATION.md`;
production verification: `docs/IBM_WATSONX_PRODUCTION_VERIFICATION_REPORT.md`.

### IBM Cloud setup

1. Create an [IBM Cloud account](https://cloud.ibm.com/registration) and open
   [watsonx.ai](https://dataplatform.cloud.ibm.com/registration/stepone?context=wx).
2. Create a **watsonx.ai project**; copy the **Project ID** (Manage → General).
3. Create a **watsonx.ai Runtime** service (Lite plan) in the *same region* and
   associate it with the project (Project → Manage → Services & integrations).
4. Create an **IAM API key** (IBM Cloud → Manage → Access (IAM) → API keys).
5. Put the values in `backend/.env` (never in code, never committed):

| Variable | Required | Notes |
|---|---|---|
| `WATSONX_APIKEY` | yes | IAM API key (server-side only) |
| `WATSONX_PROJECT_ID` | yes | project GUID |
| `WATSONX_URL` | yes | regional runtime, e.g. `https://eu-de.ml.cloud.ibm.com` or `https://us-south.ml.cloud.ibm.com` — must match the project's region |
| `WATSONX_VISION_MODEL_ID` | no | default `meta-llama/llama-4-maverick-17b-128e-instruct-fp8` (see note) |
| `WATSONX_REASONING_MODEL_ID` | no | default `ibm/granite-4-h-small` |
| `WATSONX_VISION_DEPLOYMENT_ID` / `WATSONX_REASONING_DEPLOYMENT_ID` | no | Deploy-on-Demand deployment ids (Granite Vision is DoD-only — `docs/GRANITE_VISION_AVAILABILITY_INVESTIGATION.md`) |
| `WARDROBE_VISION_PROVIDER` | no | `auto` (watsonx first, then Gemini/NVIDIA/Qwen) · `watsonx` · `legacy` |
| `WARDROBE_STYLIST_PROVIDER` | no | `auto` (Granite, labelled rule-based fallback) · `watsonx` (503/501 instead of fallback) · `deterministic` |

> **Model availability (verified live 2026-10-26).** The tutorial's
> `ibm/granite-vision-3-2-2b` has been **removed** from watsonx.ai (the API
> answers `404 model_not_supported`) and `ibm/granite-3-2-8b-instruct` was
> withdrawn on 2026-02-22; IBM's lifecycle table names `granite-4-h-small` as
> the replacement. No `granite-vision-*` model was served multitenant in
> eu-de/us-south at the time of writing, so the vision default is the
> available `image_chat` model. Model ids are configuration: when IBM lists a
> Granite vision model for your region, set `WATSONX_VISION_MODEL_ID` and
> nothing else changes. Whatever model actually answers is recorded per item
> in `analysis_source` and per outfit in `model_id`, and shown in the UI.

### Verify connectivity

```bash
set -a && source backend/.env && set +a
PYTHONPATH=. python3 scripts/watsonx_smoke.py [path/to/garment.jpg]
# PASS 1 IAM token · PASS 2 reasoning model · PASS 3 vision model · PASS 4 stylist round-trip
```

### Honesty & privacy contract

* A recommendation payload always carries `source` (`watsonx` |
  `deterministic_fallback`), `ai_generated`, `model_id` and `prompt_version`.
  The UI renders a "Rule-based match — not AI" badge for fallbacks.
* Only item descriptors (ids, category, colour, pattern, tags, the one-line
  model description) are sent to the reasoning model — never photos, URLs or
  user identifiers. Photos are sent to the vision model once per upload,
  downscaled to ≤1024 px JPEG, and are not retained by IBM per the watsonx.ai
  data policy for inference.
* Missing wardrobe categories are reported in `missing_categories`; nothing is
  invented. Model references that do not match the caller's wardrobe are
  dropped and counted in `rejected_references`.
* Colours the user asked to avoid (`excluded_colors`, or "no black" /
  "بدون أسود" in the free-text *Avoid* field) are enforced by the server, not
  just requested from the model: offending pieces are removed from the answer
  and the limitation says so. One outfit is returned per call; ask for
  "Another outfit" (`previous_item_ids`) for alternatives.
* Credentials never appear in logs (last-4 redaction), responses, or the
  frontend bundle. `GET /wardrobe/stylist/status` reports *whether* watsonx is
  configured and which model ids are in use — never the key or project id.
* Saved looks keep their provenance, but a client cannot forge it: a look
  posted with `source=watsonx` is only accepted when its `model_id` is the
  configured reasoning model (or reasoning deployment) id; anything else is
  rejected with 422. Fallback looks are always stored as `ai_generated=false`,
  `model_id=null`.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `501 FEATURE_NOT_CONFIGURED` with hint naming `WATSONX_*` | `WARDROBE_STYLIST_PROVIDER=watsonx` and credentials missing; set them or use `auto` |
| `502 PROVIDER_ERROR … watsonx_auth_failed` | IAM rejected the key (typo, deleted key) or the project is not in `WATSONX_URL`'s region / not associated with a Runtime |
| `… watsonx_model_not_supported` | model id deprecated/removed in your region; run the smoke script and change the `*_MODEL_ID` |
| `… watsonx_timeout` / `watsonx_rate_limited` | transient; the client already retries 429/5xx/timeouts with backoff — retry from the UI |
| `422 … model attribution does not match the configured watsonx model` on `POST /wardrobe/outfits` | the `model_id` sent back differs from `WATSONX_REASONING_MODEL_ID` / `WATSONX_REASONING_DEPLOYMENT_ID` (e.g. the model was rotated between recommend and save, or the payload was altered) — regenerate the look |
| API never binds its port on a **fresh PostgreSQL** database (non-production) | fixed 2026-10-26 (seed ran while the probe session was still open → lock wait); if you run several uvicorn workers against an *empty* dev database, seed once with one worker first; the database must be `UTF8` (the seed contains Arabic) |
| Rate limits appear per-worker | without an external `REDIS_URL` the limiter uses `memory://` per process; point `REDIS_URL` at a shared store for multi-worker deployments |
| Item stuck `failed` with `watsonx_vision_malformed_output` | model returned prose instead of JSON; press "Retry analysis" (temperature is 0, usually transient) |
| Outfit badge says "Rule-based match" although keys are set | check `fallback_reason` in the response and the backend log line `wardrobe_stylist_model_degraded` |

## Running the tests

```bash
PYTHONPATH=. python3 -m pytest backend/tests -q        # backend suite
cd frontend && npm run build                           # type-check + production build
```

## CI/CD

Every push and PR runs (and `main` cannot be merged unless both pass):

| Check | What it proves |
|---|---|
| `backend` | deps install, runtime-import coverage (no undeclared imports — the class of bug behind the 2026-08-29 outage), `pip-audit`, full test suite |
| `frontend` | `npm ci`, `tsc` type-check + `vite build`, `npm audit` |
| `gitleaks` | no secrets in the pushed commits or history |
| `uptime-monitor` | production `/api/v1/health` every 15 min |

## Deployment

- **Vercel**: the repo deploys as-is (`vercel.json` routes `/api/*` to the
  serverless function in `api/index.py`, SPA fallback to `index.html`).
  Set the Production env vars from the table above in the Vercel dashboard —
  not in the repo.
- **GPU worker (real virtual try-on)**:

```bash
pip install modal && modal token new
modal deploy services/vton-worker/modal_app_v15.py
# then set VTON_WORKER_URL=<the printed URL> in Vercel Production env and redeploy
```

Until the worker is deployed, try-on endpoints fail truthfully with
`503 VTON_ENGINE_UNAVAILABLE` — by design: the platform never substitutes a
static image or the user's own photo for a render.

## Honest feature status

| Feature | Status |
|---|---|
| Catalog, search, BOPIS, auth (signup/login/MFA/GDPR), profile, wardrobe, gap analysis, outfit builder, cart, checkout gate, BNPL quotes, orders/returns, brand & admin portals | ✅ Live and tested |
| AI stylist | ✅ Live (Groq/Gemini verified in production), grounded strictly in real catalog products; deterministic fallback when no keys |
| Wardrobe AI stylist (IBM watsonx.ai) | ✅ Implemented + unit/integration tested with mocked HTTP; **live verified 2026-10-26** against eu-de (`granite-4-h-small` reasoning, `llama-4-maverick` vision — Granite Vision not served in region). Fallback is labelled, never presented as AI |
| Visual search | ✅ Live — real Gemini vision analysis (verified: dress/blazer/sneaker photos detected and matched truthfully) |
| Virtual try-on rendering | ⏳ Awaiting GPU worker deployment (code complete; honest 503 until then) |
| Payments | ⚠️ Demo mode — webhook signatures verified, idempotency real; live charges need PSP credentials + sandbox testing first |

## Security posture (abridged)

JWT in httpOnly Secure SameSite cookies with CSRF double-submit; bcrypt
password hashing; RBAC enforced server-side; per-IP rate limits on auth and
GPU-cost endpoints; Fernet encryption for body measurements; GDPR purge
endpoints; production refuses to boot with default secrets; gitleaks in CI.

## License

CONFIT Enterprise Proprietary. All rights reserved.
