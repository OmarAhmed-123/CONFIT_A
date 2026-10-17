import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Floating AI Stylist control: the non-occlusion contract.
 *
 * WHY THESE CONTRACTS CHANGED (2026-10-17)
 * ----------------------------------------
 * The previous contract asserted only a position (`bottom: 1rem`, raised to
 * `5rem` under a sticky CTA) plus `html { scroll-padding-bottom }`.
 * scripts/fab_probe.mjs measured the result in a real browser and found 15
 * covered elements across 6 routes x 2 viewports, five of them interactive:
 * the /builder "Outfit name" input and occasion <select>, the /fit
 * "in / lbs" toggle, the /cart "Store Pickup (BOPIS)" button and a /wardrobe
 * card link — all at 390px.
 *
 * scroll-padding-bottom cannot fix that: it only moves browser-driven FOCUS
 * scrolling, and does nothing for a control already in the viewport or for
 * pointer input. The guarantee is now structural and has two halves:
 *
 *   1. FLOW RESERVATION — the shell's <main> spends --fab-safe-bottom as
 *      padding-bottom, so the last block of any page scrolls clear.
 *   2. SCROLL DEFERENCE — the anchor carries data-fab-hidden while the user
 *      scrolls down, and drops it on scroll up or on a route change.
 *
 * Both halves are asserted here so neither can be removed quietly. The
 * browser-level check is scripts/fab_probe.mjs (see coverage doc).
 */
const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');
const layout = read('src/layouts/ConsumerLayout.tsx');
const css = read('src/styles/index.css');
const pdp = read('src/views/consumer/ProductDetailView.tsx');
const showcases = read('src/components/showcase/DesignShowcases.tsx');

describe('floating AI Stylist control: mobile overlap contract', () => {
  it('mobile footprint is an icon-only 48px circle; the pill returns at sm', () => {
    expect(layout).toMatch(/h-12 w-12[^"]*sm:h-auto sm:w-auto sm:px-5 sm:py-3/);
  });

  it('keeps the accessible name on the button', () => {
    expect(layout).toMatch(/aria-label=\{t\('layout\.ai_stylist_director'\)\}/);
  });

  it('anchor uses the position class the CSS rules target', () => {
    expect(layout).toContain('stylist-fab-anchor');
    expect(css).toMatch(/\.stylist-fab-anchor\s*\{\s*bottom:\s*var\(--fab-offset\)/);
  });

  it('declares the size / offset / reserved-space variables the contract is built on', () => {
    expect(css).toMatch(/--fab-offset:\s*1rem/);
    // reservation = offset above + footprint + offset below
    expect(css).toMatch(/--fab-safe-bottom:\s*calc\(var\(--fab-offset\)\s*\*\s*2\s*\+\s*var\(--fab-size\)\)/);
  });

  it('PDP sticky CTA is marked and raises BOTH the anchor and the reservation', () => {
    expect(pdp).toContain('data-sticky-cta');
    // raising --fab-offset raises the anchor and --fab-safe-bottom together,
    // so the two can never disagree about how much space is needed.
    expect(css).toMatch(/body:has\(\[data-sticky-cta\]\)\s*\{\s*--fab-offset:\s*5rem;?\s*\}/);
  });

  /* ── half 1: flow reservation ─────────────────────────────────────── */
  it('the shell reserves the control\'s band as padding on <main>', () => {
    expect(layout).toMatch(/pb-\[var\(--fab-safe-bottom\)\]/);
  });

  /* ── half 2: scroll deference ─────────────────────────────────────── */
  it('anchor carries data-fab-hidden, driven by scroll direction', () => {
    expect(layout).toMatch(/data-fab-hidden=\{fabHidden \? 'true' : 'false'\}/);
    expect(layout).toMatch(/addEventListener\('scroll', onScroll, \{ passive: true \}\)/);
  });

  it('hiding the anchor takes it out of hit-testing AND the tab order', () => {
    // pointer-events alone would leave it focusable by keyboard.
    expect(css).toMatch(/\.stylist-fab-anchor\[data-fab-hidden='true'\][\s\S]*?visibility:\s*hidden/);
    expect(css).toMatch(/\.stylist-fab-anchor\[data-fab-hidden='true'\][\s\S]*?pointer-events:\s*none/);
  });

  it('a route change restores the control so it can never be unreachable', () => {
    // Both deferral reasons are cleared, not just the scroll one.
    expect(layout).toMatch(
      /useEffect\(\(\) => \{\s*setScrollHidden\(false\);\s*setFocusHidden\(false\);\s*\}, \[location\.pathname\]\)/,
    );
  });

  it('focus deference: the control steps aside when focus lands under it', () => {
    // scroll-padding-bottom only covers BROWSER-driven focus scrolling; this
    // covers click focus, programmatic focus and elements already in view.
    expect(layout).toMatch(/addEventListener\('focusin', onFocusIn\)/);
    expect(layout).toMatch(/const fabHidden = scrollHidden \|\| focusHidden;/);
  });

  it('reduced motion removes the animation without leaving the control on top', () => {
    // Suppressing the transform instead would keep an invisible control
    // geometrically over the page — the defect this block exists to remove.
    expect(css).toMatch(/prefers-reduced-motion:\s*reduce[\s\S]*?transition:\s*none/);
    expect(css).toMatch(/\.stylist-fab-anchor\[data-fab-hidden='true'\][\s\S]*?transform:\s*translateY/);
  });

  it('shared showcase component carries no legacy gold, navy, cream or slate tokens', () => {
    for (const re of [/C5A059/i, /FDF8EE/i, /7A5C28/i, /1B1F3B/i, /A37E44/i, /slate-\d+/, /FAF9F6/i]) {
      expect(showcases, `DesignShowcases still has ${re}`).not.toMatch(re);
    }
  });
});
