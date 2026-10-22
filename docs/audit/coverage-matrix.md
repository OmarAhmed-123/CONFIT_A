# CONFIT_A — Coverage Matrix

Single source of truth for review progress. One row per page or feature group.
Columns: **FE** (frontend behavior) · **API** · **DB** · **Integr.** (integrations) ·
**Design/A11y** · **i18n/RTL** · **Tests** · **Status** · Findings.

Cell legend: `OK` verified by running · `DEF` defect · `PART` partial ·
`NR` not reviewed · `—` not applicable. Row **Status**: Verified OK / Defect /
Partial / Not reviewed.

**SPECS scoring (third brief):** during Phase 1 each row is also scored on the five
SPECS dimensions — **S**ecurity, **P**erformance, **I**ntegrity, **C**ompatibility,
**S**calability — with measured evidence (same cell legend). These columns are added
per row as that row is reviewed; until then they are `NR`. Current cross-cutting SPECS
gaps are tracked in `STATUS.md`.

> **Global blocker:** production is down (F-001, Neon quota). Any row needing the
> production API cannot be marked Verified OK until production is restored. Local
> review (code + local dev server) proceeds regardless.

Inventory sizes (from code, 2026-10-22): **~40 frontend routes**, **286 canonical
`/api/v1` operations**, **46 Alembic migrations (0001–0046)**, **8 worker services**.

## Frontend pages (consumer)

| Route | FE | API | DB | Integr. | Design/A11y | i18n/RTL | Tests | Status | Findings |
|---|---|---|---|---|---|---|---|---|---|
| `/` Home | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/discover` `/catalog` `/products` `/wishlist` `/favorites` `/stylist` → DiscoverView | NR | NR | NR | NR | NR | NR | NR | Not reviewed | search/stylist share this view |
| `/brands` `/brands/:slug` `/stores` → BrandsView | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/product/:slug` `/products/:slug` ProductDetail | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/builder` `/outfits/:id` OutfitBuilder | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/outfits` `/my-looks` MyLooks | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/tryon-studio` `/try-on` `/try-on/:sessionId` `/visual-search` TryOn studio | NR | NR | NR | NR | NR | NR | NR | Not reviewed | honest 503 path to verify |
| `/fit` `/fit-finder` FitFinder | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/wardrobe` `/wardrobe/item/:id` Wardrobe | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/cart` `/checkout` Checkout | NR | NR | NR | NR | NR | NR | NR | Not reviewed | checkout gate |
| `/orders` `/orders/:orderNumber` `/returns` OrderTracking | NR | NR | NR | NR | NR | NR | NR | Not reviewed | guarded |
| `/profile` `/settings` `/notifications` UserProfile | NR | NR | NR | NR | NR | NR | NR | Not reviewed | onboarding wizard host |

## Frontend pages (public / auth / legal)

| Route | FE | API | DB | Integr. | Design/A11y | i18n/RTL | Tests | Status | Findings |
|---|---|---|---|---|---|---|---|---|---|
| `/looks/:token` SharedLook | NR | NR | NR | — | NR | NR | NR | Not reviewed | public token |
| `/email/unsubscribe` | NR | NR | NR | — | NR | NR | NR | Not reviewed | signed token |
| `/reset-password` `/verify-email` | NR | NR | NR | — | NR | NR | NR | Not reviewed | one-time token |
| `/auth` `/login` `/register` (→ modal) | NR | NR | — | — | NR | NR | NR | Not reviewed | redirect to `/?auth=` |
| `/privacy` `/terms` `/gdpr` Legal | NR | — | — | — | NR | NR | NR | Not reviewed | |
| `/brand/register` `/partner/register` | NR | NR | NR | — | NR | NR | NR | Not reviewed | |
| `*` NotFound (404) | NR | — | — | — | NR | NR | NR | Not reviewed | honest 404 |

## Frontend pages (B2B / partner / admin)

| Route | FE | API | DB | Integr. | Design/A11y | i18n/RTL | Tests | Status | Findings |
|---|---|---|---|---|---|---|---|---|---|
| `/b2b` + `/partner` dashboard | NR | NR | NR | NR | NR | NR | NR | Not reviewed | tenant-isolated |
| `/b2b/catalog` `/inventory` `/branches` `/stores` | NR | NR | NR | NR | NR | NR | NR | Not reviewed | CSV import |
| `/b2b/team` + `/team/accept` | NR | NR | NR | NR | NR | NR | NR | Not reviewed | invitations |
| `/b2b/orders` | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/b2b/analytics` (lazy) | NR | NR | NR | NR | NR | NR | NR | Not reviewed | recharts chunk |
| `/b2b/placements` | NR | NR | NR | NR | NR | NR | NR | Not reviewed | ad loop |
| `/admin` overview/analytics (lazy) | NR | NR | NR | NR | NR | NR | NR | Not reviewed | admin only |
| `/admin/catalog` `/partners` | NR | NR | NR | NR | NR | NR | NR | Not reviewed | |
| `/admin/audit` | NR | NR | NR | NR | NR | NR | NR | Not reviewed | audit chain UI |

