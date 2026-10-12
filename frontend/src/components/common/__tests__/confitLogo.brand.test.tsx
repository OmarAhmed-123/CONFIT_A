import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ConfitLogo, BRAND_COLORS } from '../ConfitLogo';

/**
 * Brand contract for Logo #3 "Individual Grid".
 * These tests fail if the old gold monogram comes back or if the four
 * official quadrant colours drift away from the sampled reference values.
 */
describe('ConfitLogo — Logo #3 brand contract', () => {
  it('exposes the accessible name "CONFIT" as an image', () => {
    render(<ConfitLogo variant="full" />);
    expect(screen.getByRole('img', { name: 'CONFIT' })).toBeInTheDocument();
  });

  it('paints the four official quadrants in coral, lilac, mint and charcoal', () => {
    const { container } = render(<ConfitLogo variant="mark" />);
    const fills = Array.from(container.querySelectorAll('svg > path')).map((p) =>
      p.getAttribute('fill'),
    );
    expect(fills).toEqual([
      BRAND_COLORS.coral,
      BRAND_COLORS.lilac,
      BRAND_COLORS.mint,
      BRAND_COLORS.charcoal,
    ]);
  });

  it('uses the sampled reference colours (not the retired gold/navy palette)', () => {
    expect(BRAND_COLORS.coral).toBe('#EF826D');
    expect(BRAND_COLORS.lilac).toBe('#A99AD6');
    expect(BRAND_COLORS.mint).toBe('#89B799');
    expect(BRAND_COLORS.charcoal).toBe('#242526');
  });

  it('no longer renders the legacy gold monogram or its label', () => {
    const { container } = render(<ConfitLogo variant="full" />);
    expect(container.innerHTML).not.toContain('CONFIT Brand Monogram');
    expect(container.innerHTML).not.toContain('#C5A059');
    expect(container.innerHTML).not.toContain('#B8935A');
  });

  it('mark variant renders the symbol only (no wordmark group)', () => {
    const { container } = render(<ConfitLogo variant="mark" />);
    expect(container.querySelector('g[transform*="scale("]')).toBeNull();
  });

  it('dark-surface theme swaps only the charcoal quadrant and wordmark to cream', () => {
    const { container } = render(<ConfitLogo variant="compact" theme="light" />);
    const fills = Array.from(container.querySelectorAll('svg > path')).map((p) =>
      p.getAttribute('fill'),
    );
    expect(fills[0]).toBe(BRAND_COLORS.coral);
    expect(fills[1]).toBe(BRAND_COLORS.lilac);
    expect(fills[2]).toBe(BRAND_COLORS.mint);
    expect(fills[3]).toBe(BRAND_COLORS.cream);
  });

  it('ships the official SVG assets in /public/brand with the right colour treatment', () => {
    const root = resolve(process.cwd(), 'public/brand');
    const read = (name: string) => readFileSync(resolve(root, name), 'utf8');

    for (const name of ['confit-logo.svg', 'confit-symbol.svg', 'favicon.svg']) {
      const svg = read(name);
      expect(svg.startsWith('<svg'), name).toBe(true);
      expect(svg, name).toContain(BRAND_COLORS.coral);
      expect(svg, name).toContain(BRAND_COLORS.lilac);
      expect(svg, name).toContain(BRAND_COLORS.mint);
    }

    const mono = read('confit-logo-monochrome.svg');
    expect(mono).not.toContain(BRAND_COLORS.coral);
    expect(mono).not.toContain(BRAND_COLORS.lilac);

    const reversed = read('confit-logo-reversed.svg');
    expect(reversed).toContain('#FFFFFF');
    expect(reversed).toContain(BRAND_COLORS.coral);
  });
});
