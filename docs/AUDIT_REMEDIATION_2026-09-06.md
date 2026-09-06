# CONFIT — Audit Remediation Report

**Date:** 6 September 2026
**Input:** Comprehensive audit of `https://confit-a.vercel.app/` dated 5 September 2026
**Method:** Every finding was **reproduced against the current `main` branch** with a headless-browser (Playwright/Chromium) probe and a locally-run full stack (FastAPI against an isolated Neon Postgres test database, `confit_fixverify`) before any code was written. Findings that only existed on the **stale Vercel deployment** (old bundle) are labelled as such; findings that were still real in `main` were fixed via the PRs below.

---

## 1. Deployment staleness — the audit tested an old bundle

The deployed bundle at audit time contained `"was dropped"`, `Demo Payment Mode` markers and the pre-fix Outfit Builder — strings absent from `main` since commit `c61da14` (4 Sep). **Several audit findings (CART-01, WARD-01, SEARCH-01 root cause, VTON-02, AUTH-01-as-experienced) were already fixed in `main` but never deployed.** Ground truth measured locally on `main` before this remediation campaign:

| Audit ID | On stale deployment | On current `main` (probed) |
|---|---|---|
| AUTH-01 login flow | Failed | ✅ Works (server-side `/auth/login` + `/auth/me` verified live with cookie jar) |
| AUTH-02 B2B/Admin gates | Dead buttons | ❌ **Still broken** → fixed in PR #55 |
| BUILDER-01/02 | Broken | ❌ **Still broken** (differently) → fixed in PR #56 |
| FIT-01 `/fit` | Wrong page | ❌ **Still broken** → fixed in PR #57 |
| SEARCH-01 visual search | Stuck "Analyzing" | ✅ Works (backend `AttributeError` already fixed); hardened in PR #62 |
| CART-01 add-to-bag | Didn't update | ✅ Works (server cart + optimistic reconciliation) |
| WARD-01 wardrobe | Endless scanning | ✅ Terminal empty/error states exist |
| VTON-02 hidden upload | Hidden input, no trigger | ✅ Visible "📸 Upload Photo" trigger wired to input |
| LEGAL-01 legal links | → `/profile` | ❌ **Still broken** → fixed in PR #58 |
| I18N-01 raw keys | `nav.wardrobe` visible | ❌ **Still broken** → fixed in PR #60 |
| DATA-02 zero flash | `(0)` then `(9)` | ❌ **Still broken** → fixed in PR #61 |
| VTON-01 fake fit claims | "92% Fit" before inference | ⚠️ Partially fixed on main; hardened in PR #62 |
| PAY-01 demo payments | Demo adapter | ✅ Honest "Demo Payment Mode" banner + `payment_mode: demo` order marker (disclosure-first strategy) |

---

## 2. Fix index (all merged to `main` via merge PRs, CI-gated)

