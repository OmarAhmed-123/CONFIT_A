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
| `/privacy`, `/privacy-policy` | PrivacyPolicyView | IMPLEMENTED, not PASS. Shared `LegalViews` colour pass; tab focus verified; AR/RTL not reviewed (see Legal evidence) |
| `/terms`, `/terms-of-service` | TermsOfServiceView | IMPLEMENTED, not PASS. Same shared pass; tab focus verified; AR/RTL not reviewed |
| `/gdpr` | GdprView | IMPLEMENTED, not PASS. Same shared pass; tab focus verified; AR/RTL not reviewed |
| `*` (404) | NotFoundView | IMPLEMENTED, not PASS. White page, charcoal primary CTA, brand-wash glyph tile, brand-muted secondary text, charcoal focus ring (was gold `#C5A059`). Desktop, mobile and keyboard focus captured. AR/RTL not yet reviewed. See 404 evidence below. |

## Consumer (storefront) routes

| Route | Component | Status |
|---|---|---|
| `/` | HomeView | IMPLEMENTED, not PASS. Hero and in-page sections moved to white-first tokens; focus ring fixed (was `ring-white`, invisible on white). Still open: shared navbar and floating AI Stylist pill are legacy (see Global shells); product rails show "could not be loaded" without backend, so rails are unverified with live data. See evidence below. |
| `/discover`, `/products`, `/stylist` | DiscoverView | IMPLEMENTED, not PASS. Class-level brand mapping applied (gold, navy, cream, slate text, eyebrow labels, search and sort focus rings). Shared `HeroSection` and `ProductCard` changes included. Still open: loading and empty states, filter and search behaviour with live data, mobile and AR/RTL review. The AI Stylist pill label was measured and is not clipped. See Discover evidence below. |
| `ProductCard` (shared component: Home, Discover, Wardrobe, MyLooks, `InteractionPrimitives`, `TryOnButton`) | ProductCard | IMPLEMENTED, not PASS. Legacy class and icon colours mapped. Changes reach every consumer above, so those pages are NOT marked PASS by this change and each still needs its own review |
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
| `ConsumerLayout`, `ConsumerNavbar` (header, nav, footer), `TrustFooter` | IMPLEMENTED, not PASS. Shared by every consumer page. White page root; light utility strip; charcoal Sign In and avatar; white AI Stylist pill with charcoal icon chip; light footer with charcoal headings and muted links; semantic emerald status kept in TrustFooter. Still legacy: the gold-dark focus token `--confit-focus` (#A37E44, 3.73:1 on white, pinned by `surfaceSystem.test.tsx`) and the register palette in `design/registers.ts` (commerce ink #1B1F3B, editorial ink #6B4F1E, other register accents). The editorial accent (navigation rule under the header) is now charcoal. See Shell evidence |
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
- CI gate finding (commit 5827f2d): the `stylist drawer browser gate` (`scripts/stylist_browser_gate.sh`) FAILED on axe colour-contrast (4 nodes, EN and AR). The probe opens the drawer on `/`, so the homepage behind it is scanned. Cause: the new `brand-wash` section background with legacy `text-slate-500` text (4.4:1). Fixed: all HomeView `text-slate-*` moved to brand tokens. Local reproduction and re-run: axe 0 violations (EN and AR), keyboard probe PASS, gate result PASS. The probe reports 59 axe 'incomplete' items per locale; these are not counted as passes.
- Photo-overlay labels (occasion cards) were charcoal on a black gradient after the blanket gold-to-charcoal mapping, which made them illegible. Changed to white (and white/90 for captions). Covered by `homeHero.brand.test.tsx`.
- Contrast (computed): charcoal on white 14.99:1; white on charcoal 14.99:1; charcoal on lilac badge 5.91:1; muted on wash 6.2:1; field boundary on white 3.33:1.
- Tests: `homeHero.brand.test.tsx` (8 source-level contracts: no legacy tokens in HeroSection; no legacy tokens in HomeView outside `palette:` data; primary CTA charcoal; no white focus ring; charcoal focus rings). Full vitest 108 files / 1387 tests passed. `tsc --noEmit` exit 0. `npm run build` exit 0.
- Captures (`/home/user/brand_build/shots/`): `pre_home_desk.png`, `pre_home_mob.png`, `post_home_desk.png`, `post_home_mob.png` (full page at 1280px and 390px), `*_fold.png`, and `qa_home_desk_sheet.png` (before and after side by side). Keyboard: a real Tab sequence reaches the primary CTA with `:focus-visible` (`post_home_focus_kbd_desk.png`).
- Limits: backend is not running, so the "Today's style picks" and "New in" rails show their error state in both before and after captures. The occasion cards, editorial stack and footer were reviewed only at half scale in the contact sheet. Arabic and RTL were not captured for the homepage in this pass.

## Consumer shell — evidence (ConsumerLayout, ConsumerNavbar, TrustFooter, AI Stylist pill)

- Status: IMPLEMENTED, not PASS. The shell is shared by all consumer routes. Only `/` (homepage) was captured for the shell. Other consumer pages are not marked PASS by this change.
- Changes: root `bg-[#FAF9F6] text-[#1B1F3B]` → `bg-white text-brand-charcoal`. Gold rule and text links → charcoal. Navy Sign In and avatar → `brand-charcoal` with white text. Cream accent fills → `brand-wash`. Gold accent icons → charcoal (`#252729`). AI Stylist pill: navy with gold label → white with charcoal icon chip and charcoal label, `shadow-lg`, `border-brand-field`. Footer: `bg-brand-wash`, charcoal headings, muted text and links, charcoal brand-portal CTA. TrustFooter: dark-panel text (`slate-300/400`) → brand tokens. Live status stays emerald (`bg-emerald-50 text-emerald-700`).
- Unchanged on purpose: the neutral slate surface fills and borders (`bg-slate-100`, `border-slate-200/80`) and the `backdrop-blur-md` header. Neutrals are not brand colours.
- Captures (`/home/user/brand_build/shots/`): `pre_shell_*` and `post_shell_*` for desktop fold, desktop dropdown menu, footer, mobile fold, mobile drawer, keyboard focus on nav and FAB. Side-by-side: `qa_shell_desk_fold_pre_post.png`, `qa_shell_mob_fold_pre_post.png`, `qa_shell_footer_pre_post.png`.
- Focus check: the global focus outline is a 3px ring. An earlier white reading was taken while the splash overlay covered the page, so it was not a real defect. The gold-dark ring (`#A37E44`) is visible on the focused FAB (`pre_fab_focus_desk.png`, `post_fab_focus_desk.png`). Decision open: whether to move `--confit-focus` to charcoal. That would need the `surfaceSystem` test updated.
- Tests: `components/navigation/__tests__/shellBrand.brand.test.tsx` (10 contracts: no legacy tokens and no slate text in the three files; root white; pill styling; RTL `end-6`; emerald kept). Focused suite across navigation, a11y, commerce, design and layouts: 13 files, 230 tests passed.
- CI gate (`scripts/stylist_browser_gate.sh`, same as CI): PASS locally. axe 0 serious/critical and 0 colour-contrast violations in EN and AR. Keyboard probe PASS in EN and AR. 59 axe "incomplete" items per locale are reported and not counted as passes.

- Navigation-rule pass (this change): the editorial register accent under the header is charcoal (`main` top border measured `rgb(37,39,41)` 3px at 1280px). Body text selection changed from bronze `#B8935A` and navy `#1B1F3B` to charcoal in `frontend/index.html`. The AI Stylist button's accessible name is now its visible label (`layout.ai_stylist_director`, "AI Stylist Director"); before, it was "Open AI Virtual Stylist", which fails WCAG 2.5.3 Label in Name. Covered by `shellBrand.brand.test.tsx` (3 new contracts) and `registers.test.tsx`.
- Pill label clipping: an earlier concern was checked and is not a defect in the pill. `pill_label.mjs` measures the label ending 21px inside the pill's right edge at 1280px and 1024px. The apparent clip in the screenshots came from a round badge in the bottom-right corner of the preview frame, which overlaps the pill and is not app markup.
- Keyboard focus, FAB: the AI Stylist button shows a solid 3px charcoal focus outline (`fab_focus_pixels.mjs`; crop `qa_post2_fab_focus_crop.png`).
- Shell status stays IMPLEMENTED, not PASS. Checked: desktop and mobile home captures, keyboard focus on nav and FAB. Not yet checked: mobile drawer and menu states in AR/RTL, `RoleGuard`, and every other consumer page that uses this shell.

## Discover — evidence (DiscoverView + shared ProductCard)

- Status: IMPLEMENTED, not PASS. Pass is blocked by items listed under Limits.
- Changes in DiscoverView: gold → charcoal, cream → `brand-wash`, navy → charcoal, slate text → `brand-muted`. Eyebrow labels `#7A5C28` → `brand-muted`. The search input and sort select use a charcoal border and a 2px charcoal focus ring with a white offset (was a gold ring at 25% opacity, too faint for a focus indicator). Colour-name swatch hex values (`#1B1F3B`, `#FAF9F6`, `#D4AF37`) stay: they are product colour data, not chrome.
- Changes in ProductCard: all legacy class and icon colours mapped (`RulerIcon` → `#252729`). `StatusIcon` is not changed.
- Tests: `views/__tests__/discoverBrand.contract.test.tsx` (4 Discover contracts, 2 ProductCard contracts). The 20 related Discover and ProductCard suites pass (325 tests). `tsc` exit 0.
- Captures (`/home/user/brand_build/shots/`): `pre_live_*` and `post_live_*` (backend down, 502 error state, no page errors). `pre_mocked__*` and `post_mocked__*` (`_mocked` fixtures, populated 6-product grid, no page errors). Review images: `qa_{pre,post}_discover_mocked_desk_{fold,grid}.png` (pre and post pairs).
- Keyboard focus: `discover_focus.mjs` tabs to the search input. Probe: border `rgb(37,39,41)`, box-shadow ring `rgb(37,39,41)` 2px with a white 2px offset. Pixel review: `qa_post_discover_search_focus.png`.
- Limits (why not PASS):
  - Backend not running. Catalogue, cart and try-on endpoints return 502 in live captures. Populated states are `_mocked` only.
  - Loading and empty states not captured separately.
  - Filter, search and sort behaviour not verified with live data.
  - Mobile captures (`*_mob_*`) taken but not yet reviewed. No AR/RTL review.
  - Pill label: measured, not clipped (21px inside the pill edge at 1280px and 1024px). The apparent clip in screenshots is a preview-frame badge that overlaps the pill.
  - Shared `ProductCard` change affects Home, Wardrobe, MyLooks and try-on. Those pages need their own review.

## 404 — evidence (NotFoundView, catch-all route)

- Status: IMPLEMENTED, not PASS. Static page; no backend dependency. AR/RTL not yet verified.
- Changes: page root `#FAF9F6` → white. Glyph tile cream gradient → `brand-wash`. Navy text and CTA → charcoal (`#1A1B1D` hover, matching the consumer shell CTA). Slate text → `brand-muted`. Secondary button border `slate-300` → `brand-field` (3.33:1 control boundary), hover border gold → charcoal. Focus rings gold `#C5A059` → charcoal (3 places).
- Tests: `views/__tests__/notFound.brand.test.tsx` (4 contracts). `accountRecoveryPages`, `outfitBuilderContract` and the new suite pass (44 tests).
- Captures: `shots/pre_404_{desk,mob}.png` (HEAD version, before), `shots/post_404_{desk,mob}.png` (after), review sheet `qa_404_desk_pre_post.png`.
- Keyboard focus: first Tab lands on "Go home". Computed focus shadow before `rgb(197,160,89)` (gold), after `rgb(37,39,41)` 2px at both 1280px and 390px. Viewport captures: `shots/post_404_*_focus_viewport.png`.
- Limits: AR/RTL layout not captured. Backend not needed for this page.

## Legal pages — evidence (LegalViews: Privacy, Terms, GDPR)

- Status: IMPLEMENTED, not PASS. Colour pass applied to the shared `LegalViews` file. Tab focus is verified (settled gold indicator). Not PASS yet: AR/RTL and the full long-form content were not reviewed.
- Changes: hero navy-to-black gradient with gold chip → `brand-charcoal` panel with white text (white on charcoal 14.99:1). Active tab navy → charcoal. Inactive tabs slate border and text → `brand-field` boundary and `brand-muted` text, charcoal hover. Article headings navy → charcoal. Body, list, and table text slate-600 → `brand-muted`. Table headers slate-400 (about 2.5:1 on white, fails AA) → `brand-muted`. Code chips → `brand-wash`. Contact link → charcoal underlined. Neutral slate dividers and borders kept.
- Tests: `views/legal/__tests__/legalBrand.contract.test.tsx` (4 contracts). Related suites (legal routes, accessibility RTL, i18n parity): 4 files, 75 tests pass.
- Captures: `shots/pre_legal_{privacy,terms,gdpr}_{desk,mob}.png` (HEAD, before) and `shots/post_legal_*` (after). No page errors in either run.
- Tab focus, resolved (not a defect): the focused tab's outline reads white for about 150ms, then settles at `rgb(163,126,68)` (`#A37E44`, the global `--confit-focus` token, 3.73:1 on white, non-text). The cause was `transition-all` on the tab class animating `outline-color` from `currentColor`. Evidence: `focus_settle.mjs` reads immediately (white) and after 600ms (gold); crop `shots/qa_legal_tab_settled_crop.png` shows the gold ring around the active "Privacy Policy" tab. No tab-specific focus classes were added.
- Lesson recorded: measure focus styles after transitions settle. Immediate reads of `outline-color` on `transition-all` elements are unreliable.

- Limits: AR/RTL not captured. Long-form article content not reviewed beyond the first section.

## Register system — open decision

- Changed in the navigation-rule pass (directed by the brief): the editorial register accent, which draws the 3px rule under the header on every editorial page (`/`, `/discover`, `/stylist`, `/products`, unknown routes), is now brand charcoal `#252729` (was gold `#C9A227`, 2.30:1, decorative only). The register test now requires every accent to clear 3:1.
- Still open (design-system decision, not changed): editorial ink `#6B4F1E` (text-grade eyebrow colour), commerce ink and accent `#1B1F3B`, and the other register accents and inks (atelier, fit, account, partner, admin). Each still affects its own surface family.

## Known pre-existing issues (not caused by this migration)

- Backend API is not running in the sandbox; pages show 502 responses for data calls. Visual checks cover layout only; data-driven states need a running backend.
- `origin/main` was merged into this branch at `412c341` (no conflicts). Re-check `behind` status before any merge.
- `npm run build` prints a rolldown plugin-timing notice (`vite:css-post`). It is informational and exits 0.
