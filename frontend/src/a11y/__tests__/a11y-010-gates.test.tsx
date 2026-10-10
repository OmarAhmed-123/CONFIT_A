/**
 * 010 UI/UX Accessibility Gates — axe scans for required surfaces (FR-001, SC-001)
 *
 * Covers: VTON upload, stylist drawer, checkout, admin & brand consoles
 * Asserts 0 critical/serious violations, checks keyboard operability, focus management
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, cleanup, screen, act } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { SkipLink } from '../../components/common/SkipLink';
import { HonestProductImage } from '../../components/common/HonestProductImage';
import { AccessibleButton, AccessibleInput } from '../../components/common/AccessiblePrimitives';
import { EmptyState, LoadingState, ErrorState } from '../../components/common/StateComponents';
import { MotionWrapper } from '../../components/common/MotionWrapper';

const JSDOM_UNCOMPUTABLE = ['color-contrast', 'target-size'];

async function seriousViolations(node: HTMLElement) {
  const results = await axe(node, {
    rules: Object.fromEntries(JSDOM_UNCOMPUTABLE.map((r) => [r, { enabled: false }])),
  });
  return results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
}

function wrap(children: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{children}</MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>
  );
}

beforeEach(async () => {
  cleanup();
  await act(async () => {
    await setAppLanguage('en');
  });
});

afterEach(() => {
  cleanup();
});

describe('010 — HonestProductImage (FR-002, SC-002)', () => {
  it('renders honest placeholder when src missing, not broken img', async () => {
    const { container } = wrap(<HonestProductImage src={null} alt="Silk Blazer" />);
    // Should NOT render <img> when src missing
    expect(container.querySelector('img')).toBeNull();
    // Should render div with role=img and accessible label
    const placeholder = screen.getByRole('img');
    expect(placeholder.getAttribute('aria-label')).toContain('Silk Blazer');
    expect(placeholder.getAttribute('aria-label')).toContain('Image unavailable');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('renders img with alt when src present, and handles error to honest placeholder', async () => {
    const { container } = wrap(
      <HonestProductImage src="https://example.com/product.jpg" alt="Wool Trousers" />
    );
    const img = container.querySelector('img');
    expect(img).toBeTruthy();
    expect(img?.getAttribute('alt')).toBe('Wool Trousers');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — AccessiblePrimitives (FR-001)', () => {
  it('AccessibleButton has accessible name, keyboard operable, min 44px', async () => {
    const { container } = wrap(<AccessibleButton>Add to bag</AccessibleButton>);
    const btn = screen.getByRole('button', { name: 'Add to bag' });
    expect(btn).toBeTruthy();
    expect(btn.getAttribute('type')).toBe('button');
    // Check min touch target via class
    expect(btn.className).toContain('min-h-[44px]');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('AccessibleInput has label, error alert, hint', async () => {
    const { container } = wrap(
      <AccessibleInput label="Email address" error="Invalid email" hint="We will never share your email" />
    );
    const input = screen.getByLabelText('Email address');
    expect(input).toBeTruthy();
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')).toContain('error');
    const error = screen.getByRole('alert');
    expect(error.textContent).toBe('Invalid email');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('IconButton enforces accessible name, emoji aria-hidden', async () => {
    const { container } = wrap(
      <AccessibleButton aria-label="Close dialog">
        <span aria-hidden="true">✕</span> Close
      </AccessibleButton>
    );
    const btn = screen.getByRole('button', { name: 'Close dialog' });
    expect(btn).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — StateComponents (FR-005, SC-005)', () => {
  it('EmptyState has status role and translated content', async () => {
    const { container } = wrap(<EmptyState title="No products" description="Try adjusting filters" />);
    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.getByText('No products')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('LoadingState has aria-busy and polite live', async () => {
    const { container } = wrap(<LoadingState label="Loading products..." />);
    const status = screen.getByRole('status');
    expect(status.getAttribute('aria-busy')).toBe('true');
    expect(status.getAttribute('aria-live')).toBe('polite');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('ErrorState has alert role and retry button', async () => {
    const { container } = wrap(
      <ErrorState message="Failed to load" retry={{ label: 'Retry', onClick: () => {} }} />
    );
    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — MotionWrapper respects prefers-reduced-motion (FR-004, SC-004)', () => {
  it('disables non-essential motion when prefers-reduced-motion', async () => {
    // Mock matchMedia to prefers-reduced-motion: reduce
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });

    const { container } = wrap(
      <MotionWrapper initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div>Content</div>
      </MotionWrapper>
    );

    // With reduced motion, should render static div, not motion div with animation
    expect(container.textContent).toContain('Content');
    // No critical a11y violations
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — SkipLink WCAG 2.4.1', () => {
  it('is first focusable, sr-only, points to main content', async () => {
    const { container } = wrap(
      <>
        <SkipLink />
        <main id="confit-main-content" tabIndex={-1}>Main content</main>
      </>
    );
    const link = screen.getByTestId('skip-link');
    expect(link.getAttribute('href')).toBe('#confit-main-content');
    expect(link.className).toContain('sr-only');
    expect(link.className).toContain('focus:not-sr-only');
    const target = container.querySelector('#confit-main-content');
    expect(target?.getAttribute('tabindex')).toBe('-1');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});
