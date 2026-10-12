# CONFIT_A platform-wide Logo #3 redesign — Phase A audit

Status vocabulary: `PASS` · `IMPLEMENTED` · `NOT_STARTED` (same as `logo-3-migration-coverage.md`).
Baseline commit: `9a33e94` (branch `feat/brand-logo-individual-grid`, PR #345).

## Discovered inventory (from repository search, not from the brief)

| Area | Evidence | Status |
|---|---|---|
| Frontend stack | React 18 + TypeScript + Vite + Tailwind (`frontend/`), vitest + jsdom | — |
| Routes | `frontend/src/router/AppRoutes.tsx`: 57 `path=` entries | see `logo-3-migration-coverage.md` |
| Logo assets | `frontend/public/brand/`: `confit-logo.svg`, `confit-logo-monochrome.svg`, `confit-logo-reversed.svg`, `confit-symbol.svg`, `favicon.svg`, `apple-touch-icon.png` | PASS (existing; `confitLogo.brand.test.tsx`) |
| Favicon / touch icon | `frontend/index.html` links `/brand/favicon.svg` and `/brand/apple-touch-icon.png` | PASS (index.html reviewed) |
| Legacy colour usage | 54 non-test source files, 981 hits for `1B1F3B`, `C5A059`, `A37E44`, `C9A227`, `FAF9F6`, `B8935A`, `7A5C28`, `FDF8EE` | IMPLEMENTED in ~15 surfaces; the rest NOT_STARTED |
| Consumer shell | `ConsumerLayout`, `ConsumerNavbar`, `TrustFooter`, AI Stylist pill, language and currency switchers | IMPLEMENTED, not PASS (see coverage doc) |
| Global focus token | `src/styles/index.css` `--confit-focus: #A37E44` (pinned by `surfaceSystem.test.tsx`) | OPEN decision |
| Brand/partner shell | `BrandLayout`, `BrandNavbar`, `BrandSidebar` | NOT_STARTED |
| Email templates | `backend/app/services/email_templates.py`: 14 legacy colour hits, 4 logo refs; asset `frontend/public/email/confit-logo.png` | NOT_STARTED (logo asset not yet verified against Logo #3) |
| PDF reports | `backend/app/services/brand_report_pdf.py`: 4 legacy hits (navy/gold header), 12 logo refs; `brand_report_service.py` | NOT_STARTED |
| CSV exports | brand and admin controllers | NOT_STARTED (data contract must not change) |
| Roles | `UserRole` enum in backend; consumer, brand/partner, admin surfaces | Inventory per role in coverage doc |
| Splash | `SplashScreen` (consumer layout, once per session) | PASS |

## Working-tree note

`git status` shows 7 mode-only changes (`100755 => 100644`) under `.specify/scripts/bash/`. They are not part of this work and were not committed. They should be reviewed by the owner before any commit that touches `.specify/`.

## Phased plan (next passes, each with its own verification)

1. Email logo asset: confirm `public/email/confit-logo.png` is Logo #3; replace if not; render-test `email_templates.py` output with a test recipient only.
2. Brand/partner shell (`BrandLayout`, `BrandNavbar`, `BrandSidebar`) and `LanguageSwitcher` in that shell.
3. Admin routes and `RoleGuard` / denial screens.
4. Brand PDF report header and palette (`brand_report_pdf.py`), with byte-level checks that CSV contracts are unchanged.
5. Remaining customer routes in coverage order: Discover, Product detail (done), Checkout, Wardrobe, Try-on, Fit finder, Profile.
6. Global focus token decision (affects every page), then rollout.

## Not claimed

No route is PASS by this audit. Nothing here was rendered or tested beyond the search and the existing coverage evidence.
