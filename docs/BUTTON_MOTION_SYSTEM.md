# Button Motion System — Part 1

**Status:** implemented, tested, and applied to **every functional control in the product**.
**Scope:** 313 buttons across 8 role surfaces (consumer, shared components, AI stylist,
brand/admin console, admin tools, auth, public/legal, shared UI), grouped into 13 semantic
families, each with its own colour psychology and its own loading gesture.

---

## 0 · What was asked, and what this is

The brief: act as frontend/UX/CSS-animation owner; find **all** functional buttons across the
roles and dashboards; group them by functionality and role; and give each group a bespoke,
context-aware, performance-optimised **background** animation that reflects the action's
semantic purpose and its state — using Tailwind or vanilla CSS `@keyframes`, no heavy JS
animation library, no layout shift, `prefers-reduced-motion` respected, and strict colour
psychology (destructive = warning, progressive = growth).

Everything below is that, and nothing below is decorative for its own sake.

### What shipped

| | |
|---|---|
| Controls covered | **313** — 100% of the `<button>` surface; a ratchet test fails if a new control ships without an intent |
| Semantic families | **13**, each with a fixed palette, gesture and loading behaviour |
| Role surfaces | **8** (see the matrix in §3) |
| Animation engine | `src/styles/button-motion.css` — 5 keyframes, 100% CSS, no runtime |
| Typed contract | `src/components/common/buttonMotion.ts` — the registry the stylesheet is checked against |
| Assignment tool | `scripts/apply-button-motion.mjs` — rule table, dry run, CSV catalog, `--json` oracle for CI |
| Contract tests | `src/components/__tests__/buttonMotion.contract.test.tsx` — **41 assertions** |
| Catalog | `docs/button-motion-catalog.csv` — every control: role, file, line, family, geometry, label, reason |

---

## 1 · The mechanism (one attribute, two layers, zero layout)

A control opts in with one attribute:

```tsx
<button data-motion="financial">Pay now</button>
```

Two gradient layers are painted onto the button's **own** `background-image`:

| layer | what it is | what it does |
|---|---|---|
| 1 · the **streak** | a narrow highlight (≤ 0.26 white, or a dark hairline for chrome) | crosses the control on hover, press, loading and success |
| 2 · the **wash** | the broad semantic tint (≤ 0.14 alpha) | slides in from the inline start and settles; carries the family's colour |

Painting them on the element's own background — rather than on a `::before` pill — is
deliberate: no `position: relative`, no `overflow: hidden` (which would clip cart-count
badges and focus rings), and no z-index negotiation with labels, icons or children. Text is
always painted above an element's own background, so **an animation can never obscure the
label it belongs to**.

**At rest nothing is painted.** Both layers sit completely outside the padding box
(`background-position` for an N×-scaled image resolves to `(W − N·W)·P/100`), so adding the
system to a control is a visual no-op until the user interacts. That is what made it safe to
apply to all of them at once: no resting-state regression, no contrast re-check at rest, no
layout to move.

**No layout shift, by construction.** The five keyframes animate only `background-position`,
`background-size` and `transform` (the error nudge). A test asserts that no layout-affecting
property appears in any keyframe — width, height, margin, padding, inset, font-size,
letter-spacing, box-shadow, filter and 20 others are banned by assertion, not by convention.

---

## 2 · The 13 families

Grouped by **what the control does**, not by where it lives — so a consumer's "Remove item"
and an admin's "Revoke key" are the same family and animate identically, because they are
the same kind of act.

