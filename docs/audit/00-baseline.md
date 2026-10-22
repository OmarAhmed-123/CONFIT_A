# CONFIT_A — Phase 0 Baseline

- **Date:** 2026-10-22
- **Repo:** `OmarAhmed-123/CONFIT_A` @ `main` `cfc6d80` (public)
- **Production:** `https://confit-a.vercel.app`
- **Companion docs:** [`coverage-matrix.md`](coverage-matrix.md) (progress tracker),
  [`findings.md`](findings.md) (defects), [`../REPO_AUDIT_2026-10-22.md`](../REPO_AUDIT_2026-10-22.md) (first audit).
- **Status:** no application code changed on `main`. One fix (F-002) is on branch
  `fix/health-db-unreachable-500` / PR #376. Evidence-only; PENDING items are labelled.

---

## 1. Global blocker

**Production is down (F-001).** The Neon database is over quota, so every data
endpoint returns `503 DATABASE_UNREACHABLE` and the `release gate` CI check fails
closed on all PRs. Restoring it is an owner action (approval-gated). Until then, no
row in the coverage matrix can reach **Verified OK** via production; local review
(code + local dev DB) proceeds normally.

## 2. Environment

| Tool | This machine | CI | Note |
|---|---|---|---|
| OS | Windows 10 | ubuntu-latest | path-length + cp1252 encoding pitfalls (F-003) |
| Python | 3.13 (venv); 3.14 also present | 3.12 | backend installs OK on 3.13 |
| Node / npm | 24.18 / 11.16 | 22 | build + vitest run |
| git | 2.54 | — | `core.longpaths=true` required for clone |
| gh | 2.103 (installed this session) | — | authenticated as OmarAhmed-123 |
| Docker | not installed | — | docker-compose path unavailable locally |

Clone obstacle recorded: the first clone failed under a deep scratch path
(Windows MAX_PATH); the repo lives at `E:\CONFIT` with long paths enabled.

## 3. Repository state

- `main` default + branch-protected (required checks `backend`, `frontend`).
- ~180 remote branches (heavy sprawl; cleanup candidate), tags `vton-audit-cut1/2`.
- Open PRs: **2** pre-existing (#372, #358) + **#376** (this session's F-002 fix);
  open issues: **0**.
- Migrations: linear `0001 … 0046_user_wishlist_items`.
- Recent CI: `ci`/`gitleaks`/`release gate` green on `main` at 00:39 UTC;
  `uptime-monitor` failing since the outage (F-001).

## 4. How to run locally (verified, with obstacles)

```
# backend (from repo root, venv on Python 3.13)
python -m venv .venv ; .venv\Scripts\python -m pip install -r backend/requirements.txt
$env:PYTHONPATH='.'; $env:CONFIT_IGNORE_DOTENV='1'; $env:PYTHONUTF8='1'   # UTF-8: see F-003
.venv\Scripts\python -m pytest backend/tests -q
.venv\Scripts\python backend/scripts/validate_database.py --url sqlite:///./backend/data/confit.db

# frontend
cd frontend ; npm ci ; npm run build ; npm run verify
```

Obstacles found (→ README/parity fixes to propose): backend install needs Python
≤3.13 (CI uses 3.12); `PYTHONUTF8=1` is required on Windows or collection aborts
(F-003); `validate_database.py` needs an explicit `--url`/`DATABASE_URL` (no settings
default).

## 5. Baseline results (as observed)

| Check | Result | Status |
|---|---|---|
| DB integrity validator (local SQLite dev DB) | all FK/domain/numeric/uniqueness checks OK | Verified OK |
| Backend `pytest` (full, Windows, `PYTHONUTF8=1`) | 4529 passed / 8 failed / 25 skipped (55 min). Isolated clean re-run on `main` → only **2 genuine failures**, both Windows-env parity (F-010 POSIX-PATH test, F-011 Celery dead-broker timing); the other 6 were concurrent-test-DB / mid-run tree-flux confounds that pass clean. CI (Linux) `main` is green. | Partial |
| Backend targeted (health + capabilities, 74 tests) | pass (on the F-002 branch) | Verified OK |
| Frontend `tsc --noEmit` + i18n gate | pass | Verified OK |
| Frontend `vite build` (production) | pass (exit 0, ~2m) | Verified OK |
| Frontend `vitest` | 2314 / 2325 pass; 11 timeout-class fails (F-007, likely environmental; CI green) | Partial |
| `pip-audit` (backend requirements) | No known vulnerabilities | Verified OK |
| `npm audit` prod (CI gate) | 0 vulnerabilities | Verified OK |
| `npm audit` full (incl. dev) | 12 (5 moderate, 7 high), all dev-only — vitest/vite (F-008) | Partial |

## 6. Inventory (from code, not the README)

- **Frontend routes:** ~40, in `frontend/src/router/AppRoutes.tsx` (one router).
  Consumer storefront (browse-first, guest-friendly), public/auth/legal, B2B
  (`/b2b` + `/partner` aliases), admin (`/admin`), honest `*` 404. Full per-route
  rows in `coverage-matrix.md`.
- **API:** **286 canonical `/api/v1` operations** (856 total — every router is also
  mounted at `/v1` and bare). Dumped from the live OpenAPI schema. Feature groups:
  auth/MFA/GDPR, catalog/search/currency, cart, commerce/orders/returns, payments
  + webhooks, stylist, try-on (`/try-on` **and** `/tryon` aliases — F-005), visual
  search, wardrobe/gap-analysis, outfit/public-looks, profile/wishlist/onboarding,
  brand/partner portal, admin governance/analytics/audit, health/telemetry,
  media/uploads.
- **Data model:** 46 Alembic migrations; validator confirms the live tables (users,
  products, product_skus, orders/order_items/events, carts, outfits, wardrobe_items,
  tryon_sessions, payment_transactions, fulfillment_groups, audit_logs +
  verification chain, brand_memberships, etc.).
- **Integrations:** AI stylist chain `local_gpu,nvidia,groq,gemini,openai,unorouter`
  + NVIDIA NIM key pool + Qwen2.5-VL; Gemini vision (visual search); Modal GPU
  worker (try-on, honest 503); 5 payment PSP adapters (Stripe, Tabby, Tamara,
  Paymob, Fawaterak); S3/R2 object storage; Brevo/SMTP email; 8 Modal worker
  services. Env surface enumerated in `backend/app/core/config.py` / `.env.example`.

## 7. Findings so far

See [`findings.md`](findings.md). Summary: **F-001** P0 production down (Neon quota,
owner action); **F-002** P1 `/health` 500 → fixed in PR #376; **F-003** P2 Windows
UTF-8 collection failure (parity); **F-004** P2 release gate blocks merges (F-001
consequence); **F-005** P3 try-on route aliases; **F-006** P3 stale AGENTS.md;
**F-007** P3 local vitest flakiness; **F-008** P3 dev-only npm advisories. Plus
recorded discrepancies vs the brief (providers, PSPs, workers).

## 8. Next

Phase 0 deliverables are in place (this baseline, the coverage matrix, the findings
list). Awaiting go-ahead before Phase 1 (per-page/per-feature review) and before any
broad change. Safe, parity-only fixes that can proceed immediately if approved:
F-003 (add `encoding="utf-8"`) and F-006 (AGENTS.md head). F-001 remains the owner's
action and gates all production verification and PR merges.
