/**
 * Spec 11 — Optional 2.5D depth gallery (§10 test contract):
 *   feature-flag matrix · unsupported-engine fallback · low-memory
 *   emulation · reduced motion · static 2D fallback is real content ·
 *   manual controls (44px, translated, live position) · lazy loading ·
 *   axe EN + AR/RTL on BOTH paths.
 *
 * Gate order pinned (capability unit tests): flag-off → unsupported →
 * low-memory → reduced-motion, failing closed when CSS.supports is absent.
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { axe } from 'vitest-axe';

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { assessDepthCapability } from '../../utils/depthCapability';
import { CircularGallery } from '../ui/circular-gallery';
import { CircularGalleryShowcase } from '../showcase/DesignShowcases';

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

/* jsdom's CSS.supports doesn't know preserve-3d — stub per scenario. */
const supportsSpy = vi.fn().mockReturnValue(true);
let originalMatchMedia: typeof window.matchMedia;

beforeEach(() => {
  originalMatchMedia = window.matchMedia;
  vi.stubGlobal('CSS', { supports: supportsSpy });
  supportsSpy.mockReturnValue(true);
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(async () => {
  cleanup();
  vi.unstubAllGlobals();
  window.matchMedia = originalMatchMedia;
  // deviceMemory is configurable per test; always restore.
  delete (navigator as { deviceMemory?: number }).deviceMemory;
  await setAppLanguage('en');
});

const setDeviceMemory = (gib: number) =>
  Object.defineProperty(navigator, 'deviceMemory', {
    value: gib,
    configurable: true,
  });

const renderShowcase = (enabled?: boolean) =>
  render(
    <I18nextProvider i18n={i18n}>
      <CircularGalleryShowcase tone="consumer" compact enabled={enabled} />
    </I18nextProvider>,
  );

/* ------------------------------------------------------------------ */
/* A. Capability gate — unit (§5 state contract, exact refusal reasons) */
/* ------------------------------------------------------------------ */
describe('assessDepthCapability', () => {
  it('flag off wins over everything', () => {
    expect(assessDepthCapability({ flagOn: false, reduceMotion: false }))
      .toEqual({ ok: false, reason: 'flag-off' });
  });

  it('engine without preserve-3d ⇒ unsupported', () => {
    supportsSpy.mockReturnValue(false);
    expect(assessDepthCapability({ flagOn: true, reduceMotion: false }))
      .toEqual({ ok: false, reason: 'unsupported' });
    expect(supportsSpy).toHaveBeenCalledWith('transform-style', 'preserve-3d');
  });

  it('missing CSS.supports fails CLOSED (ancient engine ⇒ 2D)', () => {
    vi.stubGlobal('CSS', undefined);
    expect(assessDepthCapability({ flagOn: true, reduceMotion: false }).reason)
      .toBe('unsupported');
  });

  it('deviceMemory < 2 GiB ⇒ low-memory; absent hint passes', () => {
    setDeviceMemory(1);
    expect(assessDepthCapability({ flagOn: true, reduceMotion: false }).reason)
      .toBe('low-memory');
    delete (navigator as { deviceMemory?: number }).deviceMemory;
    expect(assessDepthCapability({ flagOn: true, reduceMotion: false }).ok)
      .toBe(true);
  });

  it('reduced motion ⇒ 2D even with full capability', () => {
    expect(assessDepthCapability({ flagOn: true, reduceMotion: true }).reason)
      .toBe('reduced-motion');
  });
});

/* ------------------------------------------------------------------ */
/* B. Flag matrix in the showcase (§10)                                */
/* ------------------------------------------------------------------ */
describe('CircularGalleryShowcase: flag matrix', () => {
  it('flag ON + capable device ⇒ 3D path renders', () => {
    renderShowcase(true);
    expect(screen.getByTestId('depth-gallery-3d')).toBeInTheDocument();
    expect(screen.queryByTestId('depth-gallery-2d')).not.toBeInTheDocument();
  });

  it('flag OFF ⇒ static 2D list with the SAME real assets', () => {
    renderShowcase(false);
    expect(screen.getByTestId('depth-gallery-2d')).toBeInTheDocument();
    expect(screen.queryByTestId('depth-gallery-3d')).not.toBeInTheDocument();
    // Real content, not placeholders: 6 figures with captions + credits.
    expect(screen.getAllByRole('figure')).toHaveLength(6);
    expect(screen.getByText('Workwear Fit')).toBeInTheDocument();
    expect(screen.getByText('Photo: Tamara Bellis')).toBeInTheDocument();
  });

  it('default (no prop, env unset in tests) ⇒ safe OFF ⇒ 2D', () => {
    renderShowcase(undefined);
    expect(screen.getByTestId('depth-gallery-2d')).toBeInTheDocument();
  });

  it('flag ON but engine unsupported ⇒ 2D (never a blank hole)', () => {
    supportsSpy.mockReturnValue(false);
    renderShowcase(true);
    expect(screen.getByTestId('depth-gallery-2d')).toBeInTheDocument();
  });

  it('flag ON but low-end device (deviceMemory 1 GiB) ⇒ 2D', () => {
    setDeviceMemory(1);
    renderShowcase(true);
    expect(screen.getByTestId('depth-gallery-2d')).toBeInTheDocument();
  });

  it('flag ON but prefers-reduced-motion ⇒ 2D with full function', () => {
    window.matchMedia = ((query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    renderShowcase(true);
    expect(screen.getByTestId('depth-gallery-2d')).toBeInTheDocument();
    // The fallback still navigates (prev/next buttons from AccessibleCarousel).
    expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* C. 3D gallery controls — scroll is never the only way (§7)          */
/* ------------------------------------------------------------------ */
describe('CircularGallery: manual controls', () => {
  const items = ['One', 'Two', 'Three', 'Four'].map((n, i) => ({
    common: n,
    binomial: `Caption ${n}`,
    photo: { url: `https://example.com/${i}.jpg`, text: `Look ${n}`, by: 'Unsplash' },
  }));

  it('prev/next are ≥44px labelled buttons; stepping announces position politely', () => {
    render(
      <CircularGallery
        items={items}
        ariaLabel="Mood gallery"
        labels={{
          previous: 'Previous look',
          next: 'Next look',
          position: (c, t) => `Item ${c} of ${t}`,
          credit: (n) => `Photo: ${n}`,
        }}
      />,
    );
    const next = screen.getByRole('button', { name: 'Next look' });
    expect(next.className).toContain('min-h-11');
    expect(next.className).toContain('min-w-11');
    expect(screen.getByText('1 / 4')).toBeInTheDocument();

    fireEvent.click(next);
    expect(screen.getByText('2 / 4')).toBeInTheDocument();
    const status = screen.getAllByRole('status').find((el) => el.textContent === 'Item 2 of 4');
    expect(status).toBeTruthy();
    expect(status).toHaveAttribute('aria-live', 'polite');

    fireEvent.click(screen.getByRole('button', { name: 'Previous look' }));
    expect(screen.getByText('1 / 4')).toBeInTheDocument();
  });

  it('keyboard alone can rotate: buttons respond to Enter via native button semantics', () => {
    render(<CircularGallery items={items} ariaLabel="Mood gallery" />);
    const next = screen.getByRole('button', { name: 'Next' });
    next.focus();
    expect(document.activeElement).toBe(next);
    fireEvent.click(next); // Enter/Space on a native <button> fires click
    expect(screen.getByText('2 / 4')).toBeInTheDocument();
  });

  it('images lazy-load except the front item; no "Photo by:" hardcoded EN', () => {
    render(
      <CircularGallery
        items={items}
        ariaLabel="Mood"
        labels={{ credit: (n) => `تصوير: ${n}` }}
      />,
    );
    const imgs = screen.getAllByRole('img');
    expect(imgs[0]).toHaveAttribute('loading', 'eager');
    imgs.slice(1).forEach((img) => expect(img).toHaveAttribute('loading', 'lazy'));
    expect(screen.queryByText(/Photo by:/)).not.toBeInTheDocument();
    expect(screen.getAllByText('تصوير: Unsplash')).toHaveLength(4);
  });
});

/* ------------------------------------------------------------------ */
/* D. i18n — Arabic page is Arabic on both paths                       */
/* ------------------------------------------------------------------ */
describe('depth gallery i18n', () => {
  it('AR 3D path: controls + credits translated', async () => {
    await setAppLanguage('ar');
    renderShowcase(true);
    expect(screen.getByRole('button', { name: 'الإطلالة التالية' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'الإطلالة السابقة' })).toBeInTheDocument();
    expect(screen.getAllByText(/تصوير:/).length).toBeGreaterThan(0);
  });

  it('AR 2D fallback: region label + captions translated', async () => {
    await setAppLanguage('ar');
    renderShowcase(false);
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByTestId('depth-gallery-2d')).toBeInTheDocument();
    expect(screen.getByText('إطلالة العمل')).toBeInTheDocument();
    expect(screen.getAllByText(/تصوير:/).length).toBe(6);
  });
});

/* ------------------------------------------------------------------ */
/* E. axe — both paths, both languages                                 */
/* ------------------------------------------------------------------ */
describe('axe', () => {
  it('3D path EN: no violations', async () => {
    const { container } = renderShowcase(true);
    expect((await axe(container, AXE_RULES)).violations).toEqual([]);
  });

  it('2D fallback AR/RTL: no violations', async () => {
    await setAppLanguage('ar');
    const { container } = renderShowcase(false);
    expect((await axe(container, AXE_RULES)).violations).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* F. Spec 11 §1 — the 3D experience is Discover-ONLY                  */
/* ------------------------------------------------------------------ */
/**
 * Lint-style guard (same rationale as tryOnGateCoverage): the rule
 * "only /discover may offer the 3D path" is a property of the whole view
 * tree, not of one component. Any view other than DiscoverView that
 * mounts CircularGalleryShowcase MUST pin `enabled={false}` so the
 * production flag (ON since spec 11 shipped) can never light up 3D on
 * an off-spec page. A render test would miss next month's new view.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

describe('Discover-only 3D guard', () => {
  const VIEWS = join(__dirname, '..', '..', 'views');
  const ALLOWED_3D = new Set(['consumer/DiscoverView.tsx']);

  function walk(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir)) {
      if (entry === '__tests__') continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full, out);
      else if (/\.tsx?$/.test(entry)) out.push(full);
    }
    return out;
  }

  it('every non-Discover view that mounts the gallery forces the 2D list', () => {
    const offenders: string[] = [];
    for (const file of walk(VIEWS)) {
      const rel = relative(VIEWS, file).split(/[\\/]/).join('/');
      const src = readFileSync(file, 'utf8');
      if (!src.includes('<CircularGalleryShowcase')) continue;
      if (ALLOWED_3D.has(rel)) continue;
      // Each usage outside Discover must carry enabled={false}.
      const usages = src.split('<CircularGalleryShowcase').slice(1);
      for (const u of usages) {
        const openTag = u.slice(0, u.indexOf('/>') >= 0 ? u.indexOf('/>') : u.length);
        if (!openTag.includes('enabled={false}')) offenders.push(rel);
      }
    }
    expect(
      offenders,
      `These views can render the 3D gallery but spec 11 §1 allows it on ` +
        `/discover only — add enabled={false}:\n` +
        offenders.map((f) => `  - ${f}`).join('\n'),
    ).toEqual([]);
  });
});
