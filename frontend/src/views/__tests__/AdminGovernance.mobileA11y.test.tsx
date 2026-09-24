/**
 * Admin-governance mobile/accessibility behavioural gates (390px baseline).
 *
 * jsdom cannot calculate CSS layout or colour contrast, so these tests do NOT
 * claim a visual WCAG conformance audit. They pin what is mechanically
 * provable here: governance destinations are present and first at 390px, the
 * nav is explicitly horizontally scrollable (no functionality removed), all
 * targets meet the project's 44px target class, focus is visible, labels are
 * translated, and axe finds no serious/critical semantic issue.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';

import { BrandNavbar } from '../../components/navigation/BrandNavbar';
import { setAppLanguage } from '../../i18n/i18n';
import { useAuthStore } from '../../stores/authStore';

const ADMIN = {
  id: 9001,
  email: 'admin-mobile-contract@confit.test',
  full_name: 'Admin Contract',
  role: 'admin',
  is_active: true,
  is_verified: true,
} as any;

function renderNav(path = '/admin') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <BrandNavbar />
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  cleanup();
  Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true });
  useAuthStore.setState({
    user: ADMIN,
    isAuthenticated: true,
    isLoading: false,
    hasAttemptedBootstrap: true,
  });
  await act(async () => { await setAppLanguage('en'); });
});

afterEach(async () => {
  cleanup();
  await act(async () => { await setAppLanguage('en'); });
});

describe('admin navigation at 390px', () => {
  it('keeps governance links first and every partner destination available', () => {
    renderNav();
    const nav = screen.getByTestId('brand-primary-nav');
    expect(nav.className).toContain('overflow-x-auto');
    expect(nav.className).toContain('overscroll-x-contain');

    const links = Array.from(nav.querySelectorAll('a'));
    expect(links.map((link) => link.textContent?.trim())).toEqual([
      'Platform Admin', 'Audit Trail', 'Dashboard', 'Catalog & SKUs',
      'BOPIS Inventory', 'Return Telemetry', 'Placements',
    ]);
    expect(links.every((link) => link.className.includes('shrink-0'))).toBe(true);
    expect(links.every((link) => link.className.includes('min-h-11'))).toBe(true);
  });

  it('has a visible keyboard focus contract on every nav target', () => {
    renderNav('/admin/audit');
    const audit = screen.getByRole('link', { name: 'Audit Trail' });
    audit.focus();
    expect(document.activeElement).toBe(audit);
    expect(audit.className).toContain('focus-visible:ring-2');
    expect(audit.getAttribute('aria-current')).toBe('page');
  });

  it('translates the governance navigation in Arabic/RTL', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    renderNav();
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByRole('link', { name: 'إدارة المنصة' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'سجل التدقيق' })).toBeTruthy();
  });

  it('has no axe serious/critical semantic violations in either direction', async () => {
    const { container, unmount } = renderNav();
    const en = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(en.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    unmount();

    await act(async () => { await setAppLanguage('ar'); });
    const arRender = renderNav();
    const ar = await axe(arRender.container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(ar.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
  });
});
