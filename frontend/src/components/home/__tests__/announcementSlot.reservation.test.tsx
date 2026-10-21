import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

/**
 * CLS regression: the announcement bar is data-gated.
 *
 * MEASURED on `08b281b` (Chromium 156, 412x915, web-vitals) unless stated:
 *   `/` CLS 0.8088; aborting only `/catalog/capabilities` -> 0.0147; aborting an
 *   unrelated endpoint -> 0.7641. Cause: the bar is inserted into normal flow
 *   above the hero ~1.3s after first paint.
 *   Serving the payload with zero latency still scored 0.8077, so "earlier data"
 *   cannot fix a client-rendered SPA. Reserving the space scored 0.0088 with
 *   identical final geometry (hero top 253, page height 11888).
 *
 * The first attempt at this fix released the reservation when the fetch failed
 * and measured 0.8145 — worse than the defect. These tests pin the rule that
 * eliminates that: once the slot is reserved it stays reserved for the session,
 * and only a first-paint fact (dismissal, or a prior visit proving there is no
 * policy) may prevent the reservation.
 *
 * jsdom cannot measure layout, so the assertions are on the contract:
 * `data-reserved` at first render and in each resolved state.
 */

const SAMPLE = {
  payments_live: false, payments_live_methods: [], cod_live: true, payments_mode: 'demo' as const,
  bnpl_live: false, vton_gpu_ready: false, vton_engine_state: 'temporarily_unavailable',
  vton_offered: false, vton_renderable: false, ai_stylist_live: false,
  photo_upload_available: true, bopis_live: true, bopis_store_count: 1, storage_mode: 's3',
  returns_window_days: 30, free_shipping_threshold: 250, standard_shipping_fee: 25,
  shipping_currency: 'USD',
};

const FALLBACK = {
  free_shipping_threshold: null, shipping_currency: null,
};

const state = vi.hoisted(() => ({
  capabilities: {} as Record<string, unknown>,
  isLoading: false,
}));

// The slot tells a failed fetch from a real "no policy" answer by object
// identity against the exported sentinel. The sentinel now lives in its own
// module and is NOT mocked here, so this test exercises the same object the
// application compares against.
import { HONEST_FALLBACK_CAPABILITIES as REAL_FALLBACK } from '../../../hooks/capabilitiesFallback';

vi.mock('../../../hooks/useCapabilities', () => ({
  useCapabilities: () => ({ capabilities: state.capabilities, isLoading: state.isLoading }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o?.amount ? `${k}:${o.amount}` : k),
    i18n: { resolvedLanguage: 'en' },
  }),
}));

vi.mock('framer-motion', () => ({
  motion: { div: ({ children, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div {...p}>{children}</div> },
}));

import { AnnouncementSlot } from '../AnnouncementSlot';

const slot = () => screen.getByTestId('announcement-slot');

describe('AnnouncementSlot — layout reservation (CLS)', () => {
  beforeEach(() => {
    state.capabilities = {};
    state.isLoading = false;
    try { window.localStorage.clear(); } catch { /* jsdom without storage */ }
  });

  it('reserves the space while the capability response is in flight', () => {
    state.isLoading = true;
    render(<AnnouncementSlot />);
    expect(slot()).toHaveAttribute('data-reserved', 'true');
  });

  it('keeps the reservation when a policy resolves, so the bar lands in reserved space', () => {
    state.capabilities = { ...SAMPLE };
    render(<AnnouncementSlot />);
    expect(slot()).toHaveAttribute('data-reserved', 'true');
    expect(screen.getByTestId('announcement-bar')).toBeInTheDocument();
  });

  it('does NOT release the reservation when the fetch fails (the 0.8145 regression)', () => {
    // The bar may still be coming on a retry, and releasing now would move the
    // already-painted hero. Holding the space is invisible to CLS; releasing it
    // is a viewport-wide shift.
    state.capabilities = REAL_FALLBACK as unknown as Record<string, unknown>;
    render(<AnnouncementSlot />);
    expect(slot()).toHaveAttribute('data-reserved', 'true');
    expect(screen.queryByTestId('announcement-bar')).not.toBeInTheDocument();
  });

  it('does not remember "no policy" from a failed fetch', () => {
    // Writing the hint off a failure would permanently strip the space from a
    // deployment that does have a policy.
    state.capabilities = REAL_FALLBACK as unknown as Record<string, unknown>;
    render(<AnnouncementSlot />);
    expect(window.localStorage.getItem('confit.announcement.policy.v1')).toBeNull();
  });

  it('holds the space but does not shift when a real "no policy" answer arrives', () => {
    // Mid-session release is what produced 0.8145, so the space stays held for
    // this visit even though nothing will render.
    state.capabilities = { ...FALLBACK };
    render(<AnnouncementSlot />);
    expect(slot()).toHaveAttribute('data-reserved', 'true');
    expect(screen.queryByTestId('announcement-bar')).not.toBeInTheDocument();
  });

  it('remembers a real "no policy" answer so the next visit reserves nothing', () => {
    state.capabilities = { ...FALLBACK };
    render(<AnnouncementSlot />);
    expect(window.localStorage.getItem('confit.announcement.policy.v1')).toBe('none');
  });

  it('reserves nothing on a later visit to a deployment known to have no policy', () => {
    window.localStorage.setItem('confit.announcement.policy.v1', 'none');
    state.isLoading = true;
    render(<AnnouncementSlot />);
    // Known at first paint, so the space is never taken and never released.
    expect(slot()).toHaveAttribute('data-reserved', 'false');
  });

  it('reserves nothing for a shopper who dismissed this exact policy', () => {
    state.capabilities = { ...SAMPLE };
    window.localStorage.setItem('confit.announcement.freeship.v1', '250:USD');
    render(<AnnouncementSlot />);
    expect(slot()).toHaveAttribute('data-reserved', 'false');
    expect(screen.queryByTestId('announcement-bar')).not.toBeInTheDocument();
  });

  it('still reserves for a shopper who dismissed a DIFFERENT policy value', () => {
    // A changed threshold is news again: the bar returns, so the space must be
    // held or the returning bar would push the page down.
    state.capabilities = { ...SAMPLE, free_shipping_threshold: 300 };
    window.localStorage.setItem('confit.announcement.freeship.v1', '250:USD');
    render(<AnnouncementSlot />);
    expect(slot()).toHaveAttribute('data-reserved', 'true');
    expect(screen.getByTestId('announcement-bar')).toBeInTheDocument();
  });

  it('records that a policy exists so the next visit paints the bar in place', () => {
    state.capabilities = { ...SAMPLE };
    render(<AnnouncementSlot />);
    expect(window.localStorage.getItem('confit.announcement.policy.v1')).toBe('present');
  });
});
