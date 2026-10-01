/**
 * Spec 06 — Share / Copy Feedback. §10 required coverage:
 *   clipboard denied · browser unsupported · expired token · private/revoked
 *   token · keyboard · screen reader — plus native-share fallback paths,
 *   AR/RTL + axe, reduced motion.
 *
 * Structure:
 *   A. ShareActions state machine (copy success / denied / unsupported,
 *      timed revert + re-copy, one polite live region)
 *   B. Native share (supported / hidden, cancel is not an error, real
 *      failure falls back to clipboard with an honest announcement)
 *   C. SharedLookView (expired/revoked/private → 404 verdict, server error,
 *      ready — all localized; PNG failure announced inline)
 *   D. axe EN + AR/RTL · keyboard · reduced motion
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { ShareActions } from '../ShareActions';

vi.mock('../../../services/apiServices', () => ({
  publicLookService: { getPublicLook: vi.fn() },
}));
vi.mock('html-to-image', () => ({ toPng: vi.fn() }));

import { publicLookService } from '../../../services/apiServices';
import { toPng } from 'html-to-image';
import { SharedLookView } from '../../../views/public/SharedLookView';

const URL_UNDER_TEST = 'https://confit-a.vercel.app/looks/tok_live_abc123';

const renderShare = (props: Partial<React.ComponentProps<typeof ShareActions>> = {}) =>
  render(
    <I18nextProvider i18n={i18n}>
      <ShareActions url={URL_UNDER_TEST} title="Evening Ensemble" {...props} />
    </I18nextProvider>,
  );

/** Install a controllable clipboard; returns the writeText spy. */
function stubClipboard(impl: () => Promise<void>) {
  const writeText = vi.fn(impl);
  Object.defineProperty(window.navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
  return writeText;
}
function removeClipboard() {
  Object.defineProperty(window.navigator, 'clipboard', {
    value: undefined,
    configurable: true,
  });
}
function stubNativeShare(impl?: (data: ShareData) => Promise<void>) {
  Object.defineProperty(window.navigator, 'share', {
    value: impl ? vi.fn(impl) : undefined,
    configurable: true,
  });
  return window.navigator.share as unknown as ReturnType<typeof vi.fn>;
}

beforeEach(() => {
  vi.clearAllMocks();
  stubNativeShare(undefined); // default: no Web Share API
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// ===========================================================================
// A. Copy state machine
// ===========================================================================
describe('ShareActions — copy', () => {
  it('success: copies the EXACT url, announces "copied" as text, reverts, and can copy again', async () => {
    const writeText = stubClipboard(() => Promise.resolve());
    renderShare();

    const btn = screen.getByRole('button', { name: i18n.t('share.copy_link') });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.copied'));
    });
    expect(writeText).toHaveBeenCalledExactlyOnceWith(URL_UNDER_TEST);
    // The button LABEL also states the outcome — not colour alone (§7).
    expect(screen.getByRole('button', { name: i18n.t('share.copied') })).toBeInTheDocument();

    // Timed revert (§6.4 "لمدة مفهومة مع زر copy مرة أخرى").
    await waitFor(
      () => expect(screen.getByRole('button', { name: i18n.t('share.copy_link') })).toBeInTheDocument(),
      { timeout: 4000 },
    );
    fireEvent.click(screen.getByRole('button', { name: i18n.t('share.copy_link') }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
  });

  it('denied: permission refusal is announced honestly — never a fake "copied"', async () => {
    stubClipboard(() => Promise.reject(new DOMException('denied', 'NotAllowedError')));
    renderShare();

    fireEvent.click(screen.getByRole('button', { name: i18n.t('share.copy_link') }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.copy_denied'));
    });
    expect(screen.queryByText(i18n.t('share.copied'))).toBeNull();
    // The denied state persists (manual-copy instruction), no auto-revert
    // that would erase the guidance mid-read.
    await act(() => new Promise((r) => setTimeout(r, 100)));
    expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.copy_denied'));
  });

  it('unsupported: no Clipboard API at all → manual-copy instruction, no crash', async () => {
    removeClipboard();
    renderShare();

    fireEvent.click(screen.getByRole('button', { name: i18n.t('share.copy_link') }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.copy_unsupported'));
    });
  });

  it('screen reader: ONE polite, atomic live region that exists BEFORE the first announcement', () => {
    stubClipboard(() => Promise.resolve());
    renderShare();
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveAttribute('aria-atomic', 'true');
    expect(region).toHaveTextContent(''); // mounted empty, ready to announce
  });
});

// ===========================================================================
// B. Native share
// ===========================================================================
describe('ShareActions — native share', () => {
  it('renders the share button ONLY when navigator.share exists', () => {
    renderShare();
    expect(screen.queryByRole('button', { name: i18n.t('share.native_share') })).toBeNull();
    cleanup();

    stubNativeShare(() => Promise.resolve());
    renderShare();
    expect(screen.getByRole('button', { name: i18n.t('share.native_share') })).toBeInTheDocument();
  });

  it('passes title + url to the OS sheet; success announces nothing (the user saw it)', async () => {
    const share = stubNativeShare(() => Promise.resolve());
    stubClipboard(() => Promise.resolve());
    renderShare();

    fireEvent.click(screen.getByRole('button', { name: i18n.t('share.native_share') }));
    await waitFor(() => expect(share).toHaveBeenCalledExactlyOnceWith({ title: 'Evening Ensemble', url: URL_UNDER_TEST }));
    expect(screen.getByRole('status')).toHaveTextContent('');
  });

  it('user cancelling the sheet (AbortError) returns silently to idle — cancellation is not an error', async () => {
    stubNativeShare(() => Promise.reject(new DOMException('cancel', 'AbortError')));
    const writeText = stubClipboard(() => Promise.resolve());
    renderShare();

    fireEvent.click(screen.getByRole('button', { name: i18n.t('share.native_share') }));
    await act(() => new Promise((r) => setTimeout(r, 50)));

    expect(screen.getByRole('status')).toHaveTextContent('');
    expect(writeText).not.toHaveBeenCalled(); // no sneaky fallback on cancel
  });

  it('REAL share failure falls back to clipboard and says so — never claims the share happened', async () => {
    stubNativeShare(() => Promise.reject(new TypeError('share failed')));
    const writeText = stubClipboard(() => Promise.resolve());
    renderShare();

    fireEvent.click(screen.getByRole('button', { name: i18n.t('share.native_share') }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.shared_fallback'));
    });
    expect(writeText).toHaveBeenCalledExactlyOnceWith(URL_UNDER_TEST);
  });

  it('share failure + clipboard ALSO denied → the denied truth wins', async () => {
    stubNativeShare(() => Promise.reject(new TypeError('share failed')));
    stubClipboard(() => Promise.reject(new DOMException('denied', 'NotAllowedError')));
    renderShare();

    fireEvent.click(screen.getByRole('button', { name: i18n.t('share.native_share') }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.copy_denied'));
    });
    expect(screen.queryByText(i18n.t('share.shared_fallback'))).toBeNull();
  });
});

// ===========================================================================
// C. SharedLookView — token verdicts are server-owned
// ===========================================================================
const renderPublic = (token = 'tok_x') =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[`/looks/${token}`]}>
        <Routes>
          <Route path="/looks/:token" element={<SharedLookView />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );

const READY_LOOK = {
  title: 'Evening Ensemble',
  occasion: 'Gala',
  total_price: 420,
  compatibility_score: 88,
  created_at: '2026-09-01T00:00:00Z',
  items: [
    {
      product_title: 'Silk Blazer',
      brand_name: 'Atelier',
      category_name: 'Outerwear',
      price: 420,
      image_url: 'https://cdn.example/x.jpg',
      color_hex: '#101020',
      position: 'top',
    },
  ],
};

describe('SharedLookView token verdicts', () => {
  it('expired / revoked / private token: server 404 → localized "no longer available"', async () => {
    vi.mocked(publicLookService.getPublicLook).mockRejectedValue({ status: 404 });
    renderPublic('tok_expired');

    expect(await screen.findByText(i18n.t('shared_look.unavailable_title'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('shared_look.unavailable_body'))).toBeInTheDocument();
    // Way out is a real link.
    expect(screen.getByRole('link', { name: i18n.t('shared_look.back_home') })).toHaveAttribute('href', '/');
    // Nothing of a look leaked into the DOM.
    expect(screen.queryByTestId('outfit-share-card')).toBeNull();
  });

  it('server error (not 404) is its own honest state — not "expired", not a blank page', async () => {
    vi.mocked(publicLookService.getPublicLook).mockRejectedValue({ status: 500 });
    renderPublic();

    expect(await screen.findByText(i18n.t('shared_look.error_title'))).toBeInTheDocument();
    expect(screen.queryByText(i18n.t('shared_look.unavailable_title'))).toBeNull();
  });

  it('ready: renders the card from the public-safe DTO + viewer re-share of the CURRENT url', async () => {
    vi.mocked(publicLookService.getPublicLook).mockResolvedValue(READY_LOOK as never);
    renderPublic('tok_live');

    expect(await screen.findByTestId('outfit-share-card')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: i18n.t('share.copy_link') })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: i18n.t('shared_look.download_png') })).toBeInTheDocument();
  });

  it('PNG export failure is announced inline in a live region — no alert()', async () => {
    vi.mocked(publicLookService.getPublicLook).mockResolvedValue(READY_LOOK as never);
    vi.mocked(toPng).mockRejectedValue(new Error('canvas tainted'));
    renderPublic('tok_live');

    fireEvent.click(await screen.findByRole('button', { name: i18n.t('shared_look.download_png') }));

    await waitFor(() => {
      const statuses = screen.getAllByRole('status');
      expect(statuses.some((s) => s.textContent === i18n.t('shared_look.png_failed'))).toBe(true);
    });
  });
});