## Backend feature groups (API)

| Feature group | API | DB | Integr. | Tests | Status | Findings |
|---|---|---|---|---|---|---|
| Auth / session / MFA / GDPR (`/auth/*`) | NR | NR | — | NR | Not reviewed | |
| Catalog / search / currencies (`/catalog/*`) | NR | NR | FX | NR | Not reviewed | |
| Cart (`/cart/*`) | NR | NR | — | NR | Not reviewed | IDOR checks |
| Commerce / checkout / orders / returns | NR | NR | payments | NR | Not reviewed | |
| Payments / webhooks (`/payments/*`) | NR | NR | 5 PSPs | NR | Not reviewed | demo mode |
| Stylist AI (`/stylist/*`) | NR | NR | NVIDIA/Groq/Gemini/OpenAI/UnoRouter | NR | Not reviewed | grounding |
| Try-on (`/try-on/*`, `/tryon/*`) | NR | NR | Modal GPU | NR | Not reviewed | F-005 aliases; honest 503 |
| Visual search (`/visual-search/*`) | NR | NR | Gemini vision | NR | Not reviewed | |
| Wardrobe / gap analysis (`/wardrobe/*`) | NR | NR | workers | NR | Not reviewed | |
| Outfit builder / public looks | NR | NR | outfit worker | NR | Not reviewed | |
| Profile / wishlist / onboarding | NR | NR | — | NR | Not reviewed | |
| Brand / partner portal (`/brand/*`,`/partner/*`) | NR | NR | — | NR | Not reviewed | tenant isolation |
| Admin governance / analytics / audit | NR | NR | — | NR | Not reviewed | RBAC, audit chain |
| Health / telemetry (`/health*`) | PART | PART | — | OK | Partial | F-002 fixed (PR #376) |
| Media / uploads (`/media/*`, `/uploads`) | NR | NR | S3/local | NR | Not reviewed | 501 when no object store |

## Baseline tooling (this is not a page; tracks Phase 0 health)

| Check | Result | Status |
|---|---|---|
| DB integrity validator (local SQLite) | all checks OK | Verified OK |
| Backend `pytest` (full, Windows, PYTHONUTF8=1) | 4529 pass / 8 fail / 25 skip; clean isolated re-run → 2 genuine Windows-env fails (F-010, F-011), rest confounds; CI (Linux) green | Partial |
| Frontend `tsc` / i18n gate | pass | Verified OK |
| Frontend `vite build` | passes (built ~2m, exit 0) | Verified OK |
| Frontend `vitest` | 2314/2325 pass; 11 timeout-class fails (F-007) | Partial |
| `pip-audit` (backend) | No known vulnerabilities | Verified OK |
| `npm audit` prod (CI gate, `--omit=dev --audit-level=high`) | found 0 vulnerabilities | Verified OK |
| `npm audit` full (incl. dev) | 12 vulns (5 mod, 7 high), all dev-only — vitest/vite (F-008) | Partial |
