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
| `/` | HomeView | IMPLEMENTED, not PASS. Hero and in-page sections moved to white-first tokens; focus ring fixed (was `ring-white`, invisible on white). Still open: shared navbar and floating AI Stylist pill are legacy (see Global shells); product rails show "could not be loaded" without backend, so rails are unverified with live data. See evidence below. |
| `/discover`, `/products`, `/stylist` | DiscoverView | NOT_STARTED as a page. Its hero is the shared `HeroSection`, so it already renders white-first; the rest of the page is still legacy and unreviewed |
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
| `ConsumerLayout`, `ConsumerNavbar` (header, nav, footer) | NOT_STARTED. Still gold and navy: the gold rule under the header, the navy Sign In button, and the floating "AI Stylist Director" pill (dark, gold text). Seen in the HomeView captures |
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

## Homepage (`/`) — evidence (HomeView + shared HeroSection)

- Status: IMPLEMENTED, not PASS. The page sits inside the legacy consumer shell (see Global shells), and the product rails could not be checked with live data.
- Shared change: `HeroSection` (also used by DiscoverView) is now a white panel (`bg-white`, `border-brand-hairline`, charcoal heading, `brand-muted` support text). Glows are light lilac and mint at low opacity, decorative only. The photo caption overlay keeps white text on its black scrim. The no-photo placeholder is a plain charcoal fill. The light aside card's focus ring offset is white.
- Per-page changes in HomeView: dark glass eyebrow, facts pills and secondary button → white or `brand-wash` with charcoal text. Gold primary CTA → charcoal with white text (14.99:1). Gold link → charcoal underlined link. Gold focus rings → charcoal. Section labels, chips, and icon colours moved to charcoal and white. Photo-palette metadata arrays (`palette:` lines, around 306–327) are kept unchanged, because they describe image colours and are not UI styling.
- Fixed in this pass: the primary CTA focus ring was `ring-white`, which is invisible on a white page. It is now `ring-brand-charcoal` with a white offset. Pixel check shows the charcoal ring and the white gap.
- Contrast (computed): charcoal on white 14.99:1; white on charcoal 14.99:1; charcoal on lilac badge 5.91:1; muted on wash 6.2:1; field boundary on white 3.33:1.
- Tests: `homeHero.brand.test.tsx` (6 source-level contracts: no legacy tokens in HeroSection; no legacy tokens in HomeView outside `palette:` data; primary CTA charcoal; no white focus ring; charcoal focus rings). Full vitest 108 files / 1385 tests passed. `tsc --noEmit` exit 0. `npm run build` exit 0.
- Captures (`/home/user/brand_build/shots/`): `pre_home_desk.png`, `pre_home_mob.png`, `post_home_desk.png`, `post_home_mob.png` (full page at 1280px and 390px), `*_fold.png`, and `qa_home_desk_sheet.png` (before and after side by side). Keyboard: a real Tab sequence reaches the primary CTA with `:focus-visible` (`post_home_focus_kbd_desk.png`).
- Limits: backend is not running, so the "Today's style picks" and "New in" rails show their error state in both before and after captures. The occasion cards, editorial stack and footer were reviewed only at half scale in the contact sheet. Arabic and RTL were not captured for the homepage in this pass.

## Known pre-existing issues (not caused by this migration)

- Backend API is not running in the sandbox; pages show 502 responses for data calls. Visual checks cover layout only; data-driven states need a running backend.
- `origin/main` was merged into this branch at `412c341` (no conflicts). Re-check `behind` status before any merge.
- `npm run build` prints a rolldown plugin-timing notice (`vite:css-post`). It is informational and exits 0.