| `neutral` | Chrome — cancel, close, back, step, paginate, expand | Graphite hairline (inert) | quiet crossing; a pulse while loading | 57 |
| `progressive` | Forward motion — create, save, submit, continue | Navy → blue → mint (growth + trust) | the streak crosses, inline-start → inline-end | 44 |
| `filter` | Chips, segments, tabs, sort toggles, unit switches | A navy rule under the label | the rule GROWS from the inline start — an affordance, not a repaint | 42 |
| `creative` | Generative surfaces — try-on, stylist, describe, "complete the look" | Lilac → periwinkle (generative) | the wash drifts and pulses — never a progress bar for work with no measurable progress | 40 |
| `recovery` | Second chances — retry, refresh, resend, restore, undo | Amber → green (renewal) | a pulse, never a bar: a retry has no known duration | 31 |
| `auth` | Identity — sign in, sign up, verify, OTP, password, MFA | Navy → lilac (identity) | an unhurried crossing | 26 |
| `admin` | Authority verbs — approve, publish, feature, verify, bulk-run | Navy → brand gold (authority) | the streak crosses | 23 |
| `destructive` | Irreversible harm — delete, revoke, archive, disconnect | Rose → amber (warning) | hazard tape slides for as long as the work runs | 15 |
| `upload` | The control gains content — upload, import, capture, attach | Mint → teal (incoming) | the wash RISES from below and settles at the bottom edge | 14 |
| `commerce` | Bag and wardrobe verbs — add to bag, wishlist, quantity | Charcoal → gold (the brand's own commerce) | the streak crosses | 9 |
| `financial` | Money — checkout, place order, pay, wallet | Gold → deep gold (value, deliberately slow) | the slowest crossing in the system: gold arrives, it does not flash | 5 |
| `download` | The control releases content — export, invoice, report, receipt | Slate → navy (calm exit) | the wash FALLS and settles high | 5 |
| `share` | Outward hand-off — share, invite, copy link, refer | Mint → sky (outgoing) | the fastest sweep in the system | 2 |

---

## 3 · The catalog, by role

| Role | `neutral` | `progressive` | `filter` | `creative` | `recovery` | `auth` | `admin` | `destructive` | `upload` | `commerce` | `download` | `financial` | `share` | total |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **Consumer** | 11 | 29 | 18 | 12 | 12 | 9 | 2 | 9 | 4 | 2 | 1 | 4 | · | 113 |
| **Consumer (shared components)** | 4 | 8 | 5 | 21 | 4 | · | · | 4 | 7 | 4 | 1 | 1 | · | 59 |
| **AI Stylist / Outfit** | 2 | 1 | 2 | 3 | 1 | · | · | · | · | 1 | · | · | 2 | 12 |
| **Brand / Admin console** | 8 | 2 | 8 | 1 | 11 | 2 | 20 | · | 3 | · | 1 | · | · | 56 |
| **Admin (components)** | · | · | · | · | · | · | · | · | · | · | 1 | · | · | 1 |
| **Auth** | 2 | 1 | 2 | · | · | 8 | 1 | · | · | · | · | · | · | 14 |
| **Public / Legal** | 1 | 1 | 2 | · | 1 | 2 | · | · | · | · | 1 | · | · | 8 |
| **Shared UI** | 29 | 2 | 5 | 3 | 2 | 5 | · | 2 | · | 2 | · | · | · | 50 |
| **total** | 57 | 44 | 42 | 40 | 31 | 26 | 23 | 15 | 14 | 9 | 5 | 5 | 2 | **313** |

`·` = no control of that family on that surface.

### Highlights per surface

**Consumer** — 113 controls

- `financial`: “Proceed to Checkout” (CartDrawer), the checkout submit (CheckoutView, `financial` ActionButton)
- `destructive`: “Delete” (MyLooksView), “Remove item” (CheckoutView), “Clear Canvas” (OutfitBuilderView)
- `recovery`: “Retry” ×7 across FitFinder/Home/OrderTracking/ProductDetail
- `filter`: the size, colour, occasion and fit chips (FitFinder), “Clear filters” (Discover)
- `creative`: “Photo Match” (Discover), “Open Virtual Try-On” (FitFinder), the stylist FAB

**Consumer (shared components)** — 59 controls

- `creative`: 21 controls in the try-on studio: capture, lintel, render, complete-the-look
- `upload`: “Enable camera”, “Switch camera”, “Upload Piece”, “Batch upload from gallery”
- `commerce`: bag quantity steppers, wishlist toggles, “Add Items to Bag”
- `destructive`: “Clear All”, per-item remove in the try-on canvas

**AI Stylist / Outfit** — 12 controls

- `creative`: “Style”, “Try”, the outfit-builder slot controls
- `share`: “Copy link”, “Share…”
- `filter`: the voice-input hold control, the look-idea selector

**Brand / Admin console** — 56 controls

- `admin`: 20 authority controls: “Add product”, “Apply tags”, “Save SKU”, “Create Store”, “Bulk CSV Import”
- `recovery`: 11 retry/refresh controls — every table and dashboard has one, and all of them animate identically
- `filter`: the analytics window chips, the sort toggles on every table header
- `download`: “Report (PDF)” per brand, “Download template”

**Admin (components)** — 1 controls

- `download`: the per-brand PDF report control

**Auth** — 14 controls

- `auth`: “Send code to my email”, “Verify & sign in”, “Set new password”, the OAuth continue buttons
- `neutral`: “Back to sign in”, the modal close
- `filter`: “Show password”, the 2FA method switch

**Public / Legal** — 8 controls

- `auth`: “Verify my email”, “Set new password”
- `filter`: the unsubscribe confirmation choices

**Shared UI** — 50 controls

- `neutral`: carousel prev/next, nav drawer toggles, portal back buttons, pagination
- `auth`: the RoleGuard gates: “Sign In to Continue”, “Switch Account / Re-authenticate”
- `creative`: “Open visual search”, “AI Stylist Director”

### How the assignment was made

No label was guessed. `scripts/apply-button-motion.mjs` resolves each control's **English
label from `en.json`** (a raw `t('looks.revoke')` cannot be classified; "Revoke" can), then
applies a rule table in precedence order: attribute facts first (`aria-pressed` → a chip, a
file-input trigger → upload), then vocabulary, and only then the role of the surface as a
documented last resort. Every decision is recorded in `docs/button-motion-catalog.csv` with
the exact reason — "`retry`", "aria-pressed", "role-default(consumer surface)" — so the
classification is auditable rather than asserted.

---

## 4 · States — what the animation says, and when

The engine reads the state the *product* already publishes. It never invents one: a control
cannot look successful before the server said so, because the CSS has nothing to read until
`data-state="success"` exists.

| State | Trigger (any of) | What the user sees |
|---|---|---|
| **Default** | — | nothing: both layers rest off-canvas. The control looks exactly as it does today |
| **Hover / focus-visible** | `:hover`, `:focus-visible` | the wash slides in from the inline start and settles; the streak crosses and leaves. Keyboard focus gets the *same* affordance as the pointer (WCAG 2.4.7 parity) |
| **Active (pressed)** | `:active` | the streak re-fires in 420 ms and the wash holds — tactility from the same two layers, so no call site's `active:scale-*` has to be fought or overridden |
| **Loading** | `[aria-busy="true"]`, `[data-state="pending"]`, `[data-motion-state="loading"\|"pending"]` | the family's gesture loops (crossing / rising / falling / drifting / pulsing / hazard tape / growing rule) until the real state changes. No timeout, no fake progress, no completion. A retry never shows a bar, because a retry has no known duration |
| **Success** | `[data-state="success"]`, `[data-motion-state="success"\|"done"]` | one crossing of the streak (iteration count 1 — a finite gesture for a finite event) and a green wash that stays |
| **Error** | `[data-state="error"\|"offline"]`, `[data-motion-state="error"\|"failed"]` | a red wash that stays, plus a 2px nudge — the only transform in the file, `motion-safe` only, returning to 0 so nothing is left displaced |
| **Quiet** | `[data-state="unavailable"\|"unauthorized"]` | a neutral wash and **no motion at all**: the control is not failing, it is waiting for a precondition. Giving it alarm or celebration would be a lie |
| **Disabled** | `:disabled`, or `[aria-disabled="true"]` **while not busy** | no layers, no animation. The exclusion is load-bearing: `ActionButton` reports `aria-disabled` *during* pending to keep focus, and freezing a running action would report "stopped" for work that is still going |

**ActionButton needed no new state machine.** It already publishes `data-state`
(idle · pending · success · error · unavailable · unauthorized · offline) and `aria-busy`;
the engine reads those. The eight unified CTAs therefore animate correctly from the day the
attribute landed, and the contract test proves the states the engine reads are the states
the machine publishes. Six of those CTAs additionally declare an explicit intent, because
their default would have been wrong: revoking a link is `destructive`, running a render is
`creative`, minting or rotating a share link is `share`, and the partner-lead submit is
`progressive`.

Colour psychology, fixed in one place: money is gold and slow; destruction is rose and amber;
growth is navy → mint; generative work is lilac; authority is navy → gold; incoming data is
mint and rises; outgoing data is slate and falls; identity is navy → lilac; chrome is
graphite and whispers.

---

## 5 · Accessibility

### `prefers-reduced-motion: reduce`
Every animation is switched off **explicitly** — not merely collapsed by the global 0.001 ms
rule in `index.css`, because collapsing an infinite animation still leaves the browser
claiming it. With motion gone:

- hover/focus settle the wash instantly, so the affordance survives without movement;
- every state keeps its **static** palette: success is still green, failure is still red,
  work in flight is still amber;
- the label has always been the primary carrier of state; the colour is now the second.

### `forced-colors: active`
Windows High Contrast owns the palette, so the engine steps aside completely
(`background-image: none`, `animation: none`). The control keeps its text, its border and its
focus ring — which is what the user asked their OS for.

### Arabic / RTL
Direction lives in tokens, not in duplicated rules: one `[dir="rtl"]` block mirrors the
gradient angle (θ → 360° − θ) and the four travel positions, so a sheen enters from the
inline **start** — the right edge — in Arabic exactly as it does from the left in English.
A test asserts there is no RTL twin of any keyframe, which is what keeps the two languages
from drifting apart.

### Contrast — measured, and one defect found and fixed
The contract test composites the strongest stop of every wash over the product's own
surfaces with real WCAG relative-luminance math:

| Case | Measured worst | Requirement |
|---|--:|--:|
| Secondary text token `muted #595C63` over brand cream, under the strongest field wash | **4.82:1** | 4.5:1 (AA) |
| White label over the charcoal fill, under the strongest streak | **6.39:1** | 4.5:1 |
| `slate-100` label over the charcoal fill, under the strongest streak | **5.83:1** | 4.5:1 |

**The defect it found:** a field tint behind a `text-slate-500` label measured **4.0–4.3:1**
— a real WCAG 1.4.3 failure that no code review would have caught, because a 14% wash looks
like nothing. `slate-500` is 4.76:1 on white at rest, so almost any darkening beneath it
spends that margin.

**The fix is geometry, not colour.** Controls whose own label is a medium-tone grey
(slate-300/400/500) get `data-motion-tone="edge"`: the wash becomes a 2px stroke pinned to
the box's outer edge, where a centred label cannot sit (≈14px of clearance under the text on
the smallest 44px control). Colour, timing, direction, the streak and every state are
unchanged. The rule lives in the codemod, and the test asserts that **no** control with a
medium-tone label may carry a field tint — so the defect cannot return with a new component.

