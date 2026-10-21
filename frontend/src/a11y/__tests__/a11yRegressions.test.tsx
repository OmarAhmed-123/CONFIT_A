/**
 * Regression tests for the accessibility defects fixed on 2026-10-21.
 *
 * Each test pins a MEASURED defect, and each one fails if the defect returns.
 * Where the defect was a CSS-cascade accident rather than a missing attribute,
 * the test asserts the thing that actually broke (the control's computed
 * position), not the attribute that happened to be present.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { WishlistToggle } from '../../components/common/InteractionPrimitives';
import { HeroLightCard } from '../../components/common/HeroSection';
import { StoreBranchCard } from '../../components/brands/StoreBranchCard';

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('WishlistToggle — position belongs to the caller', () => {
  /*
   * MEASURED DEFECT (2026-10-21): the base class began with `relative`.
   * Callers position the control with `absolute top-1 end-1` over a product
   * photograph, but two utilities of equal specificity resolve by stylesheet
   * order, and `.relative` won. Result on /discover at 390px: the button sat in
   * normal flow (44x44), was clipped by the card's `overflow-hidden`, covered
   * the caption, and left a 44px empty band under every image. axe reported
   * 132 controls as "partially obscured (44px by 14px)".
   *
   * A jsdom test cannot resolve the cascade, so the test asserts the cause:
   * the shared base class must not declare a position at all.
   */
  it('base class declares no position, so a caller can position it', () => {
    render(<WishlistToggle isWishlisted={false} onToggle={() => {}} className="absolute top-1 end-1">♥</WishlistToggle>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('absolute');
    expect(btn.className.split(/\s+/)).not.toContain('relative');
    expect(btn.className).not.toMatch(/\bstatic\b/);
  });

  it('keeps a 44px minimum hit area regardless of caller styling', () => {
    render(<WishlistToggle isWishlisted={false} onToggle={() => {}} className="absolute top-1 end-1">♥</WishlistToggle>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('min-w-[44px]');
    expect(btn.className).toContain('min-h-[44px]');
  });

  it('exposes pressed state and announces the change', () => {
    render(<WishlistToggle isWishlisted onToggle={() => {}}>♥</WishlistToggle>);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(btn.querySelector('[role="status"]')).not.toBeNull();
  });
});

describe('HeroLightCard — visible text is part of the accessible name (2.5.3)', () => {
  /*
   * MEASURED DEFECT: `label` was applied as `aria-label`, replacing the card's
   * text. The name ("Example styled look — open the outfit builder") did not
   * contain the visible words, so a speech user reading the card aloud could
   * not reach it. `label` is now a suffix of visually-hidden text.
   */
  it('name contains the visible content AND the action label', () => {
    wrap(
      <HeroLightCard to="/builder" label="— open the outfit builder">
        <span>Example result</span>
        <h2>Tailored Power</h2>
      </HeroLightCard>,
    );
    const link = screen.getByRole('link');
    const name = link.textContent ?? '';
    expect(name).toContain('Example result');
    expect(name).toContain('Tailored Power');
    expect(name).toContain('open the outfit builder');
    expect(link).not.toHaveAttribute('aria-label');
  });
});

describe('StoreBranchCard — a card with controls inside it is not a button', () => {
  /*
   * MEASURED DEFECT: the card carried role="button" and aria-pressed while
   * containing three real controls (Get Directions, a tel: link, View stock).
   * axe: nested-interactive, 12 nodes. A button may not contain controls.
   */
  const branch = {
    id: 1, name: 'Atelier Sable — The Dubai Mall', city: 'Dubai', address: 'Financial Center Rd',
    phone: '+971 4 000 0000', google_maps_url: 'https://maps.example/x', is_selected: false,
    opening_hours: null, distance_km: null, active_promotions: [],
  } as never;

  it('is not itself a button, and still exposes its real controls', () => {
    render(<StoreBranchCard branch={branch} isSelected={false} onSelect={() => {}} />);
    // The card container must not be a button; its real controls must remain.
    // "Get Directions" and the phone number are links; "View stock" is a
    // button — so the count is one button, not three, and asserting "buttons"
    // alone would have measured the wrong thing.
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole('link').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole('link', { name: /Get Directions/ })).toBeTruthy();
    // No element claims a pressed state any more (the fake button did).
    expect(document.querySelector('[aria-pressed]')).toBeNull();
  });

  it('every control name still contains its visible label', () => {
    render(<StoreBranchCard branch={branch} isSelected={false} onSelect={() => {}} />);
    for (const btn of screen.getAllByRole('button')) {
      const visible = (btn.textContent ?? '').replace(/\s+/g, ' ').trim().split(' — ')[0];
      if (!visible) continue;
      const name = (btn.getAttribute('aria-label') ?? btn.textContent ?? '').replace(/\s+/g, ' ').trim();
      expect(name.toLowerCase()).toContain(visible.toLowerCase().slice(0, 12));
    }
  });
});
