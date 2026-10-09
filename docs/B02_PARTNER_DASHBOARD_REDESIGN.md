# B02 — Partner Command Center (`/b2b` authenticated) · Teardown & Redesign

Scope row (injected): **B02 لوحة الشريك الرئيسية** — `/b2b` after partner sign-in.
Required: performance, sales/conversion, catalog data, fit & return/order indicators.
Backend sources: `GET /brand/analytics`, `GET /brand/profile`, `GET /brand/products`
(`backend/app/controllers/brand_controller.py:140,151,242`).

Method (same discipline as B01): read the repo before editing; every defect below is
**measured** (contrast computed from the WCAG relative-luminance formula, occurrences
located by grep with line numbers against `frontend/src/views/b2b/BrandDashboardView.tsx`
at commit `52920b6`); nothing is claimed that is not wired.

Data contract (`backend/app/schemas/brand.py:91-111`): `funnel_conversion_rate`,
`return_rate_before_vton`, `return_rate_after_vton`, `return_reduction_percentage`,
`bopis_store_fulfillment_rate` are **Optional — `None` means "no denominator, nothing
was measured"** and MUST render as N/A, never as a fabricated 0%.

---

## Defects (current build, commit `52920b6`)

### D1 — The page bypasses i18n almost entirely (Arabic partners get English)
One `t()` call in 226 lines (`b2b.ranked_by_appearances`, line 162). Everything else is
hard-coded English. Eight strings are registered in the debt register
`frontend/i18n-baseline.json` (count 57) for this file alone:
`Add to Cart`, `B2B telemetry unavailable`, `From RecentlyViewed table`,
`No outfit appearances yet`, `No views yet - will populate when users view your products`,
`Real Data`, `Return Reduction`, `Total Purchases`.
The register's own contract says it may only SHRINK. → All copy moves to `b2b.dash.*`
keys in `en.json`+`ar.json`; the eight entries are removed from the baseline.

### D2 — `text-slate-400` on light surfaces = 2.56:1 (fails WCAG 2.2 AA 1.4.3)
Nine occurrences on white/cream:
- KPI card labels ×4 — lines 61, 72, 84, 100 (`text-xs font-bold` on `bg-white`),
- rank row meta — line 188 (`text-[10px]` on `#FAF9F6`, 2.47:1),
- "Conversion" micro-label — line 192 (`text-[9px]` on white),
- catalog summary labels ×4 — lines 206, 210, 214, 218 (`text-[10px]` on `#FAF9F6`).
(The hero uses slate-400 on slate-900 = 6.96:1 — that one passes and is not a defect.)
→ Labels to `slate-600` (7.58:1), meta notes to `slate-500` (4.76:1 on white / 4.52:1 on cream).

### D3 — Brand gold as TEXT on light surfaces = 2.85:1
- Line 75: the big try-on numeral `text-[#B8935A]` on white. Even as 24px bold (large
  text, 3:1 floor) it fails at 2.85.
- Line 186: `<strong className="text-[#B8935A]">` inside 11px copy on `#FAF9F6` — worse.
→ Numerals to `--confit-navy`/semantic `emerald-700` (5.48:1); gold survives only as
hairlines/accents on dark navy (6.26:1 on `#0F172A`), matching the B01 register rule.

### D4 — `text-slate-500` on the dark hero = 3.75:1
Line 45, the 11px methodology line on `bg-slate-900`. → `slate-300`/`slate-400` on dark
(slate-400 on slate-900 = 6.96:1).

### D5 — `amber-600` on white = 3.19:1
Line 68, the 10px "No views yet" warning. → `amber-700` on `amber-50` (4.84:1), the pair
the view already uses correctly at line 152.

### D6 — Sub-11px typography (cognitive + low-vision failure)
`text-[9px]` ×1 (line 192), `text-[10px]` ×8 (lines 34, 37, 50, 68, 188, 206, 210, 214, 218).
→ Floor raised to 11px (`text-[11px]`) for notes, 12px for labels.

### D7 — Database vocabulary shipped as user-facing copy
- Line 67 "From RecentlyViewed table", line 79 "From TryOnSession",
- line 169 "…counted from OutfitItem table grouped by product_id ORDER BY count DESC",
- line 151 "(real from SponsoredPlacement.spent_today) … (real from
  SponsoredPlacement.revenue_generated)", line 93 "Purchases/Views*100, excludes cancelled".