// ===========================================================================
// D. axe + RTL + keyboard + reduced motion
// ===========================================================================
const JSDOM_UNCOMPUTABLE = ['color-contrast', 'target-size'];
async function expectNoSeriousViolations(node: HTMLElement, label: string) {
  const results = await axe(node, {
    rules: Object.fromEntries(JSDOM_UNCOMPUTABLE.map((r) => [r, { enabled: false }])),
  });
  const bad = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
  if (bad.length) throw new Error(`${label}: ${bad.map((v) => `${v.id} — ${v.help}`).join('; ')}`);
}

describe('axe / RTL / keyboard / reduced motion', () => {
  it('ShareActions EN/LTR: no critical/serious violations; buttons are keyboard-reachable', async () => {
    stubClipboard(() => Promise.resolve());
    stubNativeShare(() => Promise.resolve());
    const { container } = renderShare();
    await expectNoSeriousViolations(container, 'ShareActions EN');

    // Keyboard: buttons are native <button>s — Enter/Space work by contract;
    // verify they are in the tab order (no tabindex=-1 anywhere).
    for (const btn of screen.getAllByRole('button')) {
      expect(btn).not.toHaveAttribute('tabindex', '-1');
    }
  });

  it('Arabic/RTL: full flow functional + axe clean; URL stays LTR-safe (passed through verbatim)', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    try {
      const writeText = stubClipboard(() => Promise.resolve());
      const { container } = renderShare();
      fireEvent.click(screen.getByRole('button', { name: i18n.t('share.copy_link') }));
      await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.copied')));
      expect(writeText).toHaveBeenCalledExactlyOnceWith(URL_UNDER_TEST); // byte-identical URL
      await expectNoSeriousViolations(container, 'ShareActions AR/RTL');
    } finally {
      await act(async () => {
        await setAppLanguage('en');
      });
    }
  });

  it('reduced motion: states are text transitions, the whole flow works with animations disabled', async () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    try {
      stubClipboard(() => Promise.resolve());
      renderShare();
      fireEvent.click(screen.getByRole('button', { name: i18n.t('share.copy_link') }));
      await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(i18n.t('share.copied')));
    } finally {
      window.matchMedia = original;
    }
  });
});
