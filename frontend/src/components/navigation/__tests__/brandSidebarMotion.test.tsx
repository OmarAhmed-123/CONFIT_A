/**
 * Spec 13 re-pass — the DYNAMIC layer on top of the functional contract:
 *   · the drawer is a PORTAL on document.body (§6.2) — overlay owns the page
 *   · full role matrix: every partner tenant role gets the SAME partner
 *     config; only `admin` gets governance (§9 "admin never sees partner
 *     controls" — and vice versa, for all three tenant roles)
 *   · exactly ONE animated active marker per surface, and it follows the
 *     route (the motion layer never duplicates or lies about state)
 *   · domain ribbon: each trust domain carries its register accent AND the
 *     portal title says it in words — color is never the only channel (§7)
 *   · reduced motion: open/Escape/scrim/focus-return all keep working with
 *     transforms disabled (§7 "function complete without motion")
 *   · deep links with query strings keep the active item (§6.5)
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { axe } from 'vitest-axe';

import { BrandNavbar, sectionsForRole } from '../BrandNavbar';
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

/** jsdom default matchMedia stub; `reduce` flips prefers-reduced-motion. */
const stubMatchMedia = (reduce: boolean) => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reduce && query.includes('prefers-reduced-motion'),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
};

beforeEach(async () => {
  cleanup();
  localStorage.clear();
  stubMatchMedia(false);
  setRole('brand_owner');
  await act(async () => { await setAppLanguage('en'); });
});

afterEach(() => {
  cleanup();
  document.body.style.overflow = '';
});

/* ------------------------------------------------------------------ */
/* A. Portal contract (§6.2)                                           */
/* ------------------------------------------------------------------ */
describe('drawer portal', () => {
  it('the open drawer is mounted directly under document.body, not inside the shell', () => {
    const { container } = renderNav('/b2b');
    openDrawer();
    const drawer = screen.getByTestId('brand-nav-drawer');
    // Not a descendant of the component tree the router rendered…
    expect(container.contains(drawer)).toBe(false);
    // …but of the body portal root.
    expect(document.body.contains(drawer)).toBe(true);
  });

  it('closing removes the portal content entirely — nothing left to block the page', () => {
    renderNav('/b2b');
    openDrawer();
    fireEvent.click(screen.getByRole('button', { name: 'Close navigation menu' }));
    expect(screen.queryByTestId('brand-nav-drawer')).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe('');
  });
});

