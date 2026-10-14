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
| `/looks/:token` | SharedLookView | IMPLEMENTED (White-first layout, brand charcoal headers/CTA, brand-wash and hairline accents; contract tested `sharedLookBrand.contract.test.tsx`) |
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
| `/product/:slug`, `/products/:slug` | ProductDetailView | IMPLEMENTED, not PASS. Light scheme. Navy, gold, cream, and slate chrome mapped to charcoal, brand-wash, and brand-muted; sale badge charcoal; savings line emerald (semantic). Primary CTA and sticky CTA focus ring charcoal (global gold ring was the settled focus). Rose, amber, and emerald status kept. Mobile and AR captured; AR/mobile not yet visually reviewed. See Product detail evidence. |
| `/builder`, `/outfits/:id` | OutfitBuilderView | IMPLEMENTED (Gold/navy/cream chrome to brand charcoal/wash; focus ring to charcoal; all 26 behavioral & axe tests pass; contract tested `outfitBuilderBrand.contract.test.tsx`) |
| `/outfits`, `/my-looks` | MyLooksView | IMPLEMENTED, not PASS. Light scheme. Gold CTA to charcoal; navy, slate chrome mapped; `TryOnButton` (shared) mapped to charcoal and white. Amber partial-look and missing-slot status and rose delete kept. "1 pieces" bug fixed with CLDR plurals (EN, AR). Charcoal focus ring on CTAs. AR/mobile captured; not yet visually reviewed for AR. See My Looks evidence. |
| `/tryon-studio`, `/try-on`, `/try-on/:sessionId`, `/visual-search` | TryOnFitView (error boundary) | IMPLEMENTED (Navy/gold hero and cards to brand charcoal/wash; contract tested `tryOnBrand.contract.test.tsx`) |
| `/fit`, `/fit-finder` | FitFinderView | IMPLEMENTED (Navy hero to brand charcoal; gold accents to charcoal; all 8 engine & localization tests pass; contract tested `fitFinderBrand.contract.test.tsx`) |
| `/wardrobe`, `/wardrobe/item/:id` | WardrobeView | IMPLEMENTED (Navy/gold chrome to brand charcoal and wash; all 9 action state tests pass; contract tested `wardrobeBrand.contract.test.tsx`) |
| `/cart`, `/checkout` | CheckoutView | IMPLEMENTED, not PASS. Gold, navy, cream and slate mapped to brand tokens; semantic colours kept; dark-filled controls use `.focus-on-light-fill` (charcoal ring, offset 3px). OPEN: fixed AI Stylist control covers Subtotal/Tax amounts at 1024-1280 in the first fold. Padding reserve tried and reverted (did not clear 1024). Backend-dependent flows unverified. See Checkout section. |
| `/orders`, `/orders/:orderNumber`, `/returns` | OrderTrackingView | IMPLEMENTED, not PASS. Light scheme. Gold and navy chrome to charcoal and brand neutrals; return CTA focus ring charcoal. Fixed state bugs: 5xx no longer shows the verify form; signed-in 404 no longer shows the guest prompt; `/orders` lists the signed-in customer's orders; hard-coded English copy moved to `order.*` keys (EN and AR). `/returns` renders the same view and is not captured separately. See Orders evidence. |
| `/profile`, `/settings`, `/notifications` | UserProfileView | IMPLEMENTED (Gold/cream/navy styling to brand charcoal and wash; contract tested `userProfileBrand.contract.test.tsx`) |

## Brand (partner) routes — `/b2b` and `/partner`

| Route | Component | Status |
|---|---|---|
| `/b2b`, `/partner`, `/partner/dashboard` | BrandDashboardView | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `brandViewsBrand.contract.test.tsx`) |
| `/b2b/catalog`, `/partner/catalog` | BrandCatalogView | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `brandViewsBrand.contract.test.tsx`) |
| `/b2b/inventory`, `/partner/inventory` | BrandInventoryView | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `brandViewsBrand.contract.test.tsx`) |
| `/b2b/orders`, `/partner/orders` | BrandOrdersView | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `brandViewsBrand.contract.test.tsx`) |
| `/b2b/analytics`, `/partner/analytics` | BrandAnalyticsView (lazy) | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `brandViewsBrand.contract.test.tsx`) |
| `/b2b/placements`, `/partner/placements` | BrandPlacementsView | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `brandViewsBrand.contract.test.tsx`) |
| Partner gateway / lead form | PartnerGatewayView, LeadForm | IMPLEMENTED (RoleGuard fallback; mapped to brand charcoal/wash; 25 axe and functional tests pass; contract tested `brandViewsBrand.contract.test.tsx`) |

## Admin routes — `/admin`

| Route | Component | Status |
|---|---|---|
| `/admin`, `/admin/overview`, `/admin/analytics` | AdminAnalyticsView (lazy) | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `adminViewsBrand.contract.test.tsx`) |
| `/admin/catalog`, `/admin/partners` | AdminCatalogView | IMPLEMENTED (Mapped to brand charcoal/wash; contract tested `adminViewsBrand.contract.test.tsx`) |
| `/admin/audit` | AdminAuditView | IMPLEMENTED (Terminal high-contrast dark table; white focus rings; contract tested `adminViewsBrand.contract.test.tsx`) |

## Global shells and components

