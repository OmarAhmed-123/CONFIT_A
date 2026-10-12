# Logo #3 brand migration — page coverage checklist

Source of truth: `frontend/src/router/AppRoutes.tsx` plus the surfaces found by repository search.
Status values: `NOT_STARTED` · `IN_PROGRESS` · `IMPLEMENTED` · `TESTING` · `PASS` · `BLOCKED`.

A row is `PASS` only when its own checks were run after its own changes and the results are recorded in the PR.

## Shared infrastructure

| Surface | Status | Evidence |
|---|---|---|
| Logo SVG assets (`frontend/public/brand/`) | PASS | Rendered and inspected; tests `confitLogo.brand.test.tsx` |
| `ConfitLogo` component (inline SVG, official geometry) | PASS | 7 brand-contract tests; tsc; full vitest |
| Favicon, apple-touch-icon, `index.html` body | PASS | Asset files present; `index.html` diff reviewed |
| Design tokens — `tailwind.config.js` `brand.*` group (official reference colours, neutral control/text tokens) | IMPLEMENTED | Additive only; `confit.*` navy/gold left in place. Accents documented as non-text. Central remap rejected by decision: rollout is per screen. Covered by `authModal.brand.test.tsx` |

## Loading and splash

| Surface | Status | Evidence |
|---|---|---|
| `SplashScreen` (consumer layout, once per session) | PASS | 3 splash tests; full vitest 105 files / 1362 tests; screenshot `01_after_splash.png` reviewed |

## Public, legal and utility routes

| Route | Component | Status |
|---|---|---|
| `/looks/:token` | SharedLookView | NOT_STARTED |
| `/email/unsubscribe` | EmailUnsubscribeView | PASS (ready, working, done, expired, invalid, error, mobile, AR/RTL reviewed; API states mocked; see evidence below) |
| `/reset-password` | ResetPasswordView | PASS (form, policy checklist, error, done, missing-token, focus, mobile, AR/RTL reviewed; API states mocked; see evidence below) |
| `/verify-email` | VerifyEmailView | PASS (ready, keyboard focus, working, done, expired, missing-token/resend, mobile, AR/RTL reviewed; API states mocked; see evidence below) |
| `/privacy`, `/privacy-policy` | PrivacyPolicyView | NOT_STARTED |
| `/terms`, `/terms-of-service` | TermsOfServiceView | NOT_STARTED |
| `/gdpr` | GdprView | NOT_STARTED |
| `*` (404) | NotFoundView | NOT_STARTED |

## Consumer (storefront) routes

| Route | Component | Status |
|---|---|---|
| `/` | HomeView | NOT_STARTED (old navy/gold hero visible in baseline screenshot) |
| `/discover`, `/products`, `/stylist` | DiscoverView | NOT_STARTED |
| `/product/:slug`, `/products/:slug` | ProductDetailView | NOT_STARTED |
| `/builder`, `/outfits/:id` | OutfitBuilderView | NOT_STARTED |
| `/outfits`, `/my-looks` | MyLooksView | NOT_STARTED |
| `/tryon-studio`, `/try-on`, `/try-on/:sessionId`, `/visual-search` | TryOnFitView (error boundary) | NOT_STARTED |
| `/fit`, `/fit-finder` | FitFinderView | NOT_STARTED |
| `/wardrobe`, `/wardrobe/item/:id` | WardrobeView | NOT_STARTED |
| `/cart`, `/checkout` | CheckoutView | NOT_STARTED (commerce path: light scheme only) |
| `/orders`, `/orders/:orderNumber`, `/returns` | OrderTrackingView | NOT_STARTED |
| `/profile`, `/settings`, `/notifications` | UserProfileView | NOT_STARTED |

## Brand (partner) routes — `/b2b` and `/partner`

| Route | Component | Status |
|---|---|---|
| `/b2b`, `/partner`, `/partner/dashboard` | BrandDashboardView | NOT_STARTED |
| `/b2b/catalog`, `/partner/catalog` | BrandCatalogView | NOT_STARTED |
| `/b2b/inventory`, `/partner/inventory` | BrandInventoryView | NOT_STARTED |
| `/b2b/orders`, `/partner/orders` | BrandOrdersView | NOT_STARTED |
| `/b2b/analytics`, `/partner/analytics` | BrandAnalyticsView (lazy) | NOT_STARTED |
| `/b2b/placements`, `/partner/placements` | BrandPlacementsView | NOT_STARTED |
| Partner gateway / lead form | PartnerGatewayView, LeadForm | NOT_STARTED (route not in `AppRoutes`; verify where it is mounted) |

## Admin routes — `/admin`