Partners are merchants. → Human source notes per metric ("Counted from product views we
retain for your brand") and ONE methodology footnote that keeps the backend's
`methodology` string verbatim (that string is the honest contract, not dev-speak).

### D8 — "Real Data" self-praise padding
`Real Data` chip (line 37), `(Real)` in two headings (157, 203), `(real from OutfitItem)`
(186). The data IS computed from DB tables — honesty is kept by the methodology
footnote + null-safe N/A rendering, not by repeating the word "real". → Chips deleted;
one source line per section. (Master prompt: eradicate fluff; B01 rule: never claim,
show.)

### D9 — Full-page generic spinner, no geometry-tailored skeletons
Line 14: `LoadingSpinner` replaces the whole screen while six parallel requests settle.
The `.skeleton-shimmer` system (styles/index.css:163-185, RTL-aware, reduced-motion-safe)
exists and is used elsewhere. → Loading renders the dashboard's own geometry as shimmer
(masthead bar, 4-cell ledger, 7/5 panels), `role="status"`.

### D10 — Partial-failure blindness
Only `analytics` gates the page (line 20). A failed `profile` silently renders the
'Brand' fallback; `fetchErrors.profile` is never shown; `loadFailed` (all six failed) is
ignored — the view shows the same EmptyState as a single-source outage, and the terminal
toast is the only all-failed signal. → Masthead shows an inline notice when profile
fails (aria-live polite); `loadFailed` renders a terminal StatusPanel distinct from the
single-source retry state.

### D11 — Ranking thumbnails are bare `<img>` (line 181)
No skeleton, no broken-image fallback. `HonestProductImage` (components/common) exists
for exactly this. → Reuse it.

### D12 — Token-less, monotone surfaces
Seven identical `bg-white rounded-3xl border-slate-200 shadow-sm` blocks; raw hexes
`#1B1F3B`, `#B8935A`, `#FAF9F6` duplicated inline instead of the established
`--confit-navy/gold/cream` tokens (styles/index.css:7-9). → Surfaces via `Surface`
primitives + tokens; presentation styles diversified (editorial masthead, hairline
ledger, bar comparison, ranked list, stat strip) like B01.

### D13 — No refresh affordance or as-of stamp on rendered data
`refresh` exists in the view-model but the dashboard offers no control; telemetry reads
as eternally current. → 48px Refresh `ActionButton` + `updated` stamp set on each
successful load.

### D14 — EmptyState retry button under the 48px floor (shared component)
`CommonComponents.tsx:258-264`: `py-2.5` + 12px text ≈ 36-38px. Same systemic fix B01
applied to `Field`. → `min-h-12 px-6` on the action button (no behaviour change).

---

## Redesign structure (12-col grid, five presentation styles)

1. **Editorial masthead (7/5)** — eyebrow + verification chip; serif clamp headline
   `{brand} Command Center` (EN string preserved for the contract + smoke harness);
   humanized catalog/commission/BOPIS line. Right 5: cream `Surface solid` panel with
   methodology footnote, as-of stamp, Refresh (48px).
2. **Hairline KPI ledger** — one `Surface solid`, 4 cells divided by hairlines
   (views / try-ons + sessions-per-view / order-line ratio (null→N/A+hint) / return
   delta). Values serif navy; semantic emerald-700/rose-700 only where the sign means
   something; notes slate-500 11px humanized.
3. **Cohort bar comparison (7)** — two horizontal bars, rose-700 (no try-on) vs
   emerald-700 (try-on), mono value labels slate-700; methodology panel cream, no emoji.
4. **Most-styled ranked list (5)** — `HonestProductImage` thumbnails, rank medallion,
   humanized empty state.
5. **Catalog stat strip** — 4 hairline stats (products/SKUs/purchases/add-to-cart).

Motion: reveal `cubic-bezier(0.25,1,0.5,1)` 0.5s, 0.06s stagger, gated on
`prefers-reduced-motion` (Surface `reveal` prop); bar fills animate width once,
reduced-motion renders final widths.

States: loading = geometry shimmer; analytics-only failure = StatusPanel error + Retry
(`common.retry`, EN "Retry" keeps contract green); loadFailed = terminal StatusPanel;
profile failure = inline masthead notice; empty (zero views) = honest "not measurable
yet" notes, never 0%.

## Verification plan
- `npm run verify` (i18n gate incl. shrunken baseline, tsc, vitest, build).
- New `frontend/src/views/__tests__/BrandDashboard.test.tsx`: skeleton role=status;
  null conversion renders N/A not "0%"; analytics failure terminal + retry; loadFailed
  terminal; AR locale renders Arabic (no English literals); refresh stamps.
- Existing `BrandPortal.contract.test.tsx` stays green unmodified (EN strings preserved).
- New goal-E2E `frontend/scripts/e2e_partner_dashboard_goals.py` (loopback-only):
  provisions an isolated brand_owner in local SQLite, real login, asserts rendered
  metrics equal the API's, skeleton-then-data, 503→error→retry, AR RTL, zero console
  errors.
- PR to `main`, CI green, merge, production bundle-hash change verified.