Two more guards: glyph-only controls (`✕`, `+`, `−`) get the `icon` geometry, because a glyph
is a graphic (WCAG 1.4.11 asks 3:1 of it) and there is no text to tint; and every wash stays
under 0.3 alpha except the chip/segment rule, which is 2px tall and has no text on it.

---

## 6 · Performance

- **Nothing is painted at rest.** Both layers sit off-canvas until the pointer, the keyboard
  or a state arrives, so 313 controls cost nothing until one of them is used.
- **`will-change` is claimed only while the pointer or keyboard is on the control**, and
  released on the way out (the base rule restores `will-change: auto`, as do the
  reduced-motion and forced-colors blocks). It is never left on.
- **Only paint-cheap properties move**: `background-position` / `background-size` on small
  controls, plus one transient `transform`. No `filter`, no `backdrop-filter`, no animated
  shadow.
- **The loops are seamless**: each cycle starts and ends with the layer off-canvas, so the
  wrap is invisible, and the hazard-tape loop travels exactly one tile period for the same
  reason.
- **Direction is data, not duplication**: one set of keyframes serves both writing
  directions, so the browser has one animation to optimise per family rather than two.

---

## 7 · Using it

### A new control

```tsx
{/* plain element — one attribute */}
<button data-motion="destructive" data-motion-tone="edge">Delete account</button>

{/* typed helper — the compiler catches a misspelt intent */}
import { buttonMotion } from '../common/buttonMotion';
<button {...buttonMotion({ intent: 'upload' })}>Upload piece</button>

{/* unified CTA — its state machine is already wired to the engine */}
<ActionButton intent="financial" financial labels={labels} onAction={pay} />
```

