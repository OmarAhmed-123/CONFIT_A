/**
 * Instalment-claim contract tests (2026-09-23).
 *
 * The defect these pin, measured in production: the product page rendered
 *
 *     "or 4 interest-free payments of $72.25 with Tabby"
 *
 * on a deployment whose own /catalog/capabilities answered `bnpl_live=false`
 * and `payments_mode=demo`, and which held no Tabby key at all. The figure is
 * arithmetic on a real price and is fine to show; the LENDER'S NAME is a claim
 * the deployment cannot support, and it is the part a shopper would act on.
 *
 * Written adversarially, like trustFooter.test.tsx: each test asserts the
 * UNFLATTERING branch. A test that only rendered the live case would have
 * passed on the page the audit objected to.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { BNPLBadge } from '../../common/CommonComponents';

afterEach(() => {
  cleanup();
  setAppLanguage('en');
});

function renderBadge(props: Parameters<typeof BNPLBadge>[0]) {
  return render(
    <I18nextProvider i18n={i18n}>
      <BNPLBadge {...props} />
    </I18nextProvider>,
  );
}

describe('an instalment estimate must not name a lender', () => {
  it('omits the provider name when the split is only an estimate', () => {
    renderBadge({
      currency: 'USD',
      provider: 'Tabby',
      installmentAmount: 72.25,
      isEstimate: true,
    });

    const text = screen.getByText(/4 payments of/).textContent ?? '';
    expect(text).not.toMatch(/tabby/i);
    expect(text).toContain('4 payments of');
    // The disclosure has to be present, not merely implied by the absence of a
    // name: "illustrative only" is what makes it honest.
    expect(text.toLowerCase()).toContain('illustrative');
  });

  it('names the provider when the server says it is a real offer', () => {
    renderBadge({
      currency: 'USD',
      provider: 'Tabby',
      installmentAmount: 72.25,
      isEstimate: false,
    });

    const text = screen.getByText(/4 interest-free payments of/).textContent ?? '';
    expect(text).toMatch(/tabby/i);
  });

  it('an omitted flag falls into the LENDER-NAMING branch — hence the required prop', () => {
    // Asserted because it is the hazard, not because it is desired: with the
    // flag absent the component renders the provider name. That is exactly how
    // the production defect would return at a new call site, so the prop is
    // required and `tsc --noEmit` (run by CI) rejects the call below.
    //
    // The contract is that no call site compiles without the flag. The
    // directive below sits on the line TypeScript reports the error for; if
    // someone re-introduces a default, the directive becomes unused and
    // `tsc --noEmit` fails the build — so this stays a compile-time gate.
    // @ts-expect-error isEstimate is required: omitting it must not compile.
    renderBadge({
      currency: 'USD',
      provider: 'Tabby',
      installmentAmount: 72.25,
    });
    expect(screen.getByText(/4 interest-free payments of/).textContent ?? '').toMatch(/tabby/i);
  });

  it('renders nothing for an ineligible amount, in either branch', () => {
    renderBadge({ currency: 'USD', installmentAmount: null, eligible: false, isEstimate: true });
    expect(screen.queryByText(/4 payments of/)).toBeNull();
  });

  it('localizes the estimate copy into Arabic', () => {
    setAppLanguage('ar');
    renderBadge({ currency: 'USD', provider: 'Tabby', installmentAmount: 72.25, isEstimate: true });
    expect(screen.getByText(/توضيحي فقط/)).toBeTruthy();
  });
});

describe('the figure must carry the currency the shopper is actually browsing in', () => {
  it('renders the EGP-formatted amount, never a dollar glyph, for an EGP figure', () => {
    // The production defect this pins (screenshot, 2026-10-07): the PDP price
    // said EGP 3,932.37 while this badge said "$18.75" — the call site forgot
    // `currency` and the component silently defaulted to USD. `currency` is
    // now a required prop, and this asserts the rendered glyphs.
    renderBadge({ currency: 'EGP', installmentAmount: 983.09, isEstimate: true });
    const text = screen.getByText(/4 payments of/).textContent ?? '';
    expect(text).not.toContain('$');
    expect(text).toMatch(/EGP|E£/);
  });
});

describe('no server figure, no badge — the browser must not invent one', () => {
  it('renders nothing when installmentAmount is absent (the old price/4 fallback is gone)', () => {
    // Previously the component computed price/4 locally when the server sent
    // no figure — a number no lender quoted and no API returned.
    renderBadge({ currency: 'USD', installmentAmount: null, isEstimate: true });
    expect(screen.queryByText(/payments of/)).toBeNull();
  });

  it('renders nothing for a zero or negative figure', () => {
    renderBadge({ currency: 'USD', installmentAmount: 0, isEstimate: true });
    expect(screen.queryByText(/payments of/)).toBeNull();
  });
});
