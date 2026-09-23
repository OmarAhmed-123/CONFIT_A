/**
 * Commerce-claim contract tests (audit 2026-09-21).
 *
 * The audit's finding: «بعض الوعود التسويقية في footer مثل BNPL وBOPIS
 * والقياسات الحيوية تحتاج شروطًا وموافقة وحدود توفر واضحة» — the footer made
 * commercial promises the deployment could not keep, and the audit could not
 * tell how they were bound to anything.
 *
 * These tests are written from the adversarial direction: for each claim, the
 * assertion is that the UNFLATTERING branch is taken when the deployment cannot
 * support it. A test that only checked the happy path would pass on the same
 * page the audit objected to.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { render, screen, cleanup, act } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { TrustFooter } from '../TrustFooter';
import type { Capabilities } from '../../../hooks/useCapabilities';

const mockState = vi.hoisted(() => ({
  capabilities: {} as Record<string, unknown>,
  isLoading: false,
}));

vi.mock('../../../hooks/useCapabilities', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../hooks/useCapabilities')>();
  return {
    ...actual,
    useCapabilities: () => ({
      capabilities: mockState.capabilities as unknown as Capabilities,
      isLoading: mockState.isLoading,
    }),
  };
});

const LIVE: Capabilities = {
  payments_live: false,
  payments_mode: 'demo',
  bnpl_live: false,
  bopis_live: true,
  bopis_store_count: 1,
  returns_window_days: 30,
  storage_mode: 'local',
} as Capabilities;

function renderFooter() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/']}>
        <TrustFooter />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

const setCaps = (over: Partial<Capabilities>) => {
  mockState.capabilities = { ...LIVE, ...over };
};

beforeEach(() => {
  mockState.isLoading = false;
  setCaps({});
  setAppLanguage('en');
});

afterEach(() => {
  cleanup();
  setAppLanguage('en');
});

describe('no claim may be rendered while the truth is still unknown', () => {
  it('shows a skeleton and NO claim text while capabilities load', () => {
    mockState.isLoading = true;
    renderFooter();
    expect(document.querySelector('[aria-busy="true"]')).toBeTruthy();
    // The failure being guarded is a flash of the flattering claim followed by
    // a correction — which is exactly as misleading, just briefly.
    expect(screen.queryByTestId('trust-footer')).toBeNull();
    expect(document.body.textContent).not.toMatch(/BNPL|Tabby|day|instalment/i);
  });
});

describe('BNPL is only claimed when the deployment can actually take it', () => {
  it('does not name an instalment provider when bnpl_live is false', () => {
    setCaps({ bnpl_live: false });
    renderFooter();
    const text = screen.getByTestId('trust-footer').textContent!;
    // Naming Tabby/Tamara to a shopper at checkout who cannot select them is
    // the specific falsehood the audit found on the live deployment.
    expect(text).not.toMatch(/Tabby|Tamara/);
    expect(text).toContain(i18n.t('footer.bnpl_unavailable'));
  });

  it('names the providers only when the flag is live', () => {
    setCaps({ bnpl_live: true });
    renderFooter();
    const text = screen.getByTestId('trust-footer').textContent!;
    expect(text).toContain(i18n.t('footer.bnpl_brand_name_full'));
    // The message must consume the parameter the call site passes: this key
    // read "({{count}} provider(s))" while the component passed `providers`,
    // so production rendered the literal "{{count}}" (see gate check 7).
    expect(text).not.toContain('{{');
    expect(text).not.toContain(i18n.t('footer.bnpl_unavailable'));
  });
});

describe('the numbers come from the server, and are validated before they are printed', () => {
  it('prints the BOPIS store count from the API', () => {
    setCaps({ bopis_live: true, bopis_store_count: 7 });
    renderFooter();
    expect(screen.getByTestId('trust-footer').textContent).toContain('7');
  });

  it('does not promise pickup when bopis is live but there are no stores', () => {
    setCaps({ bopis_live: true, bopis_store_count: 0 });
    renderFooter();
    const text = screen.getByTestId('trust-footer').textContent!;
    // "Pickup at 0 stores" is not a promise a storefront should make.
    expect(text).toContain(i18n.t('footer.bopis_unavailable'));
  });

  it('prints the returns window the server reports', () => {
    setCaps({ returns_window_days: 30 });
    renderFooter();
    expect(screen.getByTestId('trust-footer').textContent).toContain('30');
  });

  it('never renders a "0-day" or "undefined-day" returns promise', () => {
    for (const bad of [0, null, undefined, NaN, -1, 'thirty']) {
      cleanup();
      setCaps({ returns_window_days: bad as unknown as number });
      renderFooter();
      const text = screen.getByTestId('trust-footer').textContent!;
      expect(text, `returns_window_days=${String(bad)}`).not.toMatch(/0-day|undefined|NaN|-1-day/);
      expect(text).toContain(i18n.t('footer.returns_unavailable'));
    }
  });
});

describe('the withdrawn biometrics claim stays withdrawn', () => {
  it('makes no on-device or biometric claim anywhere in the footer', () => {
    renderFooter();
    const text = screen.getByTestId('trust-footer').textContent!;
    for (const phrase of [
      'on-device',
      'On-Device',
      'biometric',
      'Biometric',
      'face recognition',
      'MediaPipe',
    ]) {
      expect(text, `footer claims "${phrase}"`).not.toContain(phrase);
    }
  });

  it('the phrase is gone from the source tree, not just from the rendered DOM', () => {
    // The audit's subject is the ARABIC experience too, and a hidden or
    // AR-only string would not appear in the English DOM above.
    const srcDir = path.resolve(__dirname, '../../..');
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, e.name);
        if (e.isDirectory()) {
          if (e.name === '__tests__' || e.name === 'node_modules') continue;
          walk(full);
        } else if (/\.(tsx?|json)$/.test(e.name) && !e.name.includes('.test.')) {
          const src = fs
            .readFileSync(full, 'utf8')
            // Strip comments: a comment that QUOTES the withdrawn claim while
            // explaining why it was withdrawn is documentation, not a claim.
            .replace(/\/\*[\s\S]*?\*\//g, '')
            .replace(/^\s*\/\/.*$/gm, '');
          if (/on-device biometric|VITE_MP_|mediapipe|pose_landmarker/i.test(src)) {
            offenders.push(path.relative(srcDir, full));
          }
        }
      }
    };
    walk(srcDir);
    expect(offenders).toEqual([]);
  });
});

describe('the disclosure is reachable and localized', () => {
  it('links to the real privacy policy', () => {
    renderFooter();
    const links = screen.getAllByRole('link');
    const privacy = links.find((l) => l.getAttribute('href') === '/privacy');
    expect(privacy, 'footer must link to /privacy').toBeTruthy();
  });

  it('renders Arabic claims in Arabic, with no English leakage', async () => {
    await act(async () => {
      setAppLanguage('ar');
    });
    setCaps({ bnpl_live: true, bopis_live: true, bopis_store_count: 2 });
    renderFooter();
    const text = screen.getByTestId('trust-footer').textContent!;
    expect(/[\u0600-\u06FF]/.test(text)).toBe(true);
    expect(text).not.toContain(i18n.getFixedT('en')('footer.bopis_available', { count: 2 }));
  });

  it('states the COD-only truth instead of claiming no goods are shipped', () => {
    // 2026-09-23 hardening. `payments_live` had been `bool(PAYMENTS_LIVE)`, so
    // one env var published "Card payments are processed by a live payment
    // service provider." on a deployment with no key and no adapter. The flag
    // is now measured; this pins the *other* half of the same honesty problem —
    // when no PSP rail is live but cash on delivery settles, the demo
    // disclosure's "no goods are shipped" is false for a COD order.
    setCaps({ payments_live: false, cod_live: true, bopis_live: true, bopis_store_count: 1 });
    renderFooter();
    const text = screen.getByTestId('trust-footer').textContent!;
    expect(text).toContain(i18n.getFixedT('en')('footer.payment_mode_disclosure_cod'));
    expect(text).not.toContain(i18n.getFixedT('en')('footer.payment_mode_disclosure'));
    expect(text).not.toContain(i18n.getFixedT('en')('footer.payments_live'));
  });

  it('claims a live payment provider only when the server measured one', () => {
    setCaps({ payments_live: true, cod_live: true, bopis_live: true, bopis_store_count: 1 });
    renderFooter();
    expect(screen.getByTestId('trust-footer').textContent).toContain(
      i18n.getFixedT('en')('footer.payments_live'),
    );
  });

  it('falls back to the plain demo disclosure when nothing can settle', () => {
    setCaps({ payments_live: false, cod_live: false, bopis_live: false, bopis_store_count: 0 });
    renderFooter();
    expect(screen.getByTestId('trust-footer').textContent).toContain(
      i18n.getFixedT('en')('footer.payment_mode_disclosure'),
    );
  });
});