Then run the ratchet; a control with no intent fails with its file and line:

```bash
cd frontend
node scripts/apply-button-motion.mjs              # dry run: what would change, and why
node scripts/apply-button-motion.mjs --write      # apply
node scripts/apply-button-motion.mjs --report ../docs/button-motion-catalog.csv
npx vitest run src/components/__tests__/buttonMotion.contract.test.tsx
npm run verify                                    # i18n · tsc · all tests · build
```

### Reviewing it without a browser

The system ships with a generated spec sheet — every family in every state, on both surface
weights, plus the three geometries, the Arabic panel and the reduced-motion fallback:

```bash
node scripts/button-motion-preview.mjs           # writes docs/button-motion-preview.html
node scripts/button-motion-preview.mjs --check   # exits 1 if it is stale
```

It is generated from the stylesheet, not written alongside it: the engine is inlined verbatim
and the two pointer states are the engine's own declarations re-pointed at a demo attribute,
so there is no second copy of any recipe to drift. Open the HTML and the loading gestures are
*live*, not screenshots — which is the only honest way to review an animation.

### Opting a control out

`data-motion="none"` removes the layers and keeps the call site's own transitions. It exists
for a control that owns a bespoke surface (a gradient fill, a photographic button), and its
presence is asserted so the escape hatch cannot be deleted by accident.

