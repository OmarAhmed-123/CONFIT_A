/**
 * Mobile composition of the shared mood stack (CardStackShowcase).
 *
 * Why: the fixed AI Stylist control (48px circle below sm, 189x50 pill sm..lg,
 * bottom-4 / bottom-8) sits over the lower-right of the stack at 320–768px.
 * The fix lifts the card layer and moves the controls row clear of the control's band
 * using opt-in props on the shared CardStack. Defaults are unchanged for other consumers.
 *
 * Measured in a real browser (see docs/brand/logo-3-migration-coverage.md):
 * zero text/control overlap at 320–768 x 844, and 360–768 x 800 (320x800 has residual caption overlap).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { CardStack, type CardStackItem } from '../ui/card-stack';

const showcases = readFileSync(resolve(process.cwd(), 'src/components/showcase/DesignShowcases.tsx'), 'utf8');

const items: CardStackItem[] = [
  { id: 'a', title: 'Alpha', description: 'First', imageSrc: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', href: '/a', tag: 'A' },
  { id: 'b', title: 'Beta', description: 'Second', imageSrc: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', href: '/b', tag: 'B' },
  { id: 'c', title: 'Gamma', description: 'Third', imageSrc: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', href: '/c', tag: 'C' },
];

describe('mobile mood-stack reserve: shared-component wiring', () => {
  it('CardStackShowcase lifts the layer below lg and restores it at lg', () => {
    expect(showcases).toContain('stageClassName="!bottom-28 max-[359px]:!bottom-40 max-[359px]:origin-bottom max-[359px]:scale-[0.8] sm:!bottom-16 lg:!bottom-0"');
  });

  it('CardStackShowcase keeps the controls row clear of the FAB band below sm and restores desktop spacing at lg', () => {
    expect(showcases).toContain('controlsClassName="mt-8 sm:mt-4 sm:pe-28 lg:mt-4 lg:pe-0"');
  });

  it('CardStack applies the opt-in classes to the card layer and the controls row', () => {
    const { container } = render(
      <CardStack
        items={items}
        cardWidth={300}
        cardHeight={240}
        maxVisible={5}
        stageClassName="!bottom-28 lg:!bottom-0"
        controlsClassName="mt-8 lg:mt-4"
        labels={{ previous: 'Prev', next: 'Next', open: (t) => `Open ${t}` }}
      />,
    );
    const layer = container.querySelector('.absolute.inset-0.flex.items-end');
    expect(layer?.className).toContain('!bottom-28');
    expect(layer?.className).toContain('lg:!bottom-0');
    const controls = screen.getByRole('button', { name: 'Next' }).parentElement;
    expect(controls?.className).toContain('mt-8');
    expect(controls?.className).toContain('lg:mt-4');
  });

  it('CardStack with no opt-in props keeps the original classes (other consumers unchanged)', () => {
    const { container } = render(<CardStack items={items} cardWidth={300} cardHeight={240} maxVisible={5} />);
    const layer = container.querySelector('.absolute.inset-0.flex.items-end');
    expect(layer?.className).toBe('absolute inset-0 flex items-end justify-center');
  });

  it('keeps previous, next and open-link controls reachable with accessible names', () => {
    render(
      <CardStack
        items={items}
        cardWidth={300}
        cardHeight={240}
        maxVisible={5}
        stageClassName="!bottom-28 sm:!bottom-16 lg:!bottom-0"
        controlsClassName="mt-8 sm:mt-4 sm:pe-28 lg:mt-4 lg:pe-0"
        labels={{ previous: 'Previous card', next: 'Next card', open: (t) => `Open ${t}` }}
      />,
    );
    expect(screen.getByRole('button', { name: 'Previous card' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Next card' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open Alpha' }).getAttribute('href')).toBe('/a');
  });

  it('320px only: the card layer is scaled 0.8 from the bottom so the 300px active card fits its ~246px container', () => {
    // Measured: unscaled, "Tailored Power" lost its first letter at 320 wide (card clipped both sides).
    expect(showcases).toMatch(/max-\[359px\]:origin-bottom max-\[359px\]:scale-\[0\.8\]/);
    expect(showcases).toMatch(/max-\[359px\]:!bottom-40/);
  });
});

describe('Discover search card: lg placement (clear of the fixed AI Stylist footprint)', () => {
  const discover = readFileSync(resolve(process.cwd(), 'src/views/consumer/DiscoverView.tsx'), 'utf8');
  const hero = readFileSync(resolve(process.cwd(), 'src/components/common/HeroSection.tsx'), 'utf8');

  it('Discover moves the search aside into the left column, row 2, at lg', () => {
    expect(discover).toMatch(/asideClassName="lg:col-start-1 lg:row-start-2"/);
  });

  it('HeroSection applies asideClassName to the aside wrapper only (opt-in; default unchanged)', () => {
    expect(hero).toMatch(/asideClassName\?: string;/);
    expect(hero).toMatch(/className=\{`grid w-full min-w-0 \$\{asideClassName \?\? ''\}`\}/);
  });
});
