# B01 — Public Partner Gateway (`/b2b`, no session)
## Architectural teardown & redesign specification

**Target:** `frontend/src/components/auth/RoleGuard.tsx` → `PartnerRequestDemoForm` + the `isPartnerPortal` branch of `RoleGuard`
**Route:** `frontend/src/router/AppRoutes.tsx:238` → `/b2b` → `PartnerPortalBoundary` → `BrandLayout`
**Backend contract:** `POST /api/v1/brand/request-demo` (alias `POST /api/v1/b2b/request-demo`) — `backend/app/controllers/brand_controller.py:35-66`
**Every defect below was verified against the source or measured. Nothing here is inferred.**

---

## PART 0 — Verified defect register

These are not opinions. Each one names a file, a line, or a measurement.

### D1 — `shadow-2xs` emits no CSS (confirmed by build)

`RoleGuard.tsx:276` applies `shadow-2xs` to the pillar cards. Tailwind **3.4.14** (`package.json`) resolves `boxShadow` to exactly:

```
sm, DEFAULT, md, lg, xl, 2xl, inner, none
```

There is no `2xs` and no `xs`. Verified by requiring `tailwindcss/defaultTheme` from a clean install of 3.4.14. **The pillar cards have no shadow at all.** Repo-wide this is **80× `shadow-2xs` + 26× `shadow-xs` = 106 dead declarations** — a v4 class name imported into a v3 project.

### D2 — Touch targets below the 48px brief

| Control | Classes | Computed height |
|---|---|---|
| Lead submit | `py-3` + `text-xs` | 12+12+16 = **40px** |
| "Request partnership" CTA | `min-h-11` | **44px** |
| "Existing partner sign in" CTA | `min-h-11` | **44px** |

Stated precisely: all three **pass** WCAG 2.2 AA (SC 2.5.8, 24px) and **fail** the 48px brief and AAA SC 2.5.5 (44px, borderline). This is a brief violation, not an AA failure — don't misreport it.

### D3 — The form has no form semantics

Counts inside `RoleGuard.tsx`:

```
<label>            0      aria-describedby  0
autocomplete       0      aria-invalid      0
name=              0      role="alert"      0
focus-visible      0      maxLength         0
```

Every field is labelled by `placeholder` (which **vanishes on input**) plus an invisible `aria-label`. No `name` or `autocomplete`, so browser/password-manager autofill is dead — the single highest-leverage conversion feature on a 6-field B2B form. No `focus-visible` anywhere in the file, so keyboard users lose their position.

### D4 — The lead reference number is thrown away

`PartnerLeadOut` (`backend/app/schemas/brand.py:170`) returns `id`, `status`, `notification_status`, `duplicate`, `message`. The handler reads **only** `duplicate` and `message`:

```ts
setStatus({ type: "success", text: res.duplicate ? t(...) : res.message });
```

`res.id` never reaches the DOM. The partner walks away with no reference, no way to chase the request — and nothing discouraging a re-submit, which burns the rate limit in D6.

### D5 — A duplicate renders as success

Both branches set `type: "success"` → emerald panel. "We already have a recent request for this email" is **not** a success; it's a neutral/notice state. Styling it as one teaches the partner their second submission worked.

### D6 — The 5/hour ceiling is invisible

Two independent throttles exist and neither is surfaced:

- Route decorator: `@limiter.limit("5/hour")` → **429**
- Service: per-IP ≥5/hour → `ValidationDomainError("Too many partner-demo requests from this network. Please try again later.")`

A prospect's office behind one NAT egressing five requests **bricks the form for the whole building for an hour** — with no warning, no countdown, no explanation. This is the highest-severity UX defect on the page.

### D7 — One error path for four different failures

```ts
catch (err: any) { setStatus({ type:"error", text: err?.message || t('partner.submit_failed') }); }
```

Network drop, 422 validation, 429 throttle, and 503 collapse into one rose box. Each demands a different user action: fix a field / wait / retry / give up gracefully.

### D8 — No client/server validation parity

Server (`brand_controller.py:49-54`) enforces:

```python
re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email)     # 422
len(company_name.strip()) < 2  →  422
len(contact_name.strip())  < 2 →  422
```

Client enforces `required` + `type="email"`. A prospect who types `x` into Company gets a **full network round trip to discover a two-character rule**.

### D9 — The primary conversion action is below the fold

DOM order: `hero` → `2×2 feature grid` → **`<PartnerRequestDemoForm/>`** → `3-col pillars`. On a 900px viewport the form opens at roughly 1.5 viewports down. The one thing the page exists to produce is third in line.

### D10 — Register drift: two sources of truth for "partner"

`frontend/src/design/registers.ts` declares, with measured contrast:

```ts
partner: { accent: "#3E5C76", ink: "#35506A", labelKey: "registers.partner.label", scheme: "light" }
//   partner #35506A   7.96 / 8.38  (AAA)   — measured, CI-enforced
```

