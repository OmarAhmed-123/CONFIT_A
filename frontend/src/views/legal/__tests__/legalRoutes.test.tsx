/**
 * Legal-route verification (audit 2026-09-21).
 *
 * The audit's exact finding about these pages:
 *
 *   «/privacy و/terms و/gdpr رجّعوا HTTP 200 — لكن ده مش دليل على أن النص
 *   القانوني كامل أو محدّث، ولا على أن الترجمة العربية مكافئة.»
 *
 * An HTTP 200 from a single-page application proves ONE thing: index.html was
 * served. It cannot see whether React mounted, whether the route resolved,
 * whether the copy is the current version, or whether the Arabic page contains
 * Arabic. These tests render the real route table and assert on the content,
 * which is what the status code could not do.
 *
 * They also pin the two regression risks that a status-code check ignores:
 *   · the pages drifting back behind the auth gate (they were once reachable
 *     only through /profile, which showed "Authentication Required"), and
 *   · the legal text becoming a decorative shell again.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { AppRoutes } from '../../../router/AppRoutes';
import { LEGAL_VERSION, LEGAL_LAST_UPDATED, PHOTO_RETENTION_HOURS } from '../LegalViews';

const LEGAL_PATHS = ['/privacy', '/terms', '/gdpr', '/privacy-policy', '/terms-of-service'];

function renderRoute(route: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[route]}>
          <AppRoutes />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => setAppLanguage('en'));
afterEach(() => {
  cleanup();
  setAppLanguage('en');
});

describe('every legal path resolves to real content', () => {
  it.each(LEGAL_PATHS)('%s mounts and renders a heading, not just the app shell', async (route) => {
    renderRoute(route);
    await waitFor(() => {
      expect(screen.getAllByRole('heading').length).toBeGreaterThan(0);
    });
  });

  it('is reachable without an account — no auth wall in front of the policy', () => {
    renderRoute('/privacy');
    // These pages used to be reachable only through /profile, which showed the
    // "Authentication Required" screen to a logged-out visitor following the
    // footer's own Privacy link.
    expect(document.body.textContent).not.toMatch(/Authentication Required/i);
    expect(document.body.textContent).toContain(i18n.t('legal.privacy_h1'));
  });
});

describe('the privacy policy is complete, current, and bound to its sources of truth', () => {
  it('renders every section heading of the policy', () => {
    renderRoute('/privacy');
    for (const key of ['privacy_h1', 'privacy_h2', 'privacy_h3', 'privacy_h4', 'privacy_h5', 'privacy_h6']) {
      expect(screen.getByText(i18n.t(`legal.${key}`)), `missing section ${key}`).toBeTruthy();
    }
  });

  it('states the version and the last-updated date it actually carries', () => {
    renderRoute('/privacy');
    const text = document.body.textContent!;
    expect(text).toContain(LEGAL_VERSION);
    expect(text).toContain('2026'); // year of LEGAL_LAST_UPDATED, locale-formatted
  });

  it('derives the photo-retention figure from the shared constant', () => {
    renderRoute('/privacy');
    // The number in the policy, the number in the consent notice and the number
    // the footer discloses all come from PHOTO_RETENTION_HOURS: a policy that
    // hard-typed "24 hours" in prose could silently disagree with the product.
    expect(document.body.textContent).toContain(
      i18n.t('legal.privacy_retention_photos_value', { hours: PHOTO_RETENTION_HOURS }),
    );
  });

  it('carries the explicit "what we do NOT do" statements', () => {
    renderRoute('/privacy');
    const text = document.body.textContent!;
    expect(text).toContain(i18n.t('legal.privacy_not_sell'));
    expect(text).toContain(i18n.t('legal.privacy_not_train'));
  });

  it('exposes the withdrawal surface required by GDPR Art.7(3)', () => {
    renderRoute('/privacy');
    // The policy describes the right to withdraw consent; this is the control
    // that exercises it, on the same page that promises it.
    expect(screen.getByTestId('consent-manager')).toBeTruthy();
  });

  it('names processors and payment status honestly (demo mode)', () => {
    renderRoute('/privacy');
    const text = document.body.textContent!;
    expect(text).toContain(i18n.t('legal.privacy_processors_hosting'));
    expect(text).toContain(i18n.t('legal.privacy_processors_payments'));
    expect(i18n.t('legal.privacy_processors_payments')).toMatch(/demo/i);
  });

  it('publishes a change log so a reader can tell this version from the last', () => {
    renderRoute('/privacy');
    expect(screen.getByText(i18n.t('legal.change_log_title'))).toBeTruthy();
    expect(document.body.textContent).toContain(LEGAL_VERSION);
  });
});

describe('the terms state the product it actually is', () => {
  it('declares Demo Payment Mode rather than implying live payments', () => {
    renderRoute('/terms');
    const text = document.body.textContent!;
    expect(text).toContain(i18n.t('legal.terms_cap_demo_payments'));
    expect(i18n.t('legal.terms_cap_demo_payments')).toMatch(/demo/i);
  });

  it('conditions virtual try-on on the GPU worker being configured', () => {
    renderRoute('/terms');
    expect(document.body.textContent).toContain(i18n.t('legal.terms_cap_vton'));
  });

  it('states the limits of AI styling advice', () => {
    renderRoute('/terms');
    expect(document.body.textContent).toContain(i18n.t('legal.terms_cap_ai'));
  });
});

describe('the Arabic legal pages are translations, not an English fallback', () => {
  it('renders Arabic text and the same section structure in ar', async () => {
    await act(async () => {
      setAppLanguage('ar');
    });
    renderRoute('/privacy');
    const text = document.body.textContent!;
    expect(/[\u0600-\u06FF]/.test(text)).toBe(true);

    // Structural parity: each Arabic heading must exist AND be the Arabic
    // string. A missing translation would fall back to English here, which is
    // exactly what the audit could not rule out from an HTTP status code.
    for (const key of ['privacy_h1', 'privacy_h2', 'privacy_h4', 'privacy_h6']) {
      const arabic = i18n.getFixedT('ar')(`legal.${key}`);
      expect(/[\u0600-\u06FF]/.test(arabic), `${key} is not Arabic`).toBe(true);
      expect(text, `missing Arabic section ${key}`).toContain(arabic);
    }
    expect(text).not.toContain(i18n.getFixedT('en')('legal.privacy_h1'));
  });

  it('renders the Arabic terms and GDPR pages too', async () => {
    await act(async () => {
      setAppLanguage('ar');
    });
    for (const route of ['/terms', '/gdpr']) {
      cleanup();
      renderRoute(route);
      const text = document.body.textContent!;
      expect(/[\u0600-\u06FF]/.test(text), `${route} has no Arabic`).toBe(true);
    }
  });
});

describe('the legal text keeps its distance from withdrawn claims', () => {
  it('never claims on-device biometrics or face recognition', () => {
    for (const route of LEGAL_PATHS) {
      cleanup();
      renderRoute(route);
      const text = document.body.textContent!;
      expect(text, route).not.toMatch(/on-device biometrics?/i);
      expect(text, route).not.toMatch(/face recognition (is|runs)/i);
    }
  });

  it('does not publish the withdrawn placeholder contact address', () => {
    for (const route of LEGAL_PATHS) {
      cleanup();
      renderRoute(route);
      // privacy@confit.io was never a verified mailbox. The page now either
      // shows the configured address or says plainly that none is configured.
      expect(document.body.textContent, route).not.toContain('privacy@confit.io');
    }
  });
});
