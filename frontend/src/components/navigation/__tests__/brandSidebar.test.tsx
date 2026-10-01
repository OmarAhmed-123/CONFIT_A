/**
 * Spec 13 — responsive sidebar/drawer (§10 test contract):
 *   role matrix (admin never sees partner controls and vice versa) ·
 *   drawer open/close/Escape/scrim/route-change with focus save+restore ·
 *   deep links set aria-current · collapse state (persisted, announced
 *   as polite TEXT, names survive collapse) · breadcrumbs from the same
 *   role-gated config · skip link still first in the layout · 320px ·
 *   axe EN + AR/RTL · reduced-motion class contract.
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { axe } from 'vitest-axe';

import { BrandNavbar, BrandBreadcrumbs, sectionsForRole } from '../BrandNavbar';
import { BrandLayout } from '../../../layouts/BrandLayout';
import { setAppLanguage } from '../../../i18n/i18n';
import { useAuthStore } from '../../../stores/authStore';

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

const makeUser = (role: string) => ({
  id: 1,
  email: `${role}@confit.test`,
  full_name: `${role} user`,
  role,
  is_active: true,
  is_verified: true,
}) as any;

const setRole = (role: string) =>
  useAuthStore.setState({
    user: makeUser(role),
    isAuthenticated: true,
    isLoading: false,
    hasAttemptedBootstrap: true,
  });

const renderNav = (path = '/b2b') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<BrandNavbar />} />
      </Routes>
    </MemoryRouter>,
  );

const openDrawer = () => {
  fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }));
  return screen.getByTestId('brand-nav-drawer');
};

beforeEach(async () => {
  cleanup();
  localStorage.clear();
  setRole('brand_owner');
  await act(async () => { await setAppLanguage('en'); });
});

afterEach(() => {
  cleanup();
  document.body.style.overflow = '';
});

/* ------------------------------------------------------------------ */
/* A. Role matrix (§6.1/§8/§9)                                         */
/* ------------------------------------------------------------------ */
describe('role-gated nav config', () => {
  it('partner config contains ONLY /b2b hrefs; admin config ONLY /admin', () => {
    const partnerHrefs = sectionsForRole(false).flatMap((s) => s.items.map((i) => i.href));
    const adminHrefs = sectionsForRole(true).flatMap((s) => s.items.map((i) => i.href));
    expect(partnerHrefs.every((h) => h.startsWith('/b2b'))).toBe(true);
    expect(adminHrefs.every((h) => h.startsWith('/admin'))).toBe(true);
    expect(partnerHrefs).toHaveLength(6);
    expect(adminHrefs).toHaveLength(4);
  });

  it('partner sidebar renders tenant sections and ZERO admin links', () => {
    renderNav('/b2b');
    const sidebar = screen.getByTestId('brand-sidebar');
    expect(screen.getByRole('group', { name: 'Operations' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Growth' })).toBeInTheDocument();
    expect(Array.from(sidebar.querySelectorAll('a')).some((a) =>
      a.getAttribute('href')?.startsWith('/admin'))).toBe(false);
  });

  it('admin sidebar renders governance sections and ZERO partner links', () => {
    setRole('admin');
    renderNav('/admin');
    const sidebar = screen.getByTestId('brand-sidebar');
    expect(screen.getByRole('group', { name: 'Governance' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Trust & Audit' })).toBeInTheDocument();
    expect(Array.from(sidebar.querySelectorAll('a')).some((a) =>
      a.getAttribute('href')?.startsWith('/b2b'))).toBe(false);
  });
});

/* ------------------------------------------------------------------ */
/* B. Drawer behaviour (§5/§6.2/§6.4)                                  */
/* ------------------------------------------------------------------ */
describe('mobile drawer', () => {
  it('opens as a modal dialog and moves focus to the close button', () => {
    renderNav('/b2b');
    const drawer = openDrawer();
    expect(drawer).toHaveAttribute('role', 'dialog');
    expect(drawer).toHaveAttribute('aria-modal', 'true');
    const close = screen.getByRole('button', { name: 'Close navigation menu' });
    expect(document.activeElement).toBe(close);
    expect(document.body.style.overflow).toBe('hidden');
  });

  it('Escape closes and focus RETURNS to the hamburger', () => {
    renderNav('/b2b');
    const hamburger = screen.getByRole('button', { name: 'Open navigation menu' });
    hamburger.focus();
    fireEvent.click(hamburger);
    const drawer = screen.getByTestId('brand-nav-drawer');
    fireEvent.keyDown(drawer, { key: 'Escape' });
    expect(screen.queryByTestId('brand-nav-drawer')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(hamburger);
    expect(document.body.style.overflow).toBe('');
  });

  it('clicking the scrim (outside) closes the drawer', () => {
    renderNav('/b2b');
    const drawer = openDrawer();
    const scrim = drawer.parentElement!.querySelector('[aria-hidden="true"]')!;
    fireEvent.click(scrim);
    expect(screen.queryByTestId('brand-nav-drawer')).not.toBeInTheDocument();
  });

  it('navigating from a drawer link closes it — content is never blocked (§8)', async () => {
    renderNav('/b2b');
    openDrawer();
    const { within } = await import('@testing-library/react');
    fireEvent.click(within(screen.getByTestId('brand-nav-drawer')).getByRole('link', { name: 'BOPIS Inventory' }));
    expect(screen.queryByTestId('brand-nav-drawer')).not.toBeInTheDocument();
  });

  it('Tab wraps inside the dialog — nothing behind it can take focus', () => {
    renderNav('/b2b');
    const drawer = openDrawer();
    const focusables = Array.from(
      drawer.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
    );
    const last = focusables[focusables.length - 1];
    last.focus();
    fireEvent.keyDown(drawer, { key: 'Tab' });
    expect(document.activeElement).toBe(focusables[0]);
  });
});

/* ------------------------------------------------------------------ */
/* C. Deep links + active route (§6.3/§6.5)                            */
/* ------------------------------------------------------------------ */
describe('active route from location', () => {
  it('a deep link marks exactly its sidebar item aria-current', () => {
    renderNav('/b2b/inventory');
    const sidebar = screen.getByTestId('brand-sidebar');
    const current = Array.from(sidebar.querySelectorAll('a[aria-current="page"]'));
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute('href', '/b2b/inventory');
  });

  it('legacy /partner/* alias still resolves the active item (no deep-link loss)', () => {
    renderNav('/partner/orders');
    const sidebar = screen.getByTestId('brand-sidebar');
    const current = sidebar.querySelector('a[aria-current="page"]');
    expect(current).toHaveAttribute('href', '/b2b/orders');
  });
});

/* ------------------------------------------------------------------ */
/* D. Collapse (§5 desktop expanded/collapsed)                         */
/* ------------------------------------------------------------------ */
describe('sidebar collapse', () => {
  it('toggle collapses, announces as polite text, keeps accessible names, persists', () => {
    renderNav('/b2b');
    const toggle = screen.getByRole('button', { name: 'Collapse sidebar' });
    expect(toggle.className).toContain('min-h-11');
    fireEvent.click(toggle);

    // state announced as TEXT, not only width (§7)
    const status = screen.getAllByRole('status').find((el) =>
      el.textContent?.includes('Sidebar collapsed'));
    expect(status).toBeTruthy();
    expect(status).toHaveAttribute('aria-live', 'polite');

    // labels hidden but names remain: links still findable by role+name
    expect(screen.getAllByRole('link', { name: 'BOPIS Inventory' }).length).toBeGreaterThan(0);
    expect(localStorage.getItem('confit.b2b.sidebar_collapsed')).toBe('true');
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('collapse state is restored on next render (persisted)', () => {
    localStorage.setItem('confit.b2b.sidebar_collapsed', 'true');
    renderNav('/b2b');
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument();
    expect(screen.getByTestId('brand-sidebar').className).toContain('w-[4.5rem]');
  });

  it('width animation is gated for reduced motion (motion-reduce class)', () => {
    renderNav('/b2b');
    expect(screen.getByTestId('brand-sidebar').className).toContain('motion-reduce:transition-none');
  });
});

/* ------------------------------------------------------------------ */
/* E. Breadcrumbs from the same config (§1)                            */
/* ------------------------------------------------------------------ */
describe('breadcrumbs', () => {
  const renderCrumbs = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <BrandBreadcrumbs />
      </MemoryRouter>,
    );

  it('admin deep page: home crumb + section + current page', () => {
    setRole('admin');
    renderCrumbs('/admin/audit');
    const nav = screen.getByRole('navigation', { name: 'You are here' });
    expect(nav.textContent).toContain('Platform Governance');
    expect(nav.textContent).toContain('Trust & Audit');
    const current = nav.querySelector('[aria-current="page"]');
    expect(current?.textContent).toBe('Audit Trail');
    expect(screen.getByRole('link', { name: 'Platform Governance' })).toHaveAttribute('href', '/admin');
  });

  it('unknown drill-down route keeps ONLY the honest home crumb — no invented label', () => {
    renderCrumbs('/b2b/catalog/product/42');
    const nav = screen.getByRole('navigation', { name: 'You are here' });
    expect(screen.getByRole('link', { name: 'Brand Partner Hub' })).toBeInTheDocument();
    expect(nav.querySelectorAll('li')).toHaveLength(1);
  });
});

/* ------------------------------------------------------------------ */
/* F. Layout: skip link survives the new shell (§6.6)                  */
/* ------------------------------------------------------------------ */
describe('BrandLayout shell', () => {
  it('skip link is still the first focusable thing before the sidebar', () => {
    render(
      <MemoryRouter initialEntries={['/b2b']}>
        <Routes>
          <Route element={<BrandLayout />}>
            <Route path="/b2b" element={<p>content</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link');
    expect(links[0].getAttribute('href')).toContain('#');
  });
});

/* ------------------------------------------------------------------ */
/* G. 320px + axe EN/AR                                                */
/* ------------------------------------------------------------------ */
describe('axe + narrow viewport', () => {
  it('320px: drawer opens and axe finds no serious/critical violations', async () => {
    Object.defineProperty(window, 'innerWidth', { value: 320, configurable: true });
    const { container } = renderNav('/b2b');
    openDrawer();
    const results = await axe(container, AXE_RULES);
    expect(results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
  });

  it('AR/RTL: sections + controls translated, drawer enters from inline-start, axe clean', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    const { container } = renderNav('/b2b/analytics');
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByRole('group', { name: 'النمو' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'فتح قائمة التنقل' }));
    const drawer = screen.getByTestId('brand-nav-drawer');
    // logical positioning: start-0 class, never a hardcoded left/right flip
    expect(drawer.className).toContain('start-0');
    expect(screen.getByRole('button', { name: 'إغلاق قائمة التنقل' })).toBeInTheDocument();
    const results = await axe(container, AXE_RULES);
    expect(results.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });
});
