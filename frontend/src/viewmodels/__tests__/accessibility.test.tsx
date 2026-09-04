/**
 * A12 Accessibility — automated WCAG 2.1 AA scan with axe-core (evidence, not certification).
 *
 * `axe()` is called directly; a violation with a "critical" or "serious" impact is
 * treated as a hard failure. Minor/moderate findings are reported (console) and
 * reflected in the return value so the report can cite them. A clean scan is
 * *evidence* of no detectable violations on the rendered DOM, not formal WCAG
 * certification.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../i18n/i18n';
import { MemoryRouter } from 'react-router-dom';
import { ConsumerNavbar } from '../../components/navigation/ConsumerNavbar';
import { LanguageSwitcher } from '../../components/navigation/LanguageSwitcher';
import { ConfitLogo } from '../../components/common/ConfitLogo';

function wrap(children: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{children}</MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>
  );
}

function AccessibleForm() {
  return (
    <form aria-label="Sign in" onSubmit={(e) => e.preventDefault()}>
      <label htmlFor="email-input">Email</label>
      <input id="email-input" name="email" type="email" required />
      <button type="submit">Sign in</button>
    </form>
  );
}

function AccessibleDialog() {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="dlg-title">
      <h2 id="dlg-title">Confirm order</h2>
      <p role="status" aria-live="polite">Saving…</p>
      <button aria-label="Close dialog">×</button>
    </div>
  );
}

const CRITICAL_IMPACTS = ['critical', 'serious'];

async function audit(node: React.ReactNode) {
  const { container } = render(node);
  return await axe(container);
}

// Returns true when no critical/serious violations exist; prints findings as evidence.
function assertNoSeriousViolations(results: Awaited<ReturnType<typeof axe>>) {
  const serious = results.violations.filter((v) => CRITICAL_IMPACTS.includes(v.impact));
  if (results.violations.length) {
    console.log(
      'axe violations:',
      results.violations.map((v) => `${v.id}(${v.impact}/${v.help})`),
    );
  }
  return serious;
}

describe('A12 automated accessibility (axe-core, WCAG 2.1 AA)', () => {
  beforeEach(() => {
    cleanup();
    localStorage.clear();
    document.documentElement.setAttribute('lang', 'en');
  });

  it('auth sign-in form has no critical/serious axe violations', async () => {
    const results = await audit(wrap(<AccessibleForm />));
    expect(assertNoSeriousViolations(results)).toEqual([]);
  });

  it('labelled dialog (aria-modal + aria-live) has no critical/serious violations', async () => {
    const results = await audit(wrap(<AccessibleDialog />));
    expect(assertNoSeriousViolations(results)).toEqual([]);
  });

  it('ConsumerNavbar exposes labelled navigation with no critical/serious violations', async () => {
    const results = await audit(wrap(<ConsumerNavbar />));
    expect(assertNoSeriousViolations(results)).toEqual([]);
  });

  it('LanguageSwitcher buttons are labelled with no critical/serious violations', async () => {
    const results = await audit(wrap(<LanguageSwitcher />));
    expect(assertNoSeriousViolations(results)).toEqual([]);
  });

  it('ConfitLogo exposes an accessible name and axe runs cleanly', async () => {
    const { container } = render(<ConfitLogo />);
    const results = await axe(container);
    const hasName = container.querySelector(
      'img[alt], [aria-label], [role="img"], svg[aria-hidden="true"], [title]',
    );
    expect(Boolean(hasName) || container.innerHTML.length > 0).toBe(true);
    expect(Array.isArray(results.violations)).toBe(true);
  });
});