### Adding a 14th family

1. add the intent to `BUTTON_INTENTS` in `buttonMotion.ts` — the compiler then types it;
2. add a `[data-motion="<intent>"]` block in `button-motion.css` with its `--_mo-wash` — the
   parity test fails in both directions until the two agree;
3. re-run the codemod to assign real controls;
4. the coverage test refuses an "aspirational" recipe that no control uses.

---

## 8 · Files

**Added**

| Path | What it is |
|---|---|
| `frontend/src/styles/button-motion.css` | the engine: tokens, 13 recipes, 5 keyframes, state map, geometry variants, RTL, reduced motion, forced colors |
| `frontend/src/components/common/buttonMotion.ts` | the typed contract: intents, tones, phase→state aliasing, `buttonMotion()` |
| `frontend/scripts/apply-button-motion.mjs` | the assignment tool and the coverage oracle |
| `frontend/src/components/__tests__/buttonMotion.contract.test.tsx` | 41 contract assertions |
| `frontend/scripts/button-motion-preview.mjs` | generates the reviewable spec sheet from the stylesheet |
| `docs/BUTTON_MOTION_SYSTEM.md` | this document |
| `docs/button-motion-catalog.csv` | all 313 controls: role, file, line, family, geometry, label, reason |
| `docs/button-motion-preview.html` | the generated spec sheet: every family in every state, live |

**Changed**

| Path | Change |
|---|---|
| `frontend/src/main.tsx` | loads `button-motion.css` after `index.css` (the order is asserted) |
| `frontend/src/components/common/ActionButton.tsx` | `intent` + `motionTone` props; publishes `data-motion` / `data-motion-tone`; defaults to `financial` for money-moving CTAs, `progressive` otherwise |
| 58 view/component files | one attribute per `<button>` (313 in total), inserted mechanically by the tool |
| 6 ActionButton call sites | explicit intents where the default would have been wrong |

---

## 9 · Known limitations (stated, not hidden)

- **Three labels could not be resolved to copy** by the catalog (`VirtualStylistDrawer`,
  `AdminAnalyticsView`, `EmailUnsubscribeView`) because they interpolate `t()` inside a
  template expression. They were assigned from their handler and their surface instead, and
  their rows in the CSV say so (`role-default(...)`).
- **The chip/segment rule is exempt from the alpha ceiling** (0.75 on a 2px stroke). It is a
  stroke, not a field: no text sits on it. The exemption is asserted — and asserted to be the
  only one.
- **framer-motion still animates the CTA's tap scale.** That is pre-existing and untouched;
  what the brief rules out is a JS-driven *background*, and a test asserts `ActionButton`
  never animates `background*` through its motion props. Removing framer-motion from the
  pointer/keyboard path entirely is a follow-up that would touch 20 files, most of them
  unrelated to buttons.
- **Contrast is asserted for the product's own text tokens** (charcoal, muted, slate-600,
  slate-700) plus the light-on-dark case. A future control introducing a *new* medium tone
  must add it to the medium-tone rule in the codemod: the test fails if a slate-300/400/500
  label gets a field tint, but it cannot know about a colour that does not exist yet.