| Surface | Status |
|---|---|
| `ConsumerLayout`, `ConsumerNavbar` (header, nav, footer), `TrustFooter` | IMPLEMENTED, not PASS. Shared by every consumer page. White page root; light utility strip; charcoal Sign In and avatar; white AI Stylist pill with charcoal icon chip; light footer with charcoal headings and muted links; semantic emerald status kept in TrustFooter. Still legacy: the gold-dark focus token `--confit-focus` (#A37E44, 3.73:1 on white, pinned by `surfaceSystem.test.tsx`) and the register palette in `design/registers.ts` (commerce ink #1B1F3B, editorial ink #6B4F1E, other register accents). The editorial accent (navigation rule under the header) is now charcoal. See Shell evidence |
| `BrandLayout`, `BrandNavbar`, `BrandSidebar` | IMPLEMENTED (Light footer, white focus rings, brand coral active marker, white portal title; 37 tests pass in `brandSidebar.test.tsx` and `brandSidebarMotion.test.tsx`) |
| `AuthModal` (login, register, MFA, recovery) | PASS |

`AuthModal` evidence: white banner with the official mark (theme `dark`), charcoal primary action, charcoal underlined links (gold `#C5A059` was 2.46:1 on white), field border `#8A8D93` (3.33:1, WCAG 1.4.11), legacy navy/gold/cream and `backdrop-blur` removed. Logic, routes, and API calls unchanged.
- Checks run: `tsc` 0; focused auth suites 12 files passed; `authModal.brand.test.tsx` 7/7; full vitest 106 files / 1371 tests passed; `npm run build` 0.
- Screenshots reviewed (sandbox at `/home/user/brand_build/shots/`): `before_*` vs `after_*` for sign-in, sign-up, forgot, focus, error, loading, mobile (390px), and Arabic RTL (`after_rtl_mob.png`, `dir=rtl` confirmed).
- Limits: the MFA step, the forgot "sent" and "unconfigured" states, and data-backed success states were not captured because the backend is not running. ESLint is not configured for this repo (`eslint` fails before linting), so lint was not run.
| `AuthPageShell` (email-landing card shell, used only by the three account pages above) | PASS | White page, hairline card. Verified through the three pages' checks below |
| `RoleGuard` (logo on guard/denial screens) | IMPLEMENTED (White-first auth required and restricted cards, brand charcoal buttons, brand wash icon chips; contract tested in `roleGuardBrand.contract.test.tsx`) |
| `ShareCard` (shared look image text) | IMPLEMENTED (White card, brand charcoal typography, hairline divider, brand wash chips; contract tested in `sharedLookBrand.contract.test.tsx`) |
| Shared UI primitives (buttons, inputs, tables, cards, modals, toasts) | IMPLEMENTED (AccessiblePrimitives, CommonComponents, SectionHeader, SkipLink, StateComponents, AnnouncementBar, CollectionRail, VirtualStylistDrawer, CartDrawer, DuplicateAlertModal migrated to brand-charcoal, brand-wash, and hairline tokens; contract tested primitivesBrand.contract.test.tsx) |

## Emails, reports and exports

| Surface | Source | Status |
|---|---|---|
| Email shell and logo (`logo_url()`, header colours) | `backend/app/services/email_templates.py`, `frontend/public/email/confit-logo.png` | PASS (`confit-logo.png` replaced with official Logo #3 mark 160x160 RGBA on white; `email_templates.py` uses hosted logo) |
| Transactional templates (order, payment failed, shipping, saved look, outfit ready, fit result, price drop, partner approval, admin alert, newsletter) | `email_templates.py` | IMPLEMENTED (10 transactional templates render with official Logo #3 hosted asset; contrast verified and tested) |
| Brand/admin PDF report | `backend/app/services/brand_report_pdf.py` (`draw_logo`, navy/gold header) | IMPLEMENTED (`draw_logo` vector rewritten to official Logo #3 100x100 4 quadrants; charcoal palette; hairline rules) |
| CSV exports | brand/admin controllers | PASS (Data contracts verified intact and untouched) |

## Account pages — evidence (VerifyEmail, ResetPassword, EmailUnsubscribe)

- Shared change: `AuthPageShell` page background cream `#FAF9F6` → white; card hairline. Shared auth field/button styles from the AuthModal pass.
- Per-page changes: cream icon chips → `brand-wash`; navy headings → charcoal; gold-dark `#A37E44` icons and links → charcoal; gold focus ring → charcoal; secondary text → `brand-muted`; links charcoal and underlined by default (`#A37E44` on white is 3.73:1, below 4.5:1 for text). Semantic emerald success, rose error, and amber warning (decorative `StatusIcon`) kept.
- Tests: `accountRecovery.brand.test.tsx` (7 source-level brand contracts). Existing `accountRecoveryPages.test.tsx` (15 behaviour and axe tests) unchanged and passing. Together: 22/22.
- Browser captures in sandbox at `/home/user/brand_build/shots/`: `pre_*` (committed state before this pass) and `post_*` (after), desktop 1280px, mobile 390px, AR/RTL on mobile.
- Keyboard: a real Tab press on VerifyEmail focuses the primary button with `:focus-visible` and a charcoal ring (`post_ve_focus_kbd_desk.png`). ResetPassword input focus ring checked (`post_rp_focus_desk.png`).
- API states are MOCKED in the browser (Playwright route fixtures), labelled `_mocked`. The backend is not running in the sandbox. Request counts were recorded to confirm the mocked calls fired.
- Error copy FIXED in this pass (was a pre-existing finding). The backend answers an invalid, used, or expired verification or reset link with `401 AUTH_FAILED`. The shared mapping in `apiErrors.ts` (`errors.auth_failed`, "Your session has expired") was shown instead, and the API client treated the 401 as a session expiry. Effects before the fix: one `/auth/refresh` call, the sign-in dialog opened over the page, and wrong copy. Fix: `VerifyEmailView` and `ResetPasswordView` map `AUTH_FAILED` to their own `link_invalid` copy (EN and AR), with the shared helper unchanged for every other code. `apiClient.ts` excludes `/auth/verify-email` from session renewal and keeps its server message. Tests: `apiClient.linkRedemption.test.ts` (fails on the old client, passes now); `accountRecoveryPages.test.tsx` asserts the exact copy for both pages.
- Evidence (mocked, `_mocked`): `/home/user/brand_build/shots/pre_link_*` (HEAD build) and `post_link_*` (this change), for `verify-email` and `reset-password` in EN and AR, from `link_error_states.mjs`. Pre: refresh calls 1, dialogs 1, session copy. Post: refresh calls 0, dialogs 0, link copy. Also `pre_ve_*` and `post_ve_*`.

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
- CI regression found and fixed: the `stylist drawer browser gate` FAILED on `d13a5d4` and `0226df3`. Cause: the gate probes looked up the AI Stylist button by its old accessible name (`layout.open_ai_stylist`), which the label-in-name fix had replaced. Fix: both probes (`stylist_drawer_a11y_probe.mjs`, `stylist_drawer_keyboard_probe.mjs`) now use `layout.ai_stylist_director`, the visible label. Local gate (`GATE_PORT=43140 bash scripts/stylist_browser_gate.sh`, after `npm run build`): PASS, 3 of 3 runs, EN and AR. Axe: 0 serious/critical, 0 colour-contrast.
- Switcher pass (this change): `LanguageSwitcher` active pill navy `#1B1F3B` → `brand-charcoal` (white text); hover `#FDF8EE`/`#7A5C28` → `brand-wash`/`brand-charcoal`. `CurrencySwitcher` hover and focus ring `#7A5C28` → `brand-wash`/`brand-charcoal`. Before/after: `brand_build/shots/pre_desk_lang.png`, `pre_desk_currency_focus.png`, `post_desk_fold.png`, `post_desk_currency_focus.png`. `LanguageSwitcher` is also imported by `BrandNavbar`, so the partner shell header picks up the same active-pill colour; that surface is NOT_STARTED and is not marked PASS by this change. Tests: `switcherBrand.brand.test.tsx` (4 contracts). Full vitest 118 files / 1469 tests passed; `tsc --noEmit` exit 0; `npm run build` exit 0.
- Focus token migration (this pass, commit pending push): the global `--confit-focus` moves from gold-dark `#A37E44` to brand charcoal `#252729` (14.99:1 on white). Outline-only contract kept (no `box-shadow`). Dark surfaces opt in with `.focus-on-dark` (white outline, offset −6px so it sits inside the photo). Applied to Home occasion cards (dark photo overlays). Measured: charcoal and white rings both computed `:focus-visible`; occasion card and Sign In captured in `brand_build/shots/post2_*`. Tests: `focusToken.brand.test.tsx` (8), `surfaceSystem.test.tsx` (updated pin).
- Found and fixed in the same pass: charcoal Sign In buttons used a charcoal focus ring on a charcoal fill, so the ring was invisible. Added `focus-visible:ring-offset-2 focus-visible:ring-offset-white` to the navbar Sign In and the mobile drawer Sign In (plus one account-menu portal link). Captured as `post2_focus_signin_desk.png`: white gap, charcoal ring.
- Still open: hard-coded `focus-visible:ring-[#A37E44]` and `ring-[#C5A059]` in page and component files (for example `Field.tsx`, `CommonComponents.tsx`, `AccessibleCarousel.tsx`, `circular-gallery.tsx`, `PartnerGatewayView.tsx`, `EmailPreferencesSection.tsx`). These are legacy gold rings. Each is fixed in its own page or component pass, not in this one.
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

## Product detail — evidence (ProductDetailView, light scheme)

- Changes: legacy class mapping in `ProductDetailView.tsx` (code only; the swatch `color_hex` data and the semantic rose, amber, and emerald colours are unchanged). Overlay Try On moved from the dark glass to light glass. Secondary Try On moved from cream and gold to white with a charcoal hover. Map link underlined charcoal.
- Focus: the primary CTA and the mobile sticky CTA read the global `:focus-visible` outline (gold `rgb(163,126,68)`, settled). Both now add `focus-visible:outline-brand-charcoal`, settled `rgb(37,39,41)`. Measured with `product_detail_capture.mjs`, reading 700ms after focus so the `transition-all` has settled. Earlier immediate readings were transition artefacts, not the real ring.
- Tests: `productDetailBrand.contract.test.tsx` (6 source-level contracts; fails 5 of 5 on the HEAD view before the fix). Existing `productDetailContract.test.tsx` unchanged and passing. Together 35/35 at the time of the change.
- Checks: `tsc` 0; full Vitest 114 files, 1423 tests passed; `npm run build` 0.
- Captures (`/home/user/brand_build/shots/`): `pre_product_*` (HEAD build, port 43131) and `post_product_*` (this change). Desktop, mobile 390px, and AR/RTL mobile, plus the not-found and error states.
- API states are MOCKED (Playwright routes) and labelled `_mocked`: the product payload, a 404, and a 500. Backend not running. Image hosts are replaced by a neutral placeholder. Captures recorded no page errors.
- Limits: not yet reviewed visually for AR and mobile. The overall Try On overlay, wardrobe-linked, and BOPIS live states are not covered by these captures.

## My Looks — evidence (MyLooksView, TryOnButton shared primitive)

- Route: `/my-looks` (and `/outfits`) under `ProtectedRoute`. Session simulated with `confit_user` and a mocked `/auth/me` (user has `has_profile: true`). Saved-looks API MOCKED (`_mocked`). The backend is not running; other `/api/v1` calls return `[]` through a catch-all route.
- Changes: `MyLooksView.tsx` and `components/product/TryOnButton.tsx` (shared; also used on ProductCard). Navy and gold to charcoal and brand neutrals. Semantic amber and rose kept.
- Bug fixed: the item count read "1 pieces". `my_looks.pieces` is now a CLDR plural in EN (`one`/`other`) and AR (`one`/`two`/`few`/`many`/`other`). The i18n parity test now treats plural variants as one logical key, and it still requires exact keys otherwise. A runtime test covers EN 1/2 and AR 1/2/5.
- Focus: "Build a new look" settled focus measured 700ms after a keyboard focus: pre gold `rgb(163,126,68)`, post charcoal `rgb(37,39,41)`.
- Tests: `myLooksBrand.contract.test.tsx` (7 tests). Source contracts fail 4 of 4 on the HEAD view and shared primitive. Existing `useMyLooksViewModel.test.tsx`, `tryOnGateCoverage.test.tsx` unchanged and passing.
- Checks: `tsc` 0; full Vitest 115 files, 1430 tests passed; `npm run build` 0.
- Captures (`/home/user/brand_build/shots/`): `pre_mylooks_*` and `post_mylooks_*` for populated (desktop, mobile, AR mobile), empty, and error states, plus `*_mylooks_cta_focus_mocked.png`. Captures recorded no page errors.
- Limits: AR and mobile not yet reviewed visually. The Try On pills are shared with other pages and were checked only on this page.
- CI: the first push (`e46d38f`) failed the `frontend` job at `npm run i18n:check`. The gate treated the Arabic plural forms as drift and rejected the bare `t('my_looks.pieces')`. It was reproduced locally and fixed in `frontend/scripts/check_i18n.mjs`, which now uses the same CLDR rule as the parity test. Negative probe: a missing key still fails with exit 1. `npm audit --omit=dev --audit-level=high`: 0 vulnerabilities.

## Orders — evidence (OrderTrackingView, `/orders`, `/orders/:orderNumber`, `/returns`)

- Routes: `/orders/:orderNumber` is public. `/orders` and `/returns` are under `ProtectedRoute`. `/returns` renders the same view, so for a signed-in customer with no order number it shows the order list. It is not captured separately.
- Session simulated with `confit_user` and a mocked `/auth/me` (user has `has_profile: true`). Commerce API MOCKED (`_mocked`): `GET /commerce/orders/:n`, `/tracking`, and `GET /commerce/orders`. Fixture: order `CF-240918-0042` (items 1 and 2, timeline of 4 steps, current `shipped`). A 404 state uses `CF-000000-0000`. The backend is not running, so the states are not PASS evidence against live data.
- Changes in `OrderTrackingView.tsx`:
  - Server faults (5xx or network status 0) show `order.load_failed` with `order.load_failed_title` and a Retry action. They never show the guest verify form. Status is checked before message text, so a 5xx whose body says "Order not found" is still a load failure.
  - Signed-in 404 shows `order.not_found` with `order.not_found_desc` and no guest prompt. Anonymous 404 keeps the neutral verify prompt (anti-enumeration).
  - Signed-in 403 shows `order.access_denied`. Backend English text is no longer rendered in the UI, in either locale.
  - Signed-in `/orders` lists the customer's orders through `commerceService.getOrders()`. Each row links to `/orders/:order_number`. A list error has Retry. An empty list has its own copy. Anonymous `/orders` shows `order.no_number`, with no API call.
  - Dates use the app language through `formatDate` and `formatDateTime`. They previously used the browser locale.
  - Palette: `slate-*`, navy, and gold mapped to brand tokens. The current step, pickup panel, and status pill use charcoal or wash, not gold. The return CTA focus ring is `focus-visible:outline-brand-charcoal`.
- Locale keys: 13 new `order.*` keys in `en.json` and `ar.json`, all with Arabic script in AR. `npm run i18n:check` passes.
- Focus: return CTA settled focus measured 700ms after keyboard focus. Pre gold `rgb(163,126,68)` → post charcoal `rgb(37,39,41)`.
- Tests:
  - `orderTrackingBrand.contract.test.tsx`: source contracts for palette, focus ring, no hard-coded English, server-fault ordering, locale-aware dates, list link, and EN/AR keys.
  - `orderTrackingStates.test.tsx`: runtime states for anonymous 500 (Retry, no verify), anonymous 404 (verify kept), signed-in 404, 403, 500, 5xx-with-"not found" text, Retry reloads, list, list error and retry, empty list, anonymous `/orders`, and AR load-failed copy.
  - Result: 35 tests pass. `tsc` 0. Full Vitest 117 files, 1465 tests passed. `npm run i18n:check` 0. `npm run build` 0.
- Captures (`/home/user/brand_build/shots/`): `pre_orders_*` and `post_orders_*` for detail OK (desktop, mobile, AR mobile), 404, 500, and list, plus `cta_focus` in the capture log. All recorded no page errors.
- Before and after:
  - Pre: the 500 state showed "Verify your order". The cause was the message-text heuristic in the signed-in branch, since the mock's 500 body said "Order not found". Anonymous 500 also showed the verify form because the anonymous branch caught every failure. Both paths are now covered (signed-in capture, anonymous runtime test).
  - Pre: the 404 state showed the verify form to a signed-in user. Post: "Order not found" with no guest prompt.
  - Pre: `/orders` with no number showed "No order number was provided." Post: the signed-in order list.
  - Pre: English copy on the AR page (eyebrow, description, loading, not-found text). Post: localized.
- Limits, not PASS:
  - Timeline step titles and descriptions, and the item names, come from the backend, so they stay English on the AR page.
  - The Arabic mobile capture shows the step titles in English for this reason.
  - The AI Stylist pill sits close to the card edge on desktop and overlaps the Try On overlay at 390px. This is the shared shell and remains open.
  - `/returns` is not captured separately.
  - The pre-captures were taken before the fixture gained `status` and `total_amount`, and before the mock's 500 body was corrected. The post-captures use the corrected fixtures.

## Focus-ring sweep and Discover re-check (rollout 2)

- Defect class: a charcoal focus ring on a charcoal- or navy-filled control merges into the fill and is invisible. Fix: `focus-visible:ring-offset-2 focus-visible:ring-offset-white` on every such control, and legacy gold rings (`ring-[#A37E44]`, `ring-[#C5A059]`) switched to `ring-brand-charcoal`. Done by a repository sweep of 11 files and 16 class strings: `DiscoverView`, `NotFoundView`, `SharedLookView`, `TryOnFitView`, `PartnerGatewayView`, `BrandCatalogView`, `BrandDashboardView`, `LeadForm`, `CommonComponents`, `CameraScanModal`, `TryOnStudioErrorBoundary`. Class strings only; no logic change.
- Evidence: selected Discover chip "All Categories", before `brand_build/shots/pre_chipsel_focus.png` (no visible ring), after `post_chipsel_focus.png` (white gap, charcoal ring). Sign In after: `post2_focus_signin_desk.png`.
- Tests: `tsc --noEmit` exit 0; `npm run build` exit 0; `vitest run` 119 files / 1477 tests passed.
- Discover status: IMPLEMENTED, not PASS. Verified: desktop and mobile fold, AR fold captured, selected-chip focus. NOT verified: product rails (no backend in the sandbox, so no data-backed states), loading and empty states with data, filters and search with live data, full-page mobile review.
- Known, shared, not changed here: the floating AI Stylist pill covers carousel content on mobile (390px). It is a fixed control by design and stays open in the shell row.
- Still legacy in other files (not in this sweep): navy `#1B1F3B` and `#0C0E1E` fills in `CameraScanModal` hover and several b2b pages. Each is fixed in its page pass.

## Mobile AI Stylist overlap and shared showcase tokens (rollout 2, pass 2)

**Measured defect (before).** Discover at 390x844: the FAB is a 66x50 pill at (300,714). Its rectangle overlaps 8 visible elements: the carousel card images and captions "Evening Silk", "Minimal Capsule", and "Quiet luxury essentials built for repeat". At 1280x800 it overlaps 0. Method: `brand_build/fabmeasure.mjs` (element rectangle intersection, same build).

**Change.** `ConsumerLayout`: the mobile control is a 48px icon-only circle (`h-12 w-12`; the pill returns at `sm`), keeps `aria-label`, and anchors with `stylist-fab-anchor` at `bottom-4` (desktop `bottom-8`). `index.css`: the `.stylist-fab-anchor` rules, plus `body:has([data-sticky-cta]) .stylist-fab-anchor { bottom: 5rem }` below 1024px, so the PDP sticky CTA is still cleared. `ProductDetailView`: sticky bar marked `data-sticky-cta`.

**Measured (after, same method).** 390x844: 48x48 at (326,780), 6 overlapping elements, down from 8 and from 66x50. The overlaps are the back cards of the Discover mood stack, and they remain. 1280x800: 0 overlaps.

**Status: PARTIALLY MITIGATED, not fixed.** A fixed bottom control in the first mobile fold of a carousel cannot clear the carousel's back-card captions without one of the following: hiding the control on scroll, moving it, or changing the carousel layout. The brief rules out hiding and moving. Decision needed from the owner (see the PR).

- Tried and reverted: a shorter mobile stack height (`h-[430px] sm:h-[540px]` on the non-compact variant). Discover already uses the compact `h-[430px]`, so it had no effect there, and it would have changed Home, Orders, and Admin without evidence.

**Shared component: `DesignShowcases.tsx`.** Legacy gold, cream, navy, and slate tokens are now brand tokens, with no legacy tokens left in the file. Gold blur blobs became lilac and mint at low opacity. Focus ring is charcoal. Consumers: `CardStackShowcase` is used by Home, Discover, Order tracking, and Admin analytics. `CircularGalleryShowcase` is used by Profile and Try-on. **None of these pages is marked PASS by this change.**

**Tests.** `fabLayout.brand.test.tsx` (5 source contracts). `shellBrand.brand.test.tsx`: 2 contracts updated to the new classes, same intent (logical end placement, white pill). `tsc --noEmit` exit 0. `npm run build` exit 0. `vitest run`: 120 files, 1482 tests passed.

**Discover status.** Still IMPLEMENTED, not PASS. The showcase tokens above were missed in the earlier Discover pass and are now fixed. Backend-dependent rails and states remain unverified.

## Mood-stack mobile composition fix (rollout 2, pass 3, option 2)

**Measured source.** The earlier 48px icon-only FAB (`cab56d0`) still overlapped the Discover mood stack at 390px: the lower-right back-card captions and the active card's "Open" link. The collision was in the stack's own layout (the card layer is `absolute bottom-0`, so padding on its parent does not move it), not in the FAB size.

**Change (smallest that fixes the measured collision).** `CardStack` (`ui/card-stack.tsx`) gains two opt-in props, `stageClassName` (card layer) and `controlsClassName` (controls row). Defaults add no classes, so other consumers are unchanged. `CardStackShowcase` passes:
- `stageClassName="!bottom-28 sm:!bottom-16 lg:!bottom-0"`: raises the cards by 112px below sm, 64px at sm–lg, and restores the desktop position at lg.
- `controlsClassName="mt-8 sm:mt-4 sm:pe-28 lg:mt-4 lg:pe-0"`: below sm the controls row moves below the FAB's band (no horizontal reserve, because four controls plus dots do not fit beside the 48px FAB in a 310px card; a horizontal reserve clipped the previous-slide button). At sm–lg, where the 189px pill is wider, the row keeps a horizontal end reserve.

**Browser measurement (Discover, `fab2.mjs`, FAB rect vs. meaningful text and controls; decorative image edges counted separately).**

| Viewport | Before (cab56d0) text / control hits | After text / control hits |
|---|---|---|
| 320x844 | 5 / 0 | 0 / 0 (1 decorative image edge) |
| 360x844 | 3 / 1 | 0 / 0 |
| 390x844 | 3 / 1 | 0 / 0 |
| 414x844 | 3 / 1 | 0 / 0 |
| 640x844 | not measured | 0 / 0 |
| 768x844 | 1 / 0 | 0 / 0 |
| 390x800 | not measured | 0 / 0 |
| 640x800 | not measured | 0 / 0 |
| 768x800 | 3 / 0 | 0 / 0 |
| 320x800 | not measured | **3 / 0 (open: caption overlap at 320 wide x 800 tall)** |
| 1024x800, 1280x800 | 0 / 0 | 0 / 0 (desktop unchanged) |
| 1024x844, 1280x844 | 0 / 2 ("Search by Photo" button, pre-existing) | 0 / 2 (unchanged, not from this change) |

Screenshots (`brand_build/shots/`): `cab56d0_390.png` (before), `fix8_390.png` (after), `fix8h_*` (800-tall), `fix8d_1280.png` (desktop 800), `fix8d844_1280.png`.

**Status.** PARTIALLY RESOLVED. Zero overlap with text or controls at 360–768 at both heights measured, and at 320–414 x 844. Open: (1) 320x800 caption overlap; (2) Discover "Search by Photo" at 1024–1280 x 844 (pre-existing, Discover header, needs a design decision); (3) the scroll-dependent overlap of the fixed control with any content it scrolls over, which is inherent to a fixed control.

**Other consumers of the shared component.** `CardStackShowcase` is used by Home, Discover, Order tracking, and Admin analytics. The layout change applies to all four. Measured only Discover and `/` with `/orders` and `/profile` in the first fold. Home's text overlaps ("Photo optional for fit checks", "Privacy details before uploads") and Try-on's gallery credit ("Photo: Tamara Bellis") are **identical on the pre-change build**, so they are pre-existing route-level collisions, not caused by this change. They belong to those routes' reviews. Circular-gallery consumers (Profile, Try-on) use a different component and were not changed.

**Tests.** `src/components/__tests__/mobileStackReserve.brand.test.tsx` (5 tests): source contract for both reserves; `CardStack` applies the opt-in classes; the no-prop default is unchanged; prev, next, and open-link controls keep accessible names. `tsc --noEmit` exit 0. `npm run build` exit 0. `vitest run`: 121 files, 1487 tests passed.

**Status of affected pages.** Discover: IMPLEMENTED (not PASS). Home, Order tracking, Admin analytics: not PASS, not reviewed for this change. Try-on: not PASS.

## Discover mobile-fold fix: final measurements (rollout 2, pass 3, follow-up)

Supersedes the "Mood-stack mobile composition fix" numbers above where they differ. The layout change itself is in `6eb12b7`. Browser measurements are on the built `6eb12b7` tree.

- **Discover, 390x844.** Text/control hits 0/0, one decorative image edge. Screenshot `brand_build/shots/fix8_390.png`. Before: `cab56d0_390.png`.
- **320x844, 360x844, 414x844, 640x844, 768x844.** 0/0 at every width.
- **390x800, 640x800, 768x800.** 0/0.
- **320x800.** 3 caption hits, **still open**.
- **1024x800, 1280x800.** 0/0, unchanged from baseline.
- **1024x844, 1280x844.** "Search by Photo" button overlapped (2 control hits). **Identical on the baseline, pre-existing, not caused by this change, still open.** It is in the Discover header, not the stack.

**Other routes measured with the same method (390x844), not PASS.** `/` (Home): "Photo optional for fit checks" and "Privacy details before uploads" overlap, identical on the baseline. `/try-on`: "Photo: Tamara Bellis" gallery credit overlaps, identical on the baseline. `/orders` and `/profile`: 0 hits in the first fold.

**Regression found and fixed during this pass.** Centering the controls row inside a 64px end reserve clipped the previous-slide button at 390px. Final rule: below sm the controls row moves below the FAB band (`mt-8`), and the horizontal reserve applies only at sm–lg.

**Tests.** `src/components/__tests__/mobileStackReserve.brand.test.tsx` (5). `tsc --noEmit` 0. `vite build` 0. `vitest run`: 122 files, 1492 tests passed (including Checkout below).

**Hook and secret scan.** The pre-commit hook was **missing** from this restored clone when `6eb12b7` was committed, so that commit ran without the hook. I then ran `pre-commit install` (executable, `.git/hooks/pre-commit`) and ran gitleaks manually: `pre-commit run gitleaks --all-files` exit 0, and `--from-ref HEAD~1 --to-ref HEAD` exit 0 (Passed). The hook is now installed for later commits.

## Checkout (`/checkout`): first consumer route after the shared layout fix

**Status: IMPLEMENTED, not PASS.** Backend-dependent flows are unverified: payment methods (the page says they "could not be loaded" in this environment), cart with items, order placement, promo validation, and the loading and error states from live APIs.

**Changes (`CheckoutView.tsx`, brand tokens only, semantics kept).**
- Gold `#C5A059`, `#A37E44` text and rings, navy `#1B1F3B` and `#0C0E1E` fills, and cream `#FDF8EE`/`#FAF9F6` surfaces were moved to brand charcoal, wash, and field.
- Input and option borders (`border-slate-200`) moved to `brand-field` (3.33:1, control boundary). Dividers and card containers moved to `brand-hairline`.
- Inputs' gold focus border moved to charcoal.
- Icons that sat on white or wash use charcoal. The icon on the charcoal badge and on the charcoal CTA is white.
- Semantic emerald, amber, and rose are unchanged. The field error and promo error keep `role="alert"`.

**Focus treatment (finding).** The shared `.focus-on-dark` class draws a white ring. On the off-white wash card that ring is about 1.08:1, so it is not a usable focus indicator on light surfaces. I added `.focus-on-light-fill` (charcoal 2px ring, 3px outside the control, about 13.9:1 against the wash) and applied it to the four dark-filled Checkout controls. The shared `.focus-on-dark` is unchanged, so photo overlays are unaffected. Checkout buttons use `transition-all`, so focus must be measured after about 450ms. Screenshots taken at focus time show a transition frame.

**Browser evidence.** Before: `brand_build/shots/ckout_before_390.png`, `ckout_before_1280.png`. After: `ckout_after_390.png`, `ckout_after_1280.png`. Focus crop: `ckout_after3_390_focus.png` (settled: charcoal outline, offset 3px, on the card).

**Tests.** `src/views/__tests__/checkoutBrand.brand.test.tsx` (5 contracts): no legacy tokens; semantic colours kept; dark-filled controls use `focus-on-light-fill`; the new ring is charcoal, offset 3px, no white and no box-shadow; error alerts kept. `checkoutActionStates.test.tsx` (9) still passes.

**Limitations.** **Open at desktop 1280x800: the fixed AI Stylist control (1067,718, 189x50) covers the right-hand Subtotal and Tax amounts in the Order summary card in the first fold.** This is the same fixed-control collision class as Discover; it needs a Checkout-specific decision (for example, a summary-aware offset at lg, or scroll-hide) and is not fixed in this commit. Checkout is therefore NOT PASS. The empty-cart state is what this environment shows. Keyboard focus was verified on the guest "Sign In" button only. Checkout's loading, error, and empty-payment states are not browser-verified.

### Checkout: summary collision attempt (reverted)

Tried an `lg:pe-20` reserve inside the Order summary card. Browser result: the amounts still overlap the fixed control at 1280x800 (`$0.00` at x 1035–1071 against control x 1067) and at 1024 (control x 811–1000, amounts x 875–911). A padding reserve cannot clear 1024 without distorting the card. Reverted; the file is at `e6330f8`. **Decision needed:** accept the first-fold overlap, or choose a Checkout-specific layout (e.g. move the summary totals above the fold band), before this route can be PASS.

## Checkout: Order summary reflow (decision: fix, not accept)

**Cause.** The summary column sat at y 556–929 in the first fold. Its Subtotal, Tax, Shipping, Total, and Place order rows (y 731–904) lie inside the fixed AI Stylist footprint (y 762–812 at 844 high; 718–768 at 800 high; x 811–1000 at 1024, x 1067–1256 at 1280). Inline padding cannot fix this, because the rows are full-width blocks. Earlier `lg:pe-20` was reverted.

**Fix (lg only).** The outer wrapper becomes a 12-column grid at lg. The header (demo banner, title, guest card) takes columns 1–7. The `<form>` becomes `lg:contents`, so the Order summary takes columns 8–12 at row 1, spanning rows 1–3. The fulfillment form stays in columns 1–7 below the header. Mobile (below lg) is unchanged, and the form is the same element, so the submit button stays inside it.

**Measured (browser, `co_geom.mjs`).**

| Viewport | Summary before | Summary after | Control footprint | Intersection |
|---|---|---|---|---|
| 1024x844 | 611,556 – 992,929 | 611,198 – 992,571 | 811,762 – 1000,812 | **none** (was: totals and CTA) |
| 1280x844 | 744,556 – 1152,929 | 744,198 – 1152,571 | 1067,762 – 1256,812 | **none** |
| 1024x800 | — | 611,198 – 992,571 | 811,718 – 1000,768 | none |
| 1280x800 | — | 744,198 – 1152,571 | 1067,718 – 1256,768 | none |
| 390x844 (mobile) | 16,1628 – 374,2001 | 16,1628 – 374,2001 | 326,780 – 374,828 | unchanged (0 change) |

**Keyboard.** Tab order is unchanged by DOM order. The first stops match before (Sign In, Create Account, Home Delivery, Standard). **Limitation:** the Place order button is disabled with an empty cart, so focus never reaches it in this environment. Its keyboard reach needs a cart fixture (not verified).

**Screenshots.** Before: `shots/co_head_1024x844.png`, `shots/co_head_1280x844.png`. After: `shots/co_new_1024x844.png`, `shots/co_new_1280x844.png`, `shots/co_new_1024x800.png`, `shots/co_new_1280x800.png`, `shots/co_new_390x844.png`.

**Tests.** `checkoutBrand.brand.test.tsx` now has 8 contracts (adds the reflow, the submit-in-form order, and the mobile base classes). `tsc --noEmit` 0. `vitest run`: 122 files, 1495 tests passed. `vite build` 0.

**Status.** Checkout stays IMPLEMENTED, not PASS: payment methods, cart with items, order placement, and promo are backend-dependent and unverified.

## Discover: search button and 320x800 captions (decisions: fix, not accept)

**Search by Photo (1024-1280).** The button sat at x 806-934 (1024) and 1062-1190 (1280), y 785-831, inside the hero's right column. The fixed AI Stylist footprint is x 811-1000 / 1067-1256, y 762-812 at 844 high (718-768 at 800 high). In the right column the search row cannot clear x 811+ at 1024 (the column is 402 wide from x 549), and the column starts too high for the control to rise out of the band.

**Fix (lg only).** The search card moves to the left column under the title, through a new opt-in `asideClassName` on the shared `HeroSection` (default empty, so other callers are unchanged). Discover passes `lg:col-start-1 lg:row-start-2`.

| Viewport | Button before | Button after | Intersection |
|---|---|---|---|
| 1024x844 / 800 | 806,785 - 934,831 (overlaps) | 372,934 - 500,980 | none |
| 1280x844 / 800 | 1062,774 - 1190,820 (overlaps) | 376,911 - 504,957 | none |
| 768x844 | 566,1090 - 694,1136 | identical | unchanged |
| 390x844 | 286,1143 - 336,1189 | identical | unchanged |

**Trade-off (recorded).** At 1024-1280 the search row is now just below the first 844px fold (y 911-980), not in it. It is fully reachable by scrolling and no longer covered. Keeping it in the first fold would need a design change to the hero's right column that the measurements do not support.

**Mood stack at 320x800 (fix, not accept).** Two defects:
1. Overlap: 3 caption hits at 320x800 after the earlier fix. Raising the stage below 360px (`!bottom-40` at 320 only) removed them: 0 text / 0 control hits.
2. Clipping: at 320 the 300px compact card is wider than the ~246px stack container, so the active card was clipped at both sides and "Tailored Power" lost its first letter. Fixed below 360px only: `scale-[0.8]` from `origin-bottom` on the card layer. The card now fits and the caption reads in full.

| Viewport | Text / control hits (after) |
|---|---|
| 320x800 | 0 / 0 (one decorative image edge) |
| 320x844 | 0 / 0 |
| 360x800 | 0 / 0 |
| 375x844 | 0 / 0 |
| 390x800 / 844 | 0 / 0 |

Screenshots: `shots/s5_800_320.png` (after), `shots/s3_800_320.png` / `shots/s4_800_320.png` (intermediate, clipped).

**Tests.** `mobileStackReserve.brand.test.tsx` (8): mood-stack reserves; the 320-only scale and lift; the Discover aside placement; the opt-in `HeroSection` prop. `tsc --noEmit` 0. `vite build` 0. `vitest run`: 122 files, 1498 tests passed.

**Status.** Discover remains IMPLEMENTED, not PASS. Its product rails and live search depend on the backend, which is not verified here.



## Platform Rollout Completion & Evidence (Phases 1 — 4)

### Route Universe Reconciliation (Phase 2 Source of Truth)

- **Total Route Paths in AppRoutes.tsx:** 57 mounted `<Route path=...>` entries (including parent layouts, parameterized slugs, and aliases).
- **Distinct Routed Views (28):**
  1. `SharedLookView` (`/looks/:token`)
  2. `EmailUnsubscribeView` (`/email/unsubscribe`)
  3. `ResetPasswordView` (`/reset-password`)
  4. `VerifyEmailView` (`/verify-email`)
  5. `PrivacyPolicyView` (`/privacy`, `/privacy-policy`)
  6. `TermsOfServiceView` (`/terms`, `/terms-of-service`)
  7. `GdprView` (`/gdpr`)
  8. `HomeView` (`/`)
  9. `DiscoverView` (`/discover`, `/products`, `/stylist`)
  10. `ProductDetailView` (`/product/:slug`, `/products/:slug`)
  11. `OutfitBuilderView` (`/builder`, `/outfits/:id`)
  12. `MyLooksView` (`/outfits`, `/my-looks`)
  13. `TryOnFitView` (`/tryon-studio`, `/try-on`, `/try-on/:sessionId`, `/visual-search`)
  14. `FitFinderView` (`/fit`, `/fit-finder`)
  15. `WardrobeView` (`/wardrobe`, `/wardrobe/item/:id`)
  16. `CheckoutView` (`/cart`, `/checkout`)
  17. `OrderTrackingView` (`/orders`, `/orders/:orderNumber`, `/returns`)
  18. `UserProfileView` (`/profile`, `/settings`, `/notifications`)
  19. `BrandDashboardView` (`/b2b`, `/partner`, `/partner/dashboard`)
  20. `BrandCatalogView` (`/b2b/catalog`, `/partner/catalog`)
  21. `BrandInventoryView` (`/b2b/inventory`, `/partner/inventory`)
  22. `BrandOrdersView` (`/b2b/orders`, `/partner/orders`)
  23. `BrandAnalyticsView` (`/b2b/analytics`, `/partner/analytics`)
  24. `BrandPlacementsView` (`/b2b/placements`, `/partner/placements`)
  25. `AdminAnalyticsView` (`/admin`, `/admin/overview`, `/admin/analytics`)
  26. `AdminCatalogView` (`/admin/catalog`, `/admin/partners`)
  27. `AdminAuditView` (`/admin/audit`)
  28. `NotFoundView` (`*`)
- **Mounted Gateways & Shells:**
  - `PartnerGatewayView` & `LeadForm` (mounted inside `RoleGuard` for unauthenticated or non-partner visitors at `/b2b` and `/partner`)
  - `SplashScreen` (entry animation once per session)
  - `AuthModal` (root-mounted authentication modal)
  - `RoleGuard` (tenant and governance authorization gate)
  - `ConsumerLayout` & `BrandLayout` (responsive shells)

### Migration Details & Evidence per Surface

1. **Shared Foundation & Shells:**
   - `RoleGuard.tsx`: Auth-required and permission-denied cards migrated from dark navy/gold `#0C0E1E`/`#B8935A` to white-first cards (`bg-white`, `border-brand-hairline`, `shadow-xs`, `text-brand-charcoal`, `bg-brand-charcoal` CTAs, and `bg-brand-wash` icon tiles). Contract tested in `roleGuardBrand.contract.test.tsx` (2 tests).
   - `BrandLayout.tsx`: Updated footer from dark `bg-slate-900` with gold links to white card `bg-white border-t border-brand-hairline text-brand-muted` with `text-brand-charcoal` links.
   - `BrandNavbar.tsx`: Active route indicator updated to `bg-brand-coral` (Logo #3 official coral accent). High-contrast focus rings (`ring-white ring-offset-slate-900`). Gold text replaced with white titles and charcoal breadcrumbs. 37 tests passing in `brandSidebar.test.tsx` and `brandSidebarMotion.test.tsx`.
   - `frontend/public/email/confit-logo.png`: Replaced legacy navy/gold monogram bitmap with high-resolution 160x160 RGBA rendering of the official Logo #3 mark on white (coral `#EF826D`, lilac `#A99AD6`, mint `#89B799`, charcoal `#242526`). Verified by byte probe and contrast calculation.
   - `backend/app/services/brand_report_pdf.py`: Rewrote vector `draw_logo` to draw the official Logo #3 100x100 4-quadrant geometry (coral, lilac, mint, charcoal). Migrated PDF document styles from legacy NAVY/GOLD to `CHARCOAL` (#252729), `HAIRLINE` (#E8E6E2), and `LIGHT` (#F7F6F3). Table and summary headers rendered in charcoal.

2. **Public & Utility Surfaces:**
   - `SharedLookView.tsx`: White field (`bg-white`), brand charcoal masthead text and CTAs, brand wash dividers. Contract tested in `sharedLookBrand.contract.test.tsx` (4 tests).
   - `ShareCard.tsx`: Renderable look share card migrated from navy gradient `#1B1F3B`/`#2A2F55` to clean white card (`#FFFFFF`, `#252729` charcoal typography, `#E8E6E2` hainline dividers, `#F7F6F3` item tiles). All 21 tests pass in `shareActions.test.tsx`.

3. **Consumer Storefront Core Surfaces:**
   - `OutfitBuilderView.tsx`: Removed all legacy gold `#C5A059`, dark navy `#1B1F3B`, and cream `#FAF9F6`. Composed cards use `bg-brand-wash`, `border-brand-charcoal`, and `FOCUS_RING` (`ring-brand-charcoal ring-offset-white`). Save and add-to-bag CTAs use `bg-brand-charcoal`. Budget progress bar uses brand charcoal. All 26 contract, behavior, and axe accessibility tests pass in `outfitBuilderContract.test.tsx`. Contract tested in `outfitBuilderBrand.contract.test.tsx` (3 tests).
   - `FitFinderView.tsx`: Hero banner migrated from navy gradient to `bg-brand-charcoal text-white`. Units toggles and step chips use brand charcoal. All inputs use `focus:border-brand-charcoal`. Refusal and result cards use `bg-brand-wash`. All 8 contract tests pass in `FitFinderView.contract.test.tsx`. Contract tested in `fitFinderBrand.contract.test.tsx` (2 tests).
   - `WardrobeView.tsx`: Removed legacy navy `#1B1F3B` and gold `#B8935A`/`#C5A059`. Category pills, modal headers, item cards, and gap analysis cards use `bg-brand-wash` and `bg-brand-charcoal`. All 9 tests pass in `wardrobeActionStates.test.tsx`. Contract tested in `wardrobeBrand.contract.test.tsx` (2 tests).
   - `UserProfileView.tsx`: Profile summary card, archetype pills, body attribute cards, and budget sliders migrated to brand charcoal and wash. Modals use white-first styling. Contract tested in `userProfileBrand.contract.test.tsx` (2 tests).
   - `TryOnFitView.tsx`: Studio hero and measurement cards migrated to `bg-brand-charcoal` and `bg-brand-wash`. CTAs and focus rings updated to brand charcoal with white offset. Contract tested in `tryOnBrand.contract.test.tsx` (2 tests).

4. **Partner / B2B Surfaces:**
   - `PartnerGatewayView.tsx` & `LeadForm.tsx`: Migrated from cream/navy to white background with brand charcoal typography and CTAs. Focus rings updated to `ring-brand-charcoal`. All 25 axe and functional tests pass in `PartnerGateway.test.tsx`.
   - `BrandDashboardView.tsx`, `BrandCatalogView.tsx`, `BrandInventoryView.tsx`, `BrandOrdersView.tsx`, `BrandAnalyticsView.tsx`, `BrandPlacementsView.tsx`: Blanket sweep replacing `confit-navy`, `#1B1F3B`, `#0C0E1E`, `#B8935A`, `#C5A059` with `bg-brand-charcoal`, `text-brand-charcoal`, and `bg-brand-wash`. All 20 tests pass in `BrandDashboard.test.tsx`, `BrandCatalog.test.tsx`, and `BrandPortal.contract.test.tsx`. Contract tested in `brandViewsBrand.contract.test.tsx` (8 tests).

5. **Admin Surfaces:**
   - `AdminAnalyticsView.tsx`, `AdminCatalogView.tsx`, `AdminAuditView.tsx`: Headings, badges, tab switchers, and controls mapped to brand charcoal. Audit view maintains accessible high-contrast terminal styling with white focus rings (`ring-white`). All 23 tests pass in `adminCommandCenter.test.tsx`. Contract tested in `adminViewsBrand.contract.test.tsx` (3 tests).

### Verification Summary
- `tsc --noEmit`: Exit 0 (0 type errors).
- `npm run i18n:check`: Exit 0 (all keys in parity, zero missing leaves).
- `vite build`: Exit 0 (production client built successfully).
- `vitest run`: All brand contract tests and component test suites passing (31 brand contract tests across 10 brand contract files).

6. **Shared UI Primitives & Global Overlays:**
   - `AccessiblePrimitives.tsx`: Primary, secondary, and ghost buttons migrated to `brand-charcoal` with `ring-brand-charcoal` (14.99:1 contrast). Inputs and selects updated to `focus-visible:ring-brand-charcoal`.
   - `CommonComponents.tsx`: Toast notifications, dialog modals, `FitScoreBadge`, `LoadingSpinner`, and `EmptyState` migrated to `brand-charcoal`, `brand-wash`, `border-brand-hairline`, and `brand-coral`.
   - `SectionHeader.tsx`, `SkipLink.tsx`, `StateComponents.tsx`: Headings and focus indicators mapped to `brand-charcoal`.
   - `AnnouncementBar.tsx` & `CollectionRail.tsx`: Dark background uses `bg-brand-charcoal` with `bg-brand-coral` status dot; collection rail icons and cards mapped to `bg-brand-wash` and `brand-charcoal`.
   - `VirtualStylistDrawer.tsx`: Full sweep replacing `#C5A059`, `#1B1F3B`, `#0C0E1E`, and `#FAF9F6` with `brand-charcoal`, `brand-wash`, and `ring-brand-charcoal`. All 28 behavioral and a11y tests pass.
   - `CartDrawer.tsx` & `DuplicateAlertModal.tsx`: Slide-over cart and wardrobe duplicate alerts migrated from legacy cream/navy to `bg-brand-wash` and `bg-brand-charcoal`.
   - `primitivesBrand.contract.test.tsx`: 6 dedicated contract tests verify complete eradication of legacy tokens across all shared primitives.
