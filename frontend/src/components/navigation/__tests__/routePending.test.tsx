/**
 * Spec "Magic Navigation" §5 — pending navigation for lazy route chunks.
 *
 * What this file pins:
 *   1. RoutePending is a TEXT state: visible translated copy inside a
 *      polite live region — never a motion-only or blank pending screen.
 *   2. It speaks Arabic on the Arabic page.
 *   3. Reduced motion: the spinner is decorative (aria-hidden) and spins
 *      only under `motion-safe:`; the text carries the state on its own.
 *   4. axe: no violations, EN/LTR and AR/RTL.
 *   5. The lazy wiring is real: AppRoutes declares the two analytics views
 *      via React.lazy + Suspense(RoutePending) — a shopper's bundle no
 *      longer ships partner/governance dashboards eagerly. (The byte-level
 *      proof lives in the build: the b2b-analytics chunk is referenced
 *      only through a dynamic import. Asserted here at the source level
 *      so a regression fails fast in CI.)
 */
import { describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, act } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { I18nextProvider } from 'react-i18next';
import fs from 'node:fs';
import path from 'node:path';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { RoutePending } from '../RoutePending';

afterEach(() => {
  cleanup();
  setAppLanguage('en');
});

function wrap(ui: React.ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe('RoutePending is a text-first announced state', () => {
  it('renders the translated sentence inside a polite status region', () => {
    wrap(<RoutePending />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveTextContent('Loading this section…');
  });

  it('speaks Arabic on the Arabic page', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    wrap(<RoutePending />);
    expect(screen.getByRole('status')).toHaveTextContent('جارٍ تحميل هذا القسم…');
  });

  it('the spinner is decoration: aria-hidden and motion-safe only', () => {
    const { container } = wrap(<RoutePending />);
    const spinner = container.querySelector('[aria-hidden="true"]');
    expect(spinner).not.toBeNull();
    // `motion-safe:animate-spin` — never a bare animate-spin that ignores
    // the user's reduced-motion preference.
    expect(spinner!.className).toContain('motion-safe:animate-spin');
    expect(spinner!.className).not.toMatch(/(?<!motion-safe:)animate-spin/);
  });

  it('axe: clean in EN/LTR', async () => {
    const { container } = wrap(<RoutePending />);
    expect((await axe(container)).violations).toEqual([]);
  });

  it('axe: clean in AR/RTL', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    const { container } = wrap(
      <div dir="rtl">
        <RoutePending />
      </div>,
    );
    expect((await axe(container)).violations).toEqual([]);
  });
});

describe('the analytics views are genuinely lazy (§5 + §8 performance)', () => {
  const routesSrc = fs.readFileSync(
    path.resolve(__dirname, '../../../router/AppRoutes.tsx'),
    'utf-8',
  );

  it('both heavy analytics views load through React.lazy, not static imports', () => {
    expect(routesSrc).toMatch(/React\.lazy\(\(\)\s*=>\s*\n?\s*import\('\.\.\/views\/b2b\/BrandAnalyticsView'\)/);
    expect(routesSrc).toMatch(/React\.lazy\(\(\)\s*=>\s*\n?\s*import\('\.\.\/views\/b2b\/AdminAnalyticsView'\)/);
    expect(routesSrc).not.toMatch(/import \{ BrandAnalyticsView \} from/);
    expect(routesSrc).not.toMatch(/import \{ AdminAnalyticsView \} from/);
  });

  it('every lazy element is wrapped in Suspense with the announced pending state', () => {
    // All analytics route elements go through suspended(...) which pairs
    // the chunk load with <RoutePending/> — no blank screens.
    const lazyUsages = routesSrc.match(/suspended\(<(Brand|Admin)AnalyticsView \/>\)/g) ?? [];
    expect(lazyUsages.length).toBeGreaterThanOrEqual(4);
    expect(routesSrc).toContain('fallback={<RoutePending />}');
    // And no analytics route escapes the wrapper.
    expect(routesSrc).not.toMatch(/element=\{<(Brand|Admin)AnalyticsView \/>\}/);
  });
});