The implementation uses `#C5A059` gold on `#0C0E1E` navy and **never reads the register**. The file header explicitly warns that "/admin never resolves to the partner register and vice-versa — the two portals must stay visually distinguishable." That guarantee is currently unenforced on the public gateway.

### D11 — 31 hardcoded hex literals against existing tokens

Inside one file: `#C5A059` ×15, `#1B1F3B` ×6, `#0C0E1E` ×6, `#E2BF70` ×3, `#F43F5E` ×1. `tailwind.config.js` already ships `confit.navy.50…900` and `confit.gold.50…900`. **`#C5A059` is not in the gold scale at all** (DEFAULT `#B8935A`, 300 `#E2BF70`) — it is a rogue value with no token, used fifteen times.

### D12 — Three repetitive grids, seven copy blocks

```
hero            lg:grid-cols-[1.05fr_0.95fr]   ← arbitrary ratio, not 12-col
features        sm:grid-cols-2  → 4 identical cards
pillars         md:grid-cols-3  → 3 identical cards
```

**Nine identically-shaped containers render on this page** — 1 hero panel, 4 feature cards, 1 form card, 3 pillar cards. Seven of them come from just two `.map()` calls, which is why they are indistinguishable. This is precisely the "predictable, repetitive grid" the brief prohibits.

Measured copy load: **79 words of card body copy + 14 words of serif titles** across those 7 boxes. The strings themselves are short (8–15 words each) — the density comes from the *number of identical containers*, not from verbose copy. That distinction matters: the fix is structural, not a copy pass.

### D13 — Developer-facing copy leaked to prospects

| Key | Current value | Problem |
|---|---|---|
| `partner.submit` (en) | **"Submit real request"** | "real" is a dev artifact. No buyer reads that. |
| `partner.pillar_proof_copy` | "…are **never fabricated**." | Arguing with an accusation nobody made. |
| `partner.form_note` | "Signing up as a shopper does not grant partner access…" | Explaining internal auth architecture on a sales surface. |

### D14 — RTL arrow points backwards

`return_to_storefront` = `← Return to Consumer Storefront` (en) and `← العودة إلى واجهة المتسوقين` (ar). The glyph is **baked into both strings**. In RTL it points away from the reading direction. The repo already handles this correctly elsewhere — `RoleGuard` wraps Latin identifiers in `dir="ltr"` — so the pattern exists and was simply not applied.

### D15 — The primary CTA scrolls without moving focus

```ts
onClick={() => document.getElementById('partner-request')?.scrollIntoView({ behavior:'smooth' })}
```

Viewport moves; focus does not. A keyboard or screen-reader user is left reading the hero while the form sits off-screen below them. `aria-hidden` isn't the issue — **focus management is missing entirely**.

### D16 — `min-h-[80vh]` / `min-h-[70vh]` are magic numbers

**Two** distinct values across **four** usages: `min-h-[70vh]` ×3 and `min-h-[80vh]` ×1. Not tokens, not related to anything, and no reason given for the one 80vh outlier.

### D17 — Success destroys the user's input

`setForm({...all empty})` fires the instant the request resolves. The prospect cannot re-read what they submitted, and with no reference number (D4) they have no record at all.

### D18 — `min-h-11` on 2 of 3 CTAs, nothing on the third

Inconsistent target sizing within a single button group — evidence there is no `<Button>` primitive, only copy-pasted class strings.

---

## What is already correct — do not regress these

Honesty cuts both ways. These are real strengths:

- `motion-safe:animate-spin` — reduced-motion is respected on the bootstrap spinner.
- `role="status"` + `aria-live="polite"` on the message region.
- Colour is never the only signal — refusal badges *name* the state in text.
- `dir="ltr"` on email and role codes inside Arabic sentences.
- The bootstrap spinner (`!hasAttemptedBootstrap`) prevents the auth-wall flash — a documented AUTH-02 fix.
- The `portal` prop replaced title-sniffing — a documented regression fix with a comment explaining why.
- **Contrast is clean.** Measured with the WCAG relative-luminance formula:

  | Pair | Ratio |
  |---|---|
  | `#C5A059` on `#0C0E1E` | **7.79** |
  | `#E2BF70` on `#0C0E1E` | **10.86** |
  | `#CBD5E1` on `#0C0E1E` | **12.89** |
  | `#CBD5E1` on `#1B1F3B` | **10.83** |
  | `#64748B` on `#FFFFFF` | **4.76** |
  | `#94A3B8` on `#0C0E1E` | **7.46** |

  All AA, most AAA. **There is no contrast defect here** and I will not invent one.
- The backend correctly does *not* create an account, grant a role, or fake a CRM.

---

# PART 1 — Design System (DRY foundation)

Nothing gets built until these exist. Every component below consumes only these.

## 1.1 Tokens — `src/design/tokens.css`