| Route | Component | Status |
|---|---|---|
| `/admin`, `/admin/overview`, `/admin/analytics` | AdminAnalyticsView (lazy) | NOT_STARTED |
| `/admin/catalog`, `/admin/partners` | AdminCatalogView | NOT_STARTED |
| `/admin/audit` | AdminAuditView | NOT_STARTED |

## Global shells and components

| Surface | Status |
|---|---|
| `ConsumerLayout`, `ConsumerNavbar` (header, nav, footer) | NOT_STARTED |
| `BrandLayout`, `BrandNavbar`, `BrandSidebar` | NOT_STARTED |
| `AuthModal` (login, register, MFA, recovery) | PASS |

`AuthModal` evidence: white banner with the official mark (theme `dark`), charcoal primary action, charcoal underlined links (gold `#C5A059` was 2.46:1 on white), field border `#8A8D93` (3.33:1, WCAG 1.4.11), legacy navy/gold/cream and `backdrop-blur` removed. Logic, routes, and API calls unchanged.
- Checks run: `tsc` 0; focused auth suites 12 files passed; `authModal.brand.test.tsx` 7/7; full vitest 106 files / 1371 tests passed; `npm run build` 0.
- Screenshots reviewed (sandbox at `/home/user/brand_build/shots/`): `before_*` vs `after_*` for sign-in, sign-up, forgot, focus, error, loading, mobile (390px), and Arabic RTL (`after_rtl_mob.png`, `dir=rtl` confirmed).
- Limits: the MFA step, the forgot "sent" and "unconfigured" states, and data-backed success states were not captured because the backend is not running. ESLint is not configured for this repo (`eslint` fails before linting), so lint was not run.
| `AuthPageShell` (email-landing card shell, used only by the three account pages above) | PASS | White page, hairline card. Verified through the three pages' checks below |
| `RoleGuard` (logo on guard/denial screens) | NOT_STARTED |
| `ShareCard` (shared look image text) | NOT_STARTED |
| Shared UI primitives (buttons, inputs, tables, cards, modals, toasts) | NOT_STARTED |

## Emails, reports and exports

| Surface | Source | Status |
|---|---|---|
| Email shell and logo (`logo_url()`, header colours) | `backend/app/services/email_templates.py`, `frontend/public/email/confit-logo.png` | NOT_STARTED |
| Transactional templates (order, payment failed, shipping, saved look, outfit ready, fit result, price drop, partner approval, admin alert, newsletter) | `email_templates.py` | NOT_STARTED |
| Brand/admin PDF report | `backend/app/services/brand_report_pdf.py` (`draw_logo`, navy/gold header) | NOT_STARTED |
| CSV exports | brand/admin controllers | NOT_STARTED (data contract must stay unchanged) |

## Account pages — evidence (VerifyEmail, ResetPassword, EmailUnsubscribe)

- Shared change: `AuthPageShell` page background cream `#FAF9F6` → white; card hairline. Shared auth field/button styles from the AuthModal pass.
- Per-page changes: cream icon chips → `brand-wash`; navy headings → charcoal; gold-dark `#A37E44` icons and links → charcoal; gold focus ring → charcoal; secondary text → `brand-muted`; links charcoal and underlined by default (`#A37E44` on white is 3.73:1, below 4.5:1 for text). Semantic emerald success, rose error, and amber warning (decorative `StatusIcon`) kept.
- Tests: `accountRecovery.brand.test.tsx` (7 source-level brand contracts). Existing `accountRecoveryPages.test.tsx` (15 behaviour and axe tests) unchanged and passing. Together: 22/22.
- Browser captures in sandbox at `/home/user/brand_build/shots/`: `pre_*` (committed state before this pass) and `post_*` (after), desktop 1280px, mobile 390px, AR/RTL on mobile.
- Keyboard: a real Tab press on VerifyEmail focuses the primary button with `:focus-visible` and a charcoal ring (`post_ve_focus_kbd_desk.png`). ResetPassword input focus ring checked (`post_rp_focus_desk.png`).
- API states are MOCKED in the browser (Playwright route fixtures), labelled `_mocked`. The backend is not running in the sandbox. Request counts were recorded to confirm the mocked calls fired.
- Known finding, NOT changed (pre-existing): a server `AUTH_FAILED` on verify-email shows "Your session has expired. Please sign in again." (`errors.auth_failed` mapping in `apiErrors.ts`). That copy is wrong for a verification link. Out of brand scope; flagged for a copy/mapping fix.

## Known pre-existing issues (not caused by this migration)

- Backend API is not running in the sandbox; pages show 502 responses for data calls. Visual checks cover layout only; data-driven states need a running backend.
- `origin/main` was merged into this branch at `412c341` (no conflicts). Re-check `behind` status before any merge.
- `npm run build` prints a rolldown plugin-timing notice (`vite:css-post`). It is informational and exits 0.
