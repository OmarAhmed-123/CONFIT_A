/**
 * Spec 14 — animated semantic status icons (§10 test contract):
 *   StatusIcon typed contract (shape per status, decorative vs labelled,
 *   loading = motion-safe spin only, no continuous dancing) · reduced
 *   motion = static with full function · Toast speaks shape+text not
 *   colour, error escalates to role=alert · TryOnEngineStatus drops the
 *   unicode glyphs for semantic shapes · CatalogFreshnessIndicator's
 *   three honest states with the revision code kept LTR in Arabic ·
 *   axe EN + AR/RTL.
 *
 * jsdom cannot measure rendered colour contrast; what IS mechanically
 * provable — and pinned here — is that colour is never the only channel:
 * every state exposes a distinct icon shape (data-status) AND visible or
 * live-region text.
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { axe } from 'vitest-axe';

import { StatusIcon } from '../InteractionPrimitives';
import { Toast } from '../CommonComponents';
import { CatalogFreshnessIndicator } from '../CatalogFreshness';
import { TryOnEngineStatus } from '../../tryon/TryOnEngineStatus';
import { setAppLanguage } from '../../../i18n/i18n';

/* ---------------- mocks ---------------- */

const revisionState: {
  revision: string | null;
  sellableUnits: number | null;
  isPolling: boolean;
  error: unknown;
} = { revision: null, sellableUnits: null, isPolling: false, error: null };

vi.mock('../../../hooks/useCatalogRevision', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../hooks/useCatalogRevision')>();
  return {
    ...actual,
    useCatalogRevision: () => ({ ...revisionState }),
  };
});

const engineState: {
  engineHealth: { verdict: string; detail?: string; retry_after_seconds?: number } | null;
  engineSla: { warm_render_seconds_p50: number; cold_start_seconds_budget: number; max_garments_per_job: number | null } | null;
} = { engineHealth: null, engineSla: null };

vi.mock('../../../viewmodels/useTryOnViewModel', () => ({
  useTryOnViewModel: () => ({
    engineHealth: engineState.engineHealth,
    engineSla: engineState.engineSla,
    checkTryOnCapabilities: vi.fn().mockResolvedValue(undefined),
  }),
}));

/* ---------------- reduced-motion plumbing ---------------- */

const originalMatchMedia = window.matchMedia;
const setReducedMotion = (reduce: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? reduce : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as typeof window.matchMedia;
};

beforeEach(async () => {
  cleanup();
  setReducedMotion(false);
  revisionState.revision = null;
  revisionState.error = null;
  engineState.engineHealth = null;
  engineState.engineSla = null;
  await act(async () => { await setAppLanguage('en'); });
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
  cleanup();
});

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

/* ------------------------------------------------------------------ */
/* A. StatusIcon primitive                                             */
/* ------------------------------------------------------------------ */
describe('StatusIcon contract', () => {
  it('renders a DISTINCT svg shape per status — state is never colour-only', () => {
    const statuses = ['loading', 'success', 'error', 'warning', 'info'] as const;
    const shapes = statuses.map((status) => {
      const { container, unmount } = render(<StatusIcon status={status} />);
      const wrapper = container.querySelector(`[data-status="${status}"]`)!;
      expect(wrapper).toBeTruthy();
      const svg = wrapper.querySelector('svg')!;
      const shape = svg.innerHTML;
      unmount();
      return shape;
    });
    expect(new Set(shapes).size).toBe(statuses.length);
  });

  it('is decorative by default (text beside it owns the meaning)', () => {
    const { container } = render(<StatusIcon status="success" />);
    const wrapper = container.querySelector('[data-status="success"]')!;
    expect(wrapper.getAttribute('aria-hidden')).toBe('true');
    expect(wrapper.getAttribute('role')).toBeNull();
  });

  it('icon-only placement: label becomes the accessible name via role=img', () => {
    render(<StatusIcon status="error" label="Sync failed" />);
    const img = screen.getByRole('img', { name: 'Sync failed' });
    expect(img.getAttribute('aria-hidden')).toBeNull();
  });

  it('ONLY loading animates continuously, and only behind motion-safe', () => {
    for (const status of ['success', 'error', 'warning', 'info'] as const) {
      const { container, unmount } = render(<StatusIcon status={status} />);
      expect(container.innerHTML).not.toContain('animate-spin');
      expect(container.innerHTML).not.toContain('animate-pulse');
      unmount();
    }
    const { container } = render(<StatusIcon status="loading" />);
    expect(container.querySelector('svg')!.getAttribute('class')).toContain('motion-safe:animate-spin');
  });

  it('reduced motion: same glyphs render, spin stays CSS-gated — full function, zero scripted motion', () => {
    setReducedMotion(true);
    const { container } = render(<StatusIcon status="success" />);
    const wrapper = container.querySelector('[data-status="success"]')!;
    expect(wrapper.querySelector('svg')).toBeTruthy();
    // plain span host under reduced motion — no inline animation styles
    expect((wrapper as HTMLElement).style.opacity).toBe('');
    const loading = render(<StatusIcon status="loading" />);
    expect(loading.container.querySelector('svg')!.getAttribute('class')).toContain('motion-safe:animate-spin');
  });

  it('never renders text/emoji glyphs as the status channel', () => {
    const { container } = render(<StatusIcon status="warning" />);
    expect(container.textContent).toBe('');
  });
});