```css
:root {
  /* ---- Surface: the page has three depths, never more ---- */
  --surface-0: #FAF9F6;   /* page      */
  --surface-1: #FFFFFF;   /* raised    */
  --surface-2: #0C0E1E;   /* editorial */

  /* ---- Ink — every ratio MEASURED (WCAG relative luminance) ----
       Chosen so the floor value clears AA on BOTH surfaces, not just one. */
  --ink-1: #0C0E1E;   /* 19.14 on #FFFFFF · 18.30 on #FAF9F6 */
  --ink-2: #4A4F63;   /*  8.11 on #FFFFFF */
  --ink-3: #616674;   /*  5.74 on #FFFFFF ·  5.45 on #FAF9F6  ← body-copy floor */
  --ink-inv-1: #FFFFFF;
  --ink-inv-2: #CBD5E1;
  /* #6B7080 was rejected for --ink-3: 4.94/4.69 — technically AA but with no
     margin, and it fails the moment a surface darkens slightly. */

  /* ---- Accent: ONE gold, promoted to a token ----
     HARD RULE, measured: gold is DECORATIVE-ONLY on light surfaces.
       #B8935A on #FFFFFF 2.85 · on #FAF9F6 2.71   ← fails AA, never text
       #B8935A on #0C0E1E 6.71 · on #1B1F3B 5.64   ← AA text, legal
     Gold may be a hairline, a dot, a focus halo, or text on navy. It may never
     be body text or a control label on white. The existing code obeys this by
     accident (it only paints gold on #0C0E1E); this token makes it explicit. */
  --accent:      #B8935A;  /* confit.gold.DEFAULT */
  --accent-hi:   #D4AF37;  /* confit.gold.400 */
  --accent-soft: rgba(184,147,90,.14);
  /* #C5A059 is retired. It was never in the scale (D11). */

  /* ---- Partner register — read from registers.ts, not re-typed (D10) ---- */
  --register-accent: #3E5C76;
  --register-ink:    #35506A;

  /* ---- Spacing: 4px base, no arbitrary values ---- */
  --sp-1:4px;  --sp-2:8px;  --sp-3:12px; --sp-4:16px; --sp-5:24px;
  --sp-6:32px; --sp-7:48px; --sp-8:64px; --sp-9:96px; --sp-10:128px;

  /* ---- Radius: 4 values total ---- */
  --r-sm:8px; --r-md:14px; --r-lg:20px; --r-pill:999px;
  /* rounded-3xl / rounded-[36px] / rounded-2xl / rounded-xl are all retired. */

  /* ---- Shadow: replaces the 106 dead declarations (D1) ---- */
  --shadow-hair: 0 1px 2px rgba(12,14,30,.04);
  --shadow-sm:   0 2px 8px -2px rgba(12,14,30,.08);
  --shadow-md:   0 12px 32px -12px rgba(12,14,30,.16);
  --shadow-float:0 24px 64px -24px rgba(12,14,30,.24);

  /* ---- Motion: one luxury curve, three durations ---- */
  --ease-lux:   cubic-bezier(0.25, 1, 0.5, 1);
  --ease-soft:  cubic-bezier(0.16, 1, 0.3, 1);
  --dur-fast: 140ms;
  --dur-base: 260ms;
  --dur-slow: 520ms;

  /* ---- The hard floor that fixes D2/D18 globally ---- */
  --tap-min: 48px;

  /* ---- 12-column grid ---- */
  --gutter: 24px;
  --maxw: 1280px;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
}
```

## 1.2 Component primitives — one implementation each

| Primitive | Kills | Enforces |
|---|---|---|
| `<Field>` | 5 duplicated input class strings, D3 | `<label htmlFor>`, `aria-describedby`, `aria-invalid`, hint + error slots, autofill |
| `<Button variant size>` | 3 hand-rolled CTAs, D2, D18 | `min-height: var(--tap-min)`, focus-visible ring, `loading`/`disabled` states |
| `<Reveal>` | ad-hoc animation per site | one curve, one stagger, reduced-motion escape |
| `<Skeleton>` | no loading state, D-region | geometry-matched shimmer |
| `<SectionEyebrow>` | inline badge markup | reads `registers.partner` (D10) |
| `<StatusPanel tone>` | D5, D7 | `success`/`notice`/`error`/`throttled`, `role="alert"` on error only |

**Structural move (SRP):** `PartnerRequestDemoForm` and the whole partner marketing surface come **out of `RoleGuard.tsx`** into `src/views/b2b/PartnerGatewayView.tsx`. A route guard currently owns a 300-line marketing page plus a lead-capture form. That is the root cause of D9 and D12 — the layout was shaped by where the code happened to live.

---

# PART 2 — Section-by-section redesign

Five tiers. **No two share a presentation style.** That asymmetry is the point.

```
┌─────────────────────────────────────────────────────────┐
│ TIER 1  Editorial masthead — 7/12 + sticky form 5/12     │  ← form ABOVE the fold
├─────────────────────────────────────────────────────────┤
│ TIER 2  Capability ledger — hairline rule, no cards      │  ← horizontal, editorial
├─────────────────────────────────────────────────────────┤
│ TIER 3  Proof band — 16:9 media, offset caption          │  ← cinematic, asymmetric
├─────────────────────────────────────────────────────────┤
│ TIER 4  Stacked tiers — 3 accordions, not 3 cards        │  ← progressive disclosure
├─────────────────────────────────────────────────────────┤
│ TIER 5  Close — single CTA + text link, no card          │  ← negative space
└─────────────────────────────────────────────────────────┘
```

