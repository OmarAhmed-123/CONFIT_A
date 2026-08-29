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
# The repo bundles a seeded dev database (backend/data/confit.db) and the app
# also self-seeds when the DB is empty — no manual seed step is needed.
# To reset the demo data intentionally: PYTHONPATH=. python3 backend/app/seed_data.py --force
# (seed_data.py refuses to wipe a populated database without --force.)
PYTHONPATH=. uvicorn backend.app.main:app --reload --port 8000

# 2. Frontend (second terminal)
cd frontend
npm ci
npm run dev                                            # http://localhost:5173
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
| `TABBY_API_KEY` / `STRIPE_WEBHOOK_SECRET` / … | for live payments | PSP credentials; without them payments run in explicit demo mode (`PAYMENTS_LIVE=0`). |

### Database migrations

The project uses SQLAlchemy `create_all` plus additive migration scripts
(idempotent, data-preserving):

```bash
PYTHONPATH=. python3 backend/scripts/migrate_add_missing_columns.py
PYTHONPATH=. python3 backend/scripts/migrate_enum_columns_to_varchar.py
PYTHONPATH=. python3 backend/scripts/backfill_garment_asset_slots.py
```

## Running the tests

```bash
PYTHONPATH=. python3 -m pytest backend/tests -q        # 73 tests
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
modal deploy services/vton-worker/modal_app.py
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