/* ------------------------------------------------------------------ */
/* B. Toast                                                            */
/* ------------------------------------------------------------------ */
describe('Toast semantic status (spec 14)', () => {
  it('success: role=status/polite container, decorative success shape, visible text', () => {
    render(<Toast message="Saved to closet" type="success" onClose={() => {}} />);
    const region = screen.getByRole('status');
    expect(region.getAttribute('aria-live')).toBe('polite');
    const icon = screen.getByTestId('toast-status-icon');
    expect(icon.getAttribute('data-status')).toBe('success');
    expect(icon.getAttribute('aria-hidden')).toBe('true');
    expect(region.textContent).toContain('Saved to closet');
  });

  it('error: container escalates to role=alert + assertive — not just a red tint', () => {
    render(<Toast message="Checkout failed" type="error" onClose={() => {}} />);
    const alert = screen.getByRole('alert');
    expect(alert.getAttribute('aria-live')).toBe('assertive');
    expect(screen.getByTestId('toast-status-icon').getAttribute('data-status')).toBe('error');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('info: distinct info shape — three types, three shapes', () => {
    render(<Toast message="Heads up" type="info" onClose={() => {}} />);
    expect(screen.getByTestId('toast-status-icon').getAttribute('data-status')).toBe('info');
  });

  it('dismiss control: 44px floor + accessible name, no bare glyph', () => {
    render(<Toast message="x" type="info" onClose={() => {}} />);
    const dismiss = screen.getByRole('button', { name: 'Dismiss notification' });
    expect(dismiss.className).toContain('min-h-[44px]');
    expect(dismiss.className).toContain('min-w-[44px]');
    expect(dismiss.textContent).toBe('');
  });

  it('axe clean EN and AR/RTL; Arabic flips direction without changing meaning', async () => {
    const en = render(<Toast message="Saved" type="success" onClose={() => {}} />);
    const enAxe = await axe(en.container, AXE_RULES);
    expect(enAxe.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    en.unmount();

    await act(async () => { await setAppLanguage('ar'); });
    const ar = render(<Toast message="تم الحفظ" type="error" onClose={() => {}} />);
    expect(document.documentElement.dir).toBe('rtl');
    // same shape channel in RTL — direction never changes the meaning
    expect(screen.getByTestId('toast-status-icon').getAttribute('data-status')).toBe('error');
    expect(screen.getByRole('button', { name: 'إغلاق الإشعار' })).toBeTruthy();
    const arAxe = await axe(ar.container, AXE_RULES);
    expect(arAxe.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });
});

/* ------------------------------------------------------------------ */
/* C. TryOnEngineStatus                                                */
/* ------------------------------------------------------------------ */
describe('TryOnEngineStatus semantic shapes', () => {
  it('ready → role=status with the success shape (no unicode dot)', () => {
    engineState.engineHealth = { verdict: 'ready' };
    engineState.engineSla = { warm_render_seconds_p50: 9, cold_start_seconds_budget: 120, max_garments_per_job: 3 };
    const { container } = render(<TryOnEngineStatus />);
    expect(screen.getByRole('status')).toBeTruthy();
    expect(container.querySelector('[data-status="success"]')).toBeTruthy();
    for (const glyph of ['●', '▲', '■']) expect(container.textContent).not.toContain(glyph);
  });

  it('cold_start → warning shape inside a polite status container', () => {
    engineState.engineHealth = { verdict: 'cold_start' };
    const { container } = render(<TryOnEngineStatus />);
    expect(screen.getByRole('status')).toBeTruthy();
    expect(container.querySelector('[data-status="warning"]')).toBeTruthy();
  });

  it("unavailable → role=alert, error shape, and the backend's own sentence", () => {
    engineState.engineHealth = { verdict: 'unavailable', detail: 'GPU workspace disabled', retry_after_seconds: 45 };
    const { container } = render(<TryOnEngineStatus />);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('GPU workspace disabled');
    expect(container.querySelector('[data-status="error"]')).toBeTruthy();
  });

  it('unknown → renders nothing: we do not guess', () => {
    engineState.engineHealth = { verdict: 'unknown' };
    const { container } = render(<TryOnEngineStatus />);
    expect(container.innerHTML).toBe('');
  });
});

/* ------------------------------------------------------------------ */
/* D. CatalogFreshnessIndicator                                        */
/* ------------------------------------------------------------------ */
describe('CatalogFreshnessIndicator honest states', () => {
  it('first poll in flight → loading shape + "checking" text, polite live region', () => {
    render(<CatalogFreshnessIndicator />);
    const region = screen.getByTestId('catalog-freshness');
    expect(region.getAttribute('role')).toBe('status');
    expect(region.getAttribute('aria-live')).toBe('polite');
    expect(region.getAttribute('data-freshness-state')).toBe('loading');
    expect(region.textContent).toContain('Checking catalog freshness');
  });

  it('fingerprint current → success + states the poll interval (polling ≠ "real-time")', () => {
    revisionState.revision = 'a1b2c3d4e5f6';
    render(<CatalogFreshnessIndicator />);
    const region = screen.getByTestId('catalog-freshness');
    expect(region.getAttribute('data-freshness-state')).toBe('success');
    expect(region.textContent).toContain('every 30s');
  });

  it('poll failing → warning + degraded copy; never silent, never a fake error page', () => {
    revisionState.revision = 'a1b2c3d4e5f6';
    revisionState.error = new Error('network');
    render(<CatalogFreshnessIndicator />);
    const region = screen.getByTestId('catalog-freshness');
    expect(region.getAttribute('data-freshness-state')).toBe('warning');
    expect(region.textContent).toContain('out of date');
  });

  it('Arabic: translated copy, RTL page, but the revision CODE stays LTR', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    revisionState.revision = 'a1b2c3d4e5f6';
    const { container } = render(<CatalogFreshnessIndicator />);
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByTestId('catalog-freshness').textContent).toContain('الكتالوج متزامن');
    const code = container.querySelector('[dir="ltr"]')!;
    expect(code.textContent).toBe('a1b2c3d4');
    const results = await axe(container, AXE_RULES);
    expect(results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });
});