---

## TIER 1 — Editorial masthead + sticky capture

**Structural change.** Current: `lg:grid-cols-[1.05fr_0.95fr]` with a 2×2 card block inside, form third in the DOM. New: a true 12-column grid, **7/5 split**, form **second in the DOM and sticky**.

```jsx
<section className="grid grid-cols-12 gap-[var(--gutter)] max-w-[var(--maxw)] mx-auto
                    px-[var(--sp-5)] pt-[var(--sp-9)] pb-[var(--sp-8)]">
  {/* cols 1–7 — masthead, ragged right, left-aligned */}
  <div className="col-span-12 lg:col-span-7 flex flex-col justify-between min-h-[420px]">
    <SectionEyebrow register="partner" />
    <h1 className="font-serif text-[clamp(2.5rem,6vw,4.5rem)] leading-[0.98]
                   tracking-[-0.02em] text-[var(--ink-1)]">
      {t('partner.hero_title')}
    </h1>
    <p className="max-w-[46ch] text-[var(--ink-3)] text-[1.0625rem] leading-[1.65]">
      {t('partner.hero_body_short')}   {/* rewritten — see §4 */}
    </p>
  </div>

  {/* cols 8–12 — the conversion surface, sticky on desktop */}
  <div className="col-span-12 lg:col-span-5">
    <div className="lg:sticky lg:top-[var(--sp-6)]">
      <LeadForm />
    </div>
  </div>
</section>
```

**`justify-between` on the masthead** — explicitly required by the brief. Headline and supporting copy are variable-length strings that change radically between EN and AR (Arabic runs ~30% longer). Distributing them against a fixed `min-h` means an Arabic translation cannot collapse or overflow the column. **The form column is deliberately not stretched** — it stays top-aligned so it never resizes under the sticky offset.

**Visual alterations**
- `hero_body` is already 22 words — **length is not the problem**, so do not "shorten" it. The problem is that it is abstract: *"connects premium catalog ingestion, fit intelligence, and virtual try-on workflows so brand teams can understand the partner workflow"* describes the product describing itself. Rewrite for a concrete outcome, at the same length. (`partner.hero_body_short` in §1 above is a new key, not a truncation.)
- 2×2 feature grid **deleted from Tier 1**. It moves to Tier 2 in a completely different form.
- `portal_badge` becomes `<SectionEyebrow>`: a 1px `--register-accent` rule + uppercase micro-label, sourced from `registers.ts`.
- Headline uses `clamp()` fluid type instead of the `text-4xl sm:text-5xl` breakpoint jump.

**Presentation style:** editorial masthead — asymmetric 7/12 text column against a 5/12 utility column. Deliberately not centred, not a hero-with-badge.

### `<LeadForm>` — the conversion instrument

```jsx
<form onSubmit={submit} noValidate id="partner-request" aria-labelledby="lead-form-title"
      className="rounded-[var(--r-lg)] bg-[var(--surface-1)] p-[var(--sp-5)]
                 border border-[var(--surface-0)] shadow-[var(--shadow-md)]
                 flex flex-col gap-[var(--sp-4)]">
  <header className="flex flex-col gap-[var(--sp-1)]">
    <h2 id="lead-form-title" className="font-serif text-[1.375rem] text-[var(--ink-1)]">
      {t('partner.form_title')}
    </h2>
    <p className="text-[0.8125rem] text-[var(--ink-3)]">{t('partner.form_hint')}</p>
  </header>

  <Field name="company_name" autoComplete="organization" required minLength={2} />
  <div className="grid sm:grid-cols-2 gap-[var(--sp-3)]">
    <Field name="contact_name" autoComplete="name" required minLength={2} />
    <Field name="work_email" type="email" autoComplete="email" required />
  </div>
  <Field name="website" autoComplete="url" inputMode="url" optional />
  <Field name="monthly_order_volume" as="select" options={VOLUME_OPTIONS} />
  <Field name="message" as="textarea" rows={3} maxLength={600} counter />

  <Button type="submit" variant="primary" loading={submitting} block>
    {submitting ? t('partner.submitting') : t('partner.submit')}
  </Button>

  {state && <StatusPanel {...state} />}
</form>
```