/* ------------------------------------------------------------------ */
/* B. FULL role matrix (§9) — all three tenant roles + admin           */
/* ------------------------------------------------------------------ */
describe('role matrix across every portal role', () => {
  it.each(['brand_owner', 'brand_manager', 'brand_staff'])(
    '%s sees the partner config and ZERO admin links',
    (role) => {
      setRole(role);
      renderNav('/b2b');
      const nav = screen.getByTestId('brand-primary-nav');
      const hrefs = within(nav).getAllByRole('link').map((a) => a.getAttribute('href'));
      expect(hrefs.every((h) => h?.startsWith('/b2b'))).toBe(true);
      expect(hrefs.some((h) => h?.startsWith('/admin'))).toBe(false);
    },
  );

  it('admin sees governance only — no tenant hrefs on any surface (sidebar AND drawer)', () => {
    setRole('admin');
    renderNav('/admin');
    const sidebarHrefs = within(screen.getByTestId('brand-primary-nav'))
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'));
    expect(sidebarHrefs.every((h) => h?.startsWith('/admin'))).toBe(true);

    const drawer = openDrawer();
    const drawerNavHrefs = within(drawer)
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'))
      .filter((h) => h !== '/'); // the storefront escape hatch is legitimate
    expect(drawerNavHrefs.every((h) => h?.startsWith('/admin'))).toBe(true);
  });

  it('the two configs share no href — the trust domains cannot leak into each other', () => {
    const partner = sectionsForRole(false).flatMap((s) => s.items.map((i) => i.href));
    const admin = sectionsForRole(true).flatMap((s) => s.items.map((i) => i.href));
    expect(partner.filter((h) => admin.includes(h))).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* C. Animated active marker — motion that tells the truth             */
/* ------------------------------------------------------------------ */
describe('active route marker', () => {
  it('exactly one marker inside the sidebar, attached to the aria-current item', () => {
    renderNav('/b2b/catalog');
    const nav = screen.getByTestId('brand-primary-nav');
    const markers = within(nav).getAllByTestId('nav-active-marker');
    expect(markers).toHaveLength(1);
    const activeLink = within(nav).getByRole('link', { current: 'page' });
    expect(activeLink.contains(markers[0])).toBe(true);
    expect(activeLink).toHaveAttribute('href', '/b2b/catalog');
  });

  it('the marker follows a navigation — it never sticks to the old route', () => {
    renderNav('/b2b/catalog');
    const nav = screen.getByTestId('brand-primary-nav');
    fireEvent.click(within(nav).getByRole('link', { name: 'Orders' }));
    const markers = within(nav).getAllByTestId('nav-active-marker');
    expect(markers).toHaveLength(1);
    expect(within(nav).getByRole('link', { current: 'page' })).toHaveAttribute(
      'href',
      '/b2b/orders',
    );
  });

  it('marker is aria-hidden — state is carried by aria-current, not decoration (§7)', () => {
    renderNav('/b2b');
    const marker = within(screen.getByTestId('brand-primary-nav')).getByTestId(
      'nav-active-marker',
    );
    expect(marker).toHaveAttribute('aria-hidden', 'true');
  });
});

/* ------------------------------------------------------------------ */
/* D. Domain identity — accent + words, never color alone (§7)         */
/* ------------------------------------------------------------------ */
describe('trust-domain identity', () => {
  it('partner surfaces carry the partner register accent and SAY "Brand Partner Hub"', () => {
    renderNav('/b2b');
    const ribbons = screen.getAllByTestId('domain-ribbon');
    expect(ribbons.length).toBeGreaterThanOrEqual(2); // top bar + sidebar
    for (const ribbon of ribbons) {
      expect(ribbon.style.backgroundColor).toBe('rgb(62, 92, 118)'); // #3E5C76
      expect(ribbon).toHaveAttribute('aria-hidden', 'true');
    }
    expect(screen.getAllByText('Brand Partner Hub').length).toBeGreaterThan(0);
  });

  it('admin surfaces carry the admin register accent and SAY "Platform governance"', () => {
    setRole('admin');
    renderNav('/admin');
    for (const ribbon of screen.getAllByTestId('domain-ribbon')) {
      expect(ribbon.style.backgroundColor).toBe('rgb(90, 94, 106)'); // #5A5E6A
    }
    expect(screen.getAllByText('Platform Governance').length).toBeGreaterThan(0);
  });
});

/* ------------------------------------------------------------------ */
/* E. Reduced motion: the WHOLE function without any animation (§7)    */
/* ------------------------------------------------------------------ */
describe('prefers-reduced-motion', () => {
  beforeEach(() => stubMatchMedia(true));

  it('drawer opens instantly, focuses close, Escape closes, focus returns', () => {
    renderNav('/b2b');
    const hamburger = screen.getByRole('button', { name: 'Open navigation menu' });
    hamburger.focus(); // keyboard user: focus precedes activation
    fireEvent.click(hamburger);
    const drawer = screen.getByTestId('brand-nav-drawer');
    expect(screen.getByRole('button', { name: 'Close navigation menu' })).toHaveFocus();
    fireEvent.keyDown(drawer, { key: 'Escape' });
    expect(screen.queryByTestId('brand-nav-drawer')).not.toBeInTheDocument();
    expect(hamburger).toHaveFocus();
  });

  it('active marker still renders (static) — state survives without motion', () => {
    renderNav('/b2b/analytics');
    const nav = screen.getByTestId('brand-primary-nav');
    expect(within(nav).getAllByTestId('nav-active-marker')).toHaveLength(1);
    expect(within(nav).getByRole('link', { current: 'page' })).toHaveAttribute(
      'href',
      '/b2b/analytics',
    );
  });

  it('scrim click still closes', () => {
    const { container } = renderNav('/b2b');
    openDrawer();
    const scrim = document.body.querySelector('.bg-slate-950\\/70');
    expect(scrim).not.toBeNull();
    fireEvent.click(scrim!);
    expect(screen.queryByTestId('brand-nav-drawer')).not.toBeInTheDocument();
    expect(container).toBeTruthy();
  });
});

/* ------------------------------------------------------------------ */
/* F. Deep links with query strings (§6.5)                             */
/* ------------------------------------------------------------------ */
describe('deep links keep working', () => {
  it('/admin/catalog?tab=inventory still marks Catalog oversight active', () => {
    setRole('admin');
    renderNav('/admin/catalog?tab=inventory');
    const nav = screen.getByTestId('brand-primary-nav');
    expect(within(nav).getByRole('link', { current: 'page' })).toHaveAttribute(
      'href',
      '/admin/catalog',
    );
  });

  it('legacy /partner/orders alias resolves in the DRAWER too', () => {
    renderNav('/partner/orders');
    const drawer = openDrawer();
    expect(within(drawer).getByRole('link', { current: 'page' })).toHaveAttribute(
      'href',
      '/b2b/orders',
    );
  });
});

/* ------------------------------------------------------------------ */
/* G. axe over the NEW dynamic markup, EN + AR                         */
/* ------------------------------------------------------------------ */
describe('axe on the re-pass markup', () => {
  it('EN: sidebar + open portal drawer have no serious violations', async () => {
    renderNav('/b2b');
    openDrawer();
    const results = await axe(document.body, AXE_RULES);
    expect(
      results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'),
    ).toEqual([]);
  });

  it('AR/RTL: admin drawer (portal + ribbon + marker) is clean and translated', async () => {
    setRole('admin');
    await act(async () => { await setAppLanguage('ar'); });
    renderNav('/admin/audit');
    fireEvent.click(screen.getByRole('button', { name: 'فتح قائمة التنقل' }));
    const drawer = screen.getByTestId('brand-nav-drawer');
    expect(within(drawer).getByRole('link', { current: 'page' })).toBeInTheDocument();
    const results = await axe(document.body, AXE_RULES);
    expect(
      results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'),
    ).toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });
});
