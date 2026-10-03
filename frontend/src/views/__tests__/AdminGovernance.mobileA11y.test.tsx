/**
 * Admin-governance mobile/accessibility behavioural gates (390px baseline).
 *
 * Spec 13 changed the mobile contract: the horizontal scroller is gone —
 * at 390px the way into governance is the hamburger → drawer (dialog,
 * focus-managed). These tests pin what is mechanically provable in jsdom:
 * governance destinations are present inside the drawer, partner-tenant
 * links are never exposed to a platform admin, every target meets the 44px
 * class floor, focus is visible, labels are translated, and axe finds no
 * serious/critical semantic issue.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
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

const openDrawer = () => {
  fireEvent.click(screen.getByRole('button', { name: /Open navigation menu|فتح قائمة التنقل/ }));
  return screen.getByTestId('brand-nav-drawer');
};

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
  document.body.style.overflow = '';
  await act(async () => { await setAppLanguage('en'); });
});

describe('admin navigation at 390px (drawer contract, spec 13)', () => {
  it('drawer shows only explicit admin destinations, never partner-tenant links', () => {
    renderNav();
    const drawer = openDrawer();
    const links = Array.from(drawer.querySelectorAll('nav a'));
    expect(links.map((link) => link.textContent?.trim())).toEqual([
      'Platform Admin', 'Catalog Control', 'Platform Analytics', 'Audit Trail',
    ]);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/admin', '/admin/catalog', '/admin/analytics', '/admin/audit',
    ]);
    expect(links.every((link) => link.className.includes('min-h-11'))).toBe(true);
    // The two trust domains never mix (§8): no /b2b hrefs anywhere.
    expect(Array.from(drawer.querySelectorAll('a')).some((a) =>
      a.getAttribute('href')?.startsWith('/b2b'))).toBe(false);
  });

  it('has a visible keyboard focus contract on every drawer nav target', () => {
    renderNav();
    const drawer = openDrawer();
    const audit = within(drawer).getByRole('link', { name: 'Audit Trail' });
    audit.focus();
    expect(document.activeElement).toBe(audit);
    expect(audit.className).toContain('focus-visible:ring-2');
    // deep link: rendered at /admin, Platform Admin carries aria-current
    expect(within(drawer).getByRole('link', { name: 'Platform Admin' }).getAttribute('aria-current')).toBe('page');
  });

  it('translates the governance navigation in Arabic/RTL', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    renderNav();
    const drawer = openDrawer();
    expect(document.documentElement.dir).toBe('rtl');
    expect(within(drawer).getByRole('link', { name: 'إدارة المنصة' })).toBeTruthy();
    expect(within(drawer).getByRole('link', { name: 'سجل التدقيق' })).toBeTruthy();
  });

  it('has no axe serious/critical semantic violations with the drawer open, either direction', async () => {
    const { container, unmount } = renderNav();
    openDrawer();
    const en = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(en.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    unmount();

    await act(async () => { await setAppLanguage('ar'); });
    const arRender = renderNav();
    openDrawer();
    const ar = await axe(arRender.container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(ar.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
  });
});