**Functional requirements**
1. Client-side rules mirror the server exactly (D8): email regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`, `minLength: 2` on company + contact. Invalid submit → inline field errors, **zero network calls**.
2. `noValidate` on `<form>` so the custom validation owns the messaging instead of two competing systems.
3. Error taxonomy (D7) — four distinct states, each with its own recovery affordance:

   | Status | Trigger | Panel | Action offered |
   |---|---|---|---|
   | `field-error` | client validation | per-field, `aria-invalid` + `aria-describedby` | focus first invalid |
   | `422` | server validation | `StatusPanel tone="error"` | highlight returned field |
   | `429` / IP-throttle | `@limiter.limit("5/hour")` or service `ValidationDomainError` | `tone="throttled"`, `role="alert"` | **"Email us directly instead"** + `mailto:` |
   | `network` / `503` | fetch throw / 5xx | `tone="error"` | "Retry" + preserve input |

4. **Success renders the lead reference** (D4): `res.id` shown as `CONFIT-<id>`, plus `res.status`. Copy: *"Request <ref> received. Our partnerships team reviews leads within one business day."*
5. **Input is preserved on success** (D17) — the panel replaces the fields but a "Submit another request" affordance reveals the form again with values intact.
6. **Duplicate is `tone="notice"`, not success** (D5) — amber, neutral, with the reference of the earlier request.
7. **Rate-limit pre-warning** (D6): `localStorage` counts this browser's submissions. At 4 of 5, a `notice` panel appears *before* submit: *"You've sent 4 requests this hour. Direct email is faster."* This is a client-side courtesy — the server remains authoritative.
8. `source_path: '/b2b'` retained.

**Non-functional requirements**
- **Touch:** every control ≥ `var(--tap-min)` = 48px (fixes D2/D18 by construction, not by remembering `min-h-11`).
- **Cognitive load:** 6 fields, one primary action, zero decorative chrome. No hero badge competing inside the card.
- **Perceived performance:** optimistic button state at 0ms; `loading` swaps label to `Submitting…` with a 14px inline spinner, `transition: var(--dur-fast)`.
- **Accessibility:** real `<label htmlFor>` on every field (fixes D3); `aria-invalid` + `aria-describedby="<id>-error"` wired on failure; `role="alert"` on error panels only, `role="status"` on success/notice; focus moves to the first invalid field on a failed submit.
- **Autofill:** `autoComplete` on all 5 typed fields — the biggest single conversion lift available on this page.
- **Fluidity:** the two-column name/email pair collapses to one column under `sm` without any alignment break.

**Motion specs**

| Element | Property | Duration | Easing |
|---|---|---|---|
| Card entrance | `y: 16→0`, `opacity 0→1` | `var(--dur-slow)` | `var(--ease-lux)` |
| Field focus | `border-color`, `box-shadow: 0 0 0 3px var(--accent-soft)` | 180ms | `var(--ease-lux)` |
| Button hover | `background-color` only | `var(--dur-fast)` | `var(--ease-lux)` |
| Button active | `transform: translateY(1px)` | 80ms | `linear` |
| focus-visible | `outline: 2px solid var(--register-accent); outline-offset: 2px` | 160ms | `var(--ease-lux)` |
| Error text | `opacity 0→1` | 200ms | `var(--ease-lux)` |
| Panel swap | `height` + `opacity` | `var(--dur-base)` | `var(--ease-soft)` |

**Explicitly rejected:** `scale` on the primary CTA (reads cheap on a conversion action), and error "shake" animations (a shaking form blames the user).

---

## TIER 2 — Capability ledger

**Structural change.** The four identical `sm:grid-cols-2` cards become a **single horizontal rule-separated strip**. No cards, no borders, no backgrounds.

```jsx
<section className="border-y border-[var(--surface-0)] bg-[var(--surface-1)]">
  <ul className="max-w-[var(--maxw)] mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4
                 divide-y sm:divide-y-0 sm:divide-x divide-[var(--surface-0)]">
    {CAPABILITIES.map((c) => (
      <li key={c.key} className="px-[var(--sp-5)] py-[var(--sp-6)] flex flex-col gap-[var(--sp-2)]">
        <span className="font-mono text-[0.6875rem] tracking-[0.14em] uppercase
                         text-[var(--register-accent)]">{c.index}</span>
        <h3 className="font-serif text-[1.125rem] text-[var(--ink-1)]">{t(c.title)}</h3>
        <p className="text-[0.875rem] leading-[1.6] text-[var(--ink-3)]">{t(c.copy)}</p>
      </li>
    ))}
  </ul>
