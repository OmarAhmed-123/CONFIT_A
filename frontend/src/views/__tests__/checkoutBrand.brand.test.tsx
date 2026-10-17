/**
 * Checkout brand contract (Logo #3). Source contracts; browser evidence is in
 * docs/brand/logo-3-migration-coverage.md.
 *  - No legacy gold, navy, cream or slate tokens remain in CheckoutView.
 *  - Semantic success/warning/error colours are preserved (not recoloured to brand).
 *  - Dark-filled controls carry the white-offset focus treatment (.focus-on-light-fill).
 *  - Error feedback keeps role="alert".
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const src = readFileSync(resolve(process.cwd(), 'src/views/consumer/CheckoutView.tsx'), 'utf8');
const css = readFileSync(resolve(process.cwd(), 'src/styles/index.css'), 'utf8');

describe('Checkout brand contract', () => {
  it('has no legacy gold, navy, cream or slate tokens', () => {
    const legacy = /#C5A059|#A37E44|#1B1F3B|#0C0E1E|#FDF8EE|#FAF9F6|\b(?:bg|text|border|ring|accent)-slate-\d+|border-slate-\d+\/\d+/i;
    const hits = src.split('\n').filter((l) => legacy.test(l));
    expect(hits).toEqual([]);
  });

  it('keeps semantic success/warning/error colours', () => {
    expect(src).toMatch(/text-rose-600/);
    expect(src).toMatch(/text-amber-600|bg-amber-50/);
    expect(src).toMatch(/border-rose-400|bg-rose-50/);
  });

  it('gives every dark-filled control the light-surface focus treatment (.focus-on-light-fill)', () => {
    const lines = src.split('\n');
    const darkButtons = lines.filter((l) => /bg-brand-charcoal/.test(l) && /(className=|'focus-on-light-fill|focus-on-light-fill)/.test(l) && !/hover:bg-brand-wash/.test(l));
    // Rest-state dark fill only: a light button that turns charcoal on hover (bg-brand-wash) keeps a charcoal ring on a light surface.
    const offenders = darkButtons.filter((l) => /(^|\s)bg-brand-charcoal(\s|")/.test(l) && /(rounded-xl|rounded-2xl|rounded-lg|rounded-full)/.test(l) && !/focus-on-light-fill/.test(l) && !/w-11 h-11/.test(l) && !/bg-brand-wash/.test(l));
    expect(offenders).toEqual([]);
  });

  it('defines the light-surface focus ring: charcoal, outside the control, not white', () => {
    const rule = css.match(/\.focus-on-light-fill:focus-visible\s*\{([^}]*)\}/);
    expect(rule).not.toBeNull();
    expect(rule![1]).toMatch(/#252729/);
    expect(rule![1]).toMatch(/outline-offset:\s*3px/);
    expect(rule![1]).not.toMatch(/#fff/i);
    expect(rule![1]).not.toMatch(/box-shadow/);
  });

  it('keeps the field error alert and the promo error alert', () => {
    expect(src).toMatch(/id="guest-email-error" role="alert"/);
    expect(src).toMatch(/promoError && <p role="alert"/);
  });

  it('reflows the summary beside the header at lg (clear of the fixed AI Stylist footprint)', () => {
    // Measured: summary was y 556-929 (overlapping the control at 762-812 / 718-768).
    // Now y 198-571 at 1024 and 1280. Source contract for the reflow.
    expect(src).toMatch(/className="space-y-8 lg:space-y-0 lg:grid lg:grid-cols-12 lg:gap-8 lg:items-start pb-24 max-w-5xl mx-auto"/);
    expect(src).toMatch(/className="grid grid-cols-1 gap-8 lg:contents"/);
    expect(src).toMatch(/lg:col-span-5 lg:col-start-8 lg:row-start-1 lg:row-span-3/);
  });

  it('keeps the Place order submit button inside the form (DOM and tab order preserved)', () => {
    const formStart = src.indexOf('<form noValidate onSubmit={handleSubmitOrder}');
    const formEnd = src.indexOf('</form>', formStart);
    expect(formStart).toBeGreaterThan(-1);
    expect(formEnd).toBeGreaterThan(formStart);
    const inside = src.slice(formStart, formEnd);
    expect(inside).toMatch(/data-testid="place-order-cta"/);
    expect(inside).toMatch(/type="submit"|<ActionButton/);
  });

  it('mobile stays single-column: lg-only classes do not alter the base form', () => {
    const base = src.match(/<form noValidate onSubmit=\{handleSubmitOrder\} className="([^"]+)"/);
    expect(base).not.toBeNull();
    expect(base![1].split(' ').filter((c) => !c.startsWith('lg:'))).toEqual(['grid', 'grid-cols-1', 'gap-8']);
  });
});