| PR | Branch | Audit items | Fix summary | Regression tests added |
|---|---|---|---|---|
| [#55](https://github.com/OmarAhmed-123/CONFIT_A/pull/55) | `fix/auth-b2b-admin-gates` | **AUTH-02**, AUTH-01 (UX half) | `<AuthModal>` + `<Toast>` mounted at app root (were consumer-only → B2B/Admin "Sign In" buttons were dead); `fetchMe()` bootstrap at app root (BrandLayout never restored sessions); `hasAttemptedBootstrap` gate state (no guest-gate flash with a valid cookie); post-login **role landing** (brand→`/b2b`, admin→`/admin`); StrictMode-safe SplashScreen (dev: splash blocked every click forever) | `authStore.bootstrap.test.tsx` (4) |
| [#56](https://github.com/OmarAhmed-123/CONFIT_A/pull/56) | `fix/outfit-builder-slots` | **BUILDER-01, BUILDER-02** | Root cause 1: `PointerSensor` had no `activationConstraint` → dnd-kit swallowed plain clicks (proven: JS click worked, mouse click didn't). Fixed with `distance: 6`. Root cause 2: accessory slot modelled but not rendered → clutch/tie mutated totals invisibly. Accessory slot is now first-class with same replace/remove/validate rules | `useOutfitBuilderViewModel.test.tsx` (5) |
| [#57](https://github.com/OmarAhmed-123/CONFIT_A/pull/57) | `fix/fit-finder-route` | **FIT-01** | `/fit` now renders a dedicated **FitFinderView** (was TryOnFitView): full anthropometric form (height/weight/chest/waist/hip/shape/preferred fit, cm⇄in), server recommendation via `/tryon/no-photo-fit` with confidence + "Why this size" breakdown + brand tendency + return risk + size table, loading/error/empty states, optional privacy-preserving save through the F-14-gated measurement-session API. Hardcoded `verdict="96% Fit"` badge → real score | — |
| [#58](https://github.com/OmarAhmed-123/CONFIT_A/pull/58) | `fix/legal-pages` | **LEGAL-01** | Public `/privacy`, `/terms`, `/gdpr` (v3.0 = backend `POLICY_VERSION`), content matched to system reality (24h try-on photo expiry, demo payments disclosed in Terms, real export/erase endpoints), footer retargeted | — |
| [#60](https://github.com/OmarAhmed-123/CONFIT_A/pull/60) | `fix/i18n-completeness` | **I18N-01** | Wrong keys fixed (`nav.wardrobe`→`nav.my_wardrobe` etc.); new `common/nav/layout/footer/b2b_layout` namespaces with real Arabic; `parseMissingKeyHandler` humanizes any future missing key (raw dotted keys can never render again); footer + FAB + Sign In translated | — |
| [#61](https://github.com/OmarAhmed-123/CONFIT_A/pull/61) | `fix/catalog-loading-states` | **DATA-02** | Counts never render pre-data: `View All Catalog →` (countless) while loading; `Loading verified styles…` instead of "Showing 0"; counters read the same resolved query cache as the grids | — |
| [#62](https://github.com/OmarAhmed-123/CONFIT_A/pull/62) | `fix/vton-search-honesty` | **SEARCH-01, VTON-01** (hardening) | 30s `AbortController` timeout on every API request (`REQUEST_TIMEOUT` vs `NETWORK_ERROR`); visual-search failures persist inline with Try-again and **clear stale results**; try-on stage label says "Rendering N layer(s)…" until inference completes — composition never presented as a finished drape | — |

**Verification performed per PR:** `tsc --noEmit` clean · full vitest suite green (35 tests after campaign) · production `vite build` green · Playwright E2E against local stack (login flows for all three roles, builder click/drag/total math to the cent, `/fit` real calculation + profile save, Arabic RTL with zero raw keys, throttled-catalog zero-flash check, forced-failure visual search).

---

## 3. Backend / data truth-check (no-code changes needed)

The backend was verified **healthy and honest** against production and an isolated clone:

- `GET /api/v1/health` → database ok, schema at head `0016_vton_temporary_delivery`, VTON engine registry reporting the commercially-licensed `fashn_vton_segfee` fork, storage honestly flagged `production_grade: false` (local FS on serverless).
- `POST /api/v1/auth/login` + `GET /api/v1/auth/me` → full token + httpOnly cookie + CSRF round-trip works with the audited demo accounts.
- Neon production DB contains the real schema (51 tables) and seeded role accounts; the schema-drift gate (503 `SCHEMA_DRIFT`) is active by design.
- Guest carts, measurement sessions, orders, GDPR export/erase endpoints all exist server-side.

## 4. Remaining items that are **operations, not code** (owners must supply credentials/infra)

1. **Redeploy** `main` on Vercel so the accumulated fixes actually reach `confit-a.vercel.app` (the audit-experienced bugs were largely stale-bundle issues). If auto-deploy is connected, the merges above trigger it.
2. **Cloudflare "Workers Builds: confit-a" check is failing** (pre-existing, non-required for merge). Inspect the Cloudflare dashboard build `7868cb1c…` if that target is still wanted.
3. **Photorealistic VTON output (VTON-01 tail):** the worker URL + admin token are configured and health-reported, but a real GPU inference **output** must be demonstrated (job log + before/after image) before marketing language stronger than "rendering" is used. The UI now never claims completion before output arrives.
4. **Live payments (PAY-01):** connect Stripe/Tabby/Tamara keys and set `PAYMENTS_LIVE=true`; until then the checkout keeps its explicit Demo Payment Mode banner and `payment_mode: demo` order markers. This is the honest-by-construction state.
5. **DATA-01 tail:** the product/SKU/inventory schema is real, but brand catalog feeds are seeded fixtures with Unsplash imagery. Real brand onboarding/import (B2B catalog import with `source` + `last_synced`) is the remaining commercial work.
6. **Secrets hygiene:** the DATABASE_URL and GitHub PAT shared during this engagement should be rotated; `.env` files are gitignored and were never committed.

## 5. How to re-run the verification

```bash
# Backend (isolated DB recommended)
python3 -m alembic -c backend/alembic.ini upgrade head
PYTHONPATH=. python3 -c "from backend.app.seed_data import seed_database; seed_database()"
PYTHONPATH=. uvicorn backend.app.main:app --port 8000

# Frontend
cd frontend && npm ci && npm run dev   # proxies /api -> :8000

# Tests
cd frontend && npm test               # vitest, 35 green
```

**Completion standard applied (per the audit's directive):** a feature counts as fixed only when a real state mutation or a real server response was demonstrated — every PR above includes a probe that proves exactly that.