</section>
```

**Presentation style:** editorial index / ledger. Hairline dividers carry the structure instead of card chrome — this is the "minimalist but deep" instruction applied literally. The mono numeral (`01`–`04`) is the only ornament.

**Visual alterations:** none to the copy. Measured, the four `feat_*_copy` strings are 10 / 8 / 11 / 10 words — **already tight**. Do not shorten them.

The density problem on this page is **container count, not string length**: 4 feature copies + 3 pillar copies = **79 words of body copy plus 7 serif titles**, all inside 7 identically-shaped boxes. Individual strings are fine; seven identical boxes is the fluff. That is why the fix here is structural (hairline ledger) and in Tier 4 (accordion), and not a copy pass.

**FR:** static content; `sm:divide-x` flips to `divide-y` on mobile so the rule always runs perpendicular to the scroll axis.
**NFR:** zero elevation change means zero layout shift; `--ink-3` at 5.2:1 keeps the copy AA-compliant while receding visually behind the serif titles (clear typographic hierarchy without weight stacking).

**Motion:** `<Reveal>` stagger `0.06s`, `y: 12→0`, `viewport={{ once: true, amount: 0.3 }}`.

---

## TIER 3 — Proof band

**Structural change.** Replaces the second half of the hero's 2×2 block with a **single 16:9 media panel and an offset caption**, deliberately unbalanced.

```jsx
<section className="max-w-[var(--maxw)] mx-auto px-[var(--sp-5)] py-[var(--sp-9)]">
  <div className="grid grid-cols-12 gap-[var(--gutter)] items-center">
    <figure className="col-span-12 lg:col-span-8 lg:col-start-1">
      <div className="aspect-[16/9] lg:aspect-[16/9] max-lg:aspect-[4/5]
                      rounded-[var(--r-lg)] overflow-hidden bg-[var(--surface-0)]">
        {/* Skeleton until loaded; see motion table */}
      </div>
    </figure>
    {/* offset: starts on col 9 but bleeds 1 col left on lg — intentional overlap */}
    <figcaption className="col-span-12 lg:col-span-4 lg:-ml-[var(--sp-6)]
                           bg-[var(--surface-1)] p-[var(--sp-6)]
                           rounded-[var(--r-lg)] shadow-[var(--shadow-md)]">
      <span className="block w-8 h-px bg-[var(--register-accent)] mb-[var(--sp-4)]" />
      <blockquote className="font-serif text-[1.25rem] leading-[1.4] text-[var(--ink-1)]">
        {t('partner.proof_quote')}
      </blockquote>
    </figcaption>
  </div>
</section>
```

**Presentation style:** cinematic. `aspect-[16/9]` on desktop for the narrative sweep, `aspect-[4/5]` on mobile where a portrait crop holds attention in a vertical scroll. The caption **overlaps the media by `--sp-6`** (`lg:-ml`) — an offset structural layout, not a grid cell.

**NFR — media states (required by the brief):**
- `<Skeleton>` with the figure's exact radius and aspect ratio, so the swap is zero-shift.
- Shimmer: `background-position` sweep, `1.6s linear infinite`, gradient stops matched to `--surface-0`.
- `loading="lazy"` + `decoding="async"`; explicit `width`/`height` attributes so CLS stays 0.
- Contextual zoom on hover: `scale(1.03)`, `var(--dur-slow)`, `var(--ease-lux)`, `overflow-hidden` on the parent. Disabled under reduced motion.
- Decorative-only image gets `alt=""`.

**FR:** the panel is presentational; it must not carry a claim the analytics cannot support (the repo's `pillar_proof_copy` already commits to never fabricating metrics — this redesign keeps that promise by using no metric at all here).

---

## TIER 4 — Stacked tiers (progressive disclosure)

**Structural change.** The three identical `md:grid-cols-3` pillar cards — the block with the dead `shadow-2xs` (D1) — become **three accordion rows**. This is the single largest reduction in content density on the page.

```jsx
<section className="max-w-[var(--maxw)] mx-auto px-[var(--sp-5)] pb-[var(--sp-9)]">
  <div className="border-t border-[var(--surface-0)]">
    {PILLARS.map((p, i) => (
      <div key={p.key} className="border-b border-[var(--surface-0)]">
        <h3>
          <button
            aria-expanded={open === i}
            aria-controls={`pillar-panel-${i}`}
            id={`pillar-trigger-${i}`}
            onClick={() => setOpen(open === i ? null : i)}
            className="w-full min-h-[var(--tap-min)] py-[var(--sp-5)] flex items-center
                       justify-between gap-[var(--sp-4)] text-left group"
          >
            <span className="font-serif text-[1.25rem] text-[var(--ink-1)]
                             group-hover:text-[var(--register-ink)]
                             transition-colors duration-[var(--dur-fast)] ease-[var(--ease-lux)]">
              {t(p.title)}
            </span>
            <ChevronDown className="shrink-0 transition-transform duration-[var(--dur-base)]
                                    ease-[var(--ease-soft)]"
                         style={{ rotate: open === i ? '180deg' : '0deg' }} />
          </button>
        </h3>
        <AnimatePresence initial={false}>
          {open === i && (
            <motion.div id={`pillar-panel-${i}`} role="region"
                        aria-labelledby={`pillar-trigger-${i}`}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}>
              <p className="pb-[var(--sp-5)] max-w-[62ch] text-[0.9375rem]
                            leading-[1.7] text-[var(--ink-3)]">{t(p.copy)}</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    ))}
  </div>
</section>
```

**Presentation style:** stacked interactive tiers. Three hairline-separated rows replacing three floating cards — measured density drops from **46 words visible to 17** (three titles + three copies → one title + one copy), with the remaining depth available on demand.

**FR:** one panel open at a time (`open === i ? null : i`); `aria-expanded` / `aria-controls` / `role="region"` fully wired; state is URL-independent so it survives nothing and needs no hydration.
**NFR:** trigger is `min-h: var(--tap-min)` and full-width — the entire row is the target, not the chevron. Reduced-motion collapses the height animation to an instant swap via the global media query.

**Motion:** `height: auto` 320ms `cubic-bezier(0.16, 1, 0.3, 1)`; chevron rotate 260ms same curve; title colour 140ms.

---

## TIER 5 — Close

**Structural change.** No card, no border, no background. A single centred CTA in negative space, with the sign-in path demoted to a text link.

```jsx
<section className="max-w-[var(--maxw)] mx-auto px-[var(--sp-5)]
                    py-[var(--sp-10)] text-center flex flex-col items-center gap-[var(--sp-4)]">
  <Button variant="primary" size="lg" onClick={scrollToForm}>
    {t('partner.request_partnership')}
  </Button>
  <button onClick={() => openAuthModal('login')}
          className="min-h-[var(--tap-min)] px-[var(--sp-4)] text-[0.875rem]
                     text-[var(--ink-3)] hover:text-[var(--register-ink)]
                     underline underline-offset-4 decoration-[var(--accent)]
                     transition-colors duration-[var(--dur-fast)] ease-[var(--ease-lux)]">
    {t('partner.existing_sign_in')}
  </button>
</section>
```

**`scrollToForm` fixes D15** — it scrolls *and* moves focus:

```ts
const scrollToForm = () => {
  const el = document.getElementById('partner-request');
  if (!el) return;
  el.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center' });
  // Focus must follow the viewport or keyboard/AT users are left behind.
  el.querySelector('input, select, textarea')?.focus({ preventScroll: true });
};
```

`preventScroll: true` prevents a double-scroll fight between `scrollIntoView` and `focus()`.

---

# PART 3 — KPI mapping

| Change | KPI | Mechanism |
|---|---|---|
| Form moved above the fold, sticky (D9) | **Demo-request conversion** | Zero scroll to reach the conversion instrument |
| `autoComplete` on 5 fields (D3) | **Form completion rate** | Removes retyping friction on mobile |
| Client/server validation parity (D8) | **Form abandonment** | No wasted round trip to learn a 2-char rule |
| Lead reference `CONFIT-<id>` (D4) | **Repeat submissions ↓** | Prospect has a record; no reason to resend |
| Rate-limit pre-warning + mailto escape (D6) | **Dead-end bounce ↓** | The 5/hour wall becomes a routed alternative, not a dead end |
| Accordion tiers (D12) | **Cognitive load / dwell** | 46 words → 17 visible; depth on demand |
| Skeletons matched to geometry | **CLS / perceived performance** | Zero-shift media and content loads |
| Register alignment (D10) | **Brand trust** | One partner identity, CI-enforced contrast |

---

# PART 4 — Copy corrections

| Key | Now | Replace with | Why |
|---|---|---|---|
| `partner.submit` (en) | "Submit real request" | **"Request partnership review"** | "real" is a developer artifact (D13) |
| `partner.pillar_proof_copy` | "…are never fabricated." | State the capability positively | Don't answer an accusation |
| `partner.form_note` | Explains shopper-vs-partner auth | **"Reviewed by our partnerships team within one business day."** | Prospect needs an expectation, not architecture |
| `partner.hero_body` | 22 words, abstract | Same length, concrete outcome | Length is fine; it describes the product describing itself |
| `partner.return_to_storefront` | `← …` baked into en **and** ar | Drop the glyph; use a logical-property icon | Points backwards in RTL (D14) |

**RTL fix (D14):** never hardcode directional glyphs in translation strings.

```jsx
<ArrowLeft className="rtl:rotate-180 transition-transform" aria-hidden="true" />
<span>{t('partner.return_to_storefront')}</span>  // string carries no arrow
```

---

# PART 5 — Implementation order

Each step is independently shippable and verifiable.

1. **`src/design/tokens.css`** — the token layer. Zero visual change, no component touched.
2. **`<Button>` + `<Field>`** — unit-test that every rendered control measures ≥ 48px. *Closes D2, D18.*
3. **`shadow-2xs`/`shadow-xs` sweep** — repo-wide, 106 sites, mapped to `--shadow-hair`/`--shadow-sm`. *Closes D1.*
4. **Extract `PartnerGatewayView.tsx`** out of `RoleGuard.tsx`; guard returns the view, owns no layout. *Closes D9 at the root.*
5. **`<LeadForm>`** with validation parity, error taxonomy, reference number, duplicate-as-notice. *Closes D3, D4, D5, D7, D8.*
6. **Rate-limit affordance** — client counter + `mailto:` escape. *Closes D6.*
7. **Tiers 2–5** in order, each with its `<Reveal>` and reduced-motion path. *Closes D12.*
8. **Register wiring** — `<SectionEyebrow>` reads `registers.partner`; add a test asserting the public gateway resolves to the partner register, never admin. *Closes D10.*
9. **Copy + RTL pass.** *Closes D13, D14.*
10. **Focus management** on the CTA. *Closes D15.*

---

# PART 6 — Acceptance criteria

Measurable, not vibes.

- [ ] `grep -rn "shadow-2xs\|shadow-xs" frontend/src` → **0 results**
- [ ] `grep -rn "#C5A059" frontend/src` → **0 results**
- [ ] Every `<button>`, `<input>`, `<select>` in `PartnerGatewayView` computes `offsetHeight >= 48`
- [ ] Every `<input>` has a sibling `<label htmlFor>` and a non-empty `autocomplete` where a token applies
- [ ] Submitting `company_name: "x"` produces an inline error and **zero** network requests (assert with `vi.fn()` on the fetch)
- [ ] A `429` renders `tone="throttled"` with a working `mailto:` — not the generic error string
- [ ] A `201` with `duplicate: true` renders `tone="notice"`, **not** `tone="success"`
- [ ] A `201` renders `res.id` in the DOM
- [ ] No two adjacent sections share a presentation pattern (ledger / cinematic / accordion / close)
- [ ] `prefers-reduced-motion: reduce` → no transform or height animation executes
- [ ] Lighthouse a11y ≥ 98; CLS = 0 on the media panel
- [ ] EN and AR both render without overflow at 320px, 768px, 1280px, 1440px
- [ ] All contrast pairs ≥ 4.5:1 (baseline already passes — this is a no-regression gate)
- [ ] **No gold (`--accent`, `--accent-hi`, or any `confit.gold.*`) used as text or control label on a light surface.** Measured ceiling is 2.85:1 on `#FFFFFF` and 2.71:1 on `#FAF9F6` — decorative use only. Gold text is legal solely on `#0C0E1E` (6.71:1) or `#1B1F3B` (5.64:1).
- [ ] `--ink-3` never drops below 5.4:1 on any surface it is placed on

---

*Baseline verified against `RoleGuard.tsx` and the `/brand/request-demo` contract. Every defect cites a line, a build output, or a computed measurement. Where the existing code is already correct — contrast, reduced-motion handling, bootstrap guard, backend honesty — that is recorded rather than reinvented.*

---

# Pass 2 — audit of the page AS REBUILT (2026-10-08)

Pass 1 critiqued the page that shipped inside `RoleGuard.tsx`. All 18 of its
defects were fixed and merged. This pass re-measures the **current** code
rather than restating the old findings, and separates what is genuinely sound
from what still fails.

## Measured sound — no action taken, and none invented

| Property | Measurement |
| --- | --- |
| Motion spec | `cubic-bezier(0.25, 1, 0.5, 1)` throughout; reveal 0.52s, stagger 0.06s, gated on `prefers-reduced-motion` |
| Touch targets | 8× `min-h-[48px]` + `min-h-12` across the gateway, form, `Field`, `StatusPanel` — zero `min-h-11` in scope (the 31 in `views/b2b/` are the admin/brand screens, out of scope) |
| Content density | 207 words total across 5 tiers; ledger 46 words / 3 rows, pillars 47 / 4 — no text stuffing to remove |
| Text contrast | navy on cream 15.28 · navy on white 16.08 · slate-600 7.58 · white on navy 16.08 · gold on deep navy 6.71 — all AA |
| Grid | 12-column with `justify-between` on the masthead column for variable string length, as specified |

## D19 — a skeleton that never resolves

Tier 3's "media" wore `skeleton-shimmer` over a gradient, with no image behind
it. `confit-shimmer` is declared `infinite` (`styles/index.css:178`), so the
page animated a **loading state forever**: a permanent repaint in service of a
promise nothing intended to keep. Beside it, `hover:scale-[1.03]` was a
contextual zoom with nothing to zoom.

Fix: both removed. What remains is presented honestly as a decorative brand
surface in the register's own three colours, keeping the intended 4:5 mobile /
16:9 desktop aspect ratios and signing itself with the existing
`partner.portal_badge` key — no new copy, no new i18n key.

## D20 — `text-slate-400` fails AA in three places (2.56:1)

Introduced by the pass-1 rebuild, not pre-existing. WCAG 2.2 AA asks 4.5:1 for
text and 3:1 for non-text UI (1.4.11); 2.56:1 fails both.

| Site | Why it matters | Fix |
| --- | --- | --- |
| `PartnerGatewayView` accordion chevron | the visual expanded/collapsed cue | `text-slate-500` (4.76:1) + `group-hover` to register ink |
| `Field` character counter, 11px | real information at the smallest size on the page | `text-slate-500`; kept `aria-hidden` deliberately — a live "n / 600" on every keystroke is noise, and the limit is enforced by `maxLength` and stated in the label |
| `Field` `placeholder:text-slate-400` | **shared primitive** — the failure shipped to every form in the app | `placeholder:text-slate-500` |

After the fix: 0 occurrences of `text-slate-400` in the four B01 files, and
every text pair measures ≥ 4.52:1.

## Verification

`npm run verify` exit 0 (i18n gate, `tsc --noEmit`, 92/92 test files, `vite
build`). `e2e_partner_gateway_goals.py --phase main` 44/44 steps — unchanged,
confirming the visual pass did not move behaviour.
