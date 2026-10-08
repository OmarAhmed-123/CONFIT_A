/**
 * Spec 05 — Magic Navigation / App Shell. §10 required coverage:
 *   routes/RoleGuard role matrix · keyboard menu · mobile drawer a11y ·
 *   deep link · active state · route announcement · axe (EN/LTR + AR/RTL) ·
 *   reduced motion.
 *
 * Structure:
 *   A. RoleGuard role matrix (guest / consumer / partner / admin × portals)
 *   B. PartnerPortalBoundary — admin never lands in tenant surfaces
 *   C. BrandNavbar — admin sees governance links ONLY, partner tenant ONLY
 *   D. ConsumerNavbar desktop — keyboard-operable disclosures, aria-current
 *   E. Mobile drawer — dialog semantics, focus trap, Escape, named controls
 *   F. Route announcement · deep links · logout honesty
 *   G. axe + RTL + reduced motion
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';

import i18n, { setAppLanguage } from '../../../i18n/i18n';

// ---------------------------------------------------------------------------
// Store mocks — mutable state objects the tests rewrite per scenario.
// ---------------------------------------------------------------------------
const showToast = vi.fn();
const openAuthModal = vi.fn();
const openStylist = vi.fn();
const openVisualSearch = vi.fn();
const openCart = vi.fn();
const logout = vi.fn().mockResolvedValue(undefined);

type AnyUser = { role: string; email: string; full_name: string; has_profile?: boolean } | null;
const authState: { user: AnyUser; isAuthenticated: boolean; hasAttemptedBootstrap: boolean; logout: typeof logout } = {
  user: null,
  isAuthenticated: false,
  hasAttemptedBootstrap: true,
  logout,
};

vi.mock('../../../stores/authStore', () => ({
  useAuthStore: (selector?: (s: unknown) => unknown) =>
    selector ? selector(authState) : authState,
}));
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (selector?: (s: unknown) => unknown) => {
    const state = { showToast, openAuthModal, openStylist, openVisualSearch };
    return selector ? selector(state) : state;
  },
}));
vi.mock('../../../stores/cartStore', () => ({
  useCartStore: (selector?: (s: unknown) => unknown) => {
    const state = { cart: { items_count: 2 }, openCart, addItem: vi.fn(), openCart2: null };
    return selector ? selector(state) : state;
  },
}));
// Switchers have their own suites; stub them to keep this one about the shell.
vi.mock('../LanguageSwitcher', () => ({
  LanguageSwitcher: () => <button type="button" aria-label="Language">EN</button>,
}));
vi.mock('../CurrencySwitcher', () => ({
  CurrencySwitcher: () => <button type="button" aria-label="Currency">USD</button>,
}));

import { ConsumerNavbar } from '../ConsumerNavbar';
import { BrandNavbar } from '../BrandNavbar';
import { RoleGuard } from '../../auth/RoleGuard';
import { PartnerPortalBoundary } from '../../../router/AppRoutes';
import { RouteAnnouncer } from '../../../hooks/useRouteAnnouncement';
import { CONSUMER_NAV, isSectionActive } from '../navMetadata';

const PARTNER_ROLES = ['brand_owner', 'brand_manager', 'brand_staff'];

const setUser = (user: AnyUser, isAuthenticated = !!user) => {
  authState.user = user;
  authState.isAuthenticated = isAuthenticated;
  authState.hasAttemptedBootstrap = true;
};

const renderAt = (ui: React.ReactNode, route = '/') =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </I18nextProvider>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  logout.mockResolvedValue(undefined);
  setUser(null);
});
afterEach(cleanup);

// ===========================================================================
// A. RoleGuard — role matrix
// ===========================================================================
describe('RoleGuard role matrix', () => {
  it('guest on the admin portal: auth gate, no protected content, no fake 403', () => {
    renderAt(
      <RoleGuard allowedRoles={['admin']} portal="admin">
        <div data-testid="admin-secret" />
      </RoleGuard>,
    );
    expect(screen.queryByTestId('admin-secret')).toBeNull();
    expect(screen.getByRole('button', { name: new RegExp(i18n.t('partner.sign_in_to_continue')) })).toBeInTheDocument();
  });

  it('consumer on the admin portal: explicit 403 with the role requirement as TEXT', () => {
    setUser({ role: 'consumer', email: 'c@x.dev', full_name: 'C X' });
    renderAt(
      <RoleGuard allowedRoles={['admin']} portal="admin">
        <div data-testid="admin-secret" />
      </RoleGuard>,
    );
    expect(screen.queryByTestId('admin-secret')).toBeNull();
    expect(screen.getByText(i18n.t('guard.access_restricted'))).toBeInTheDocument();
    // The refusal names the required roles — state is text, not colour.
    expect(screen.getByText('admin')).toBeInTheDocument();
    // And offers a way out, back to the storefront.
    expect(screen.getByRole('link', { name: i18n.t('guard.return_storefront') })).toHaveAttribute('href', '/');
  });

  it('partner role passes the partner guard; admin passes the admin guard', () => {
    setUser({ role: 'brand_owner', email: 'b@x.dev', full_name: 'B O' });
    renderAt(
      <RoleGuard allowedRoles={PARTNER_ROLES} portal="partner">
        <div data-testid="tenant-content" />
      </RoleGuard>,
    );
    expect(screen.getByTestId('tenant-content')).toBeInTheDocument();
    cleanup();

    setUser({ role: 'admin', email: 'a@x.dev', full_name: 'A D' });
    renderAt(
      <RoleGuard allowedRoles={['admin']} portal="admin">
        <div data-testid="governance-content" />
      </RoleGuard>,
    );
    expect(screen.getByTestId('governance-content')).toBeInTheDocument();
  });

  it('consumer on the PARTNER portal sees onboarding (declared portal prop, not title sniffing)', () => {
    setUser({ role: 'consumer', email: 'c@x.dev', full_name: 'C X' });
    renderAt(
      <RoleGuard allowedRoles={PARTNER_ROLES} portal="partner">
        <div data-testid="tenant-content" />
      </RoleGuard>,
    );
    expect(screen.queryByTestId('tenant-content')).toBeNull();
    // The partner value proposition + request form, not the generic wall.
    expect(screen.getByText(i18n.t('partner.hero_title'))).toBeInTheDocument();
    // The redesigned gateway (B01) deliberately places the primary CTA twice —
    // once in the masthead so it is above the fold, once in the closing tier.
    // Two same-named controls is the design, so assert presence, not uniqueness.
    expect(
      screen.getAllByRole('button', { name: i18n.t('partner.request_partnership') }).length,
    ).toBeGreaterThanOrEqual(2);
    // And the form itself, which is the actual conversion instrument.
    expect(screen.getByTestId('lead-form')).toBeInTheDocument();
  });

  it('bootstrap in flight: a polite verifying state — never a premature auth wall', () => {
    authState.hasAttemptedBootstrap = false;
    renderAt(
      <RoleGuard allowedRoles={['admin']} portal="admin">
        <div data-testid="admin-secret" />
      </RoleGuard>,
    );
    expect(screen.queryByTestId('admin-secret')).toBeNull();
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent(i18n.t('guard.verifying_session'));
  });
});

// ===========================================================================
// B. PartnerPortalBoundary — admin is never a tenant
// ===========================================================================
describe('PartnerPortalBoundary', () => {
  const App = () => (
    <Routes>
      <Route
        path="/b2b/*"
        element={
          <PartnerPortalBoundary>
            <div data-testid="tenant-portal" />
          </PartnerPortalBoundary>
        }
      />
      <Route path="/admin" element={<div data-testid="admin-home" />} />
      <Route path="/admin/analytics" element={<div data-testid="admin-analytics" />} />
      <Route path="/admin/catalog" element={<div data-testid="admin-catalog" />} />
    </Routes>
  );

  it('redirects an admin from /b2b to the governance portal (no tenant requests fired)', () => {
    setUser({ role: 'admin', email: 'a@x.dev', full_name: 'A D' });
    renderAt(<App />, '/b2b');
    expect(screen.queryByTestId('tenant-portal')).toBeNull();
    expect(screen.getByTestId('admin-home')).toBeInTheDocument();
  });

  it('maps deep tenant URLs to their admin equivalents (/b2b/analytics → /admin/analytics)', () => {
    setUser({ role: 'admin', email: 'a@x.dev', full_name: 'A D' });
    renderAt(<App />, '/b2b/analytics');
    expect(screen.getByTestId('admin-analytics')).toBeInTheDocument();
  });

  it('keeps partner roles inside the tenant portal', () => {
    setUser({ role: 'brand_manager', email: 'b@x.dev', full_name: 'B M' });
    renderAt(<App />, '/b2b');
    expect(screen.getByTestId('tenant-portal')).toBeInTheDocument();
  });
});

// ===========================================================================
// C. BrandNavbar — strict link separation per trust domain
// ===========================================================================
describe('BrandNavbar role separation', () => {
  it('admin sees governance links only — zero tenant links', () => {
    setUser({ role: 'admin', email: 'a@x.dev', full_name: 'A D' });
    renderAt(<BrandNavbar />, '/admin');
    const nav = screen.getByTestId('brand-primary-nav');
    const hrefs = Array.from(nav.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs.every((h) => h?.startsWith('/admin'))).toBe(true);
    expect(hrefs.some((h) => h?.startsWith('/b2b'))).toBe(false);
  });

  it('partner sees tenant links only — zero /admin links', () => {
    setUser({ role: 'brand_owner', email: 'b@x.dev', full_name: 'B O' });
    renderAt(<BrandNavbar />, '/b2b');
    const nav = screen.getByTestId('brand-primary-nav');
    const hrefs = Array.from(nav.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs.every((h) => h?.startsWith('/b2b'))).toBe(true);
    expect(hrefs.some((h) => h?.startsWith('/admin'))).toBe(false);
  });

  it('marks the current section with aria-current="page"', () => {
    setUser({ role: 'brand_owner', email: 'b@x.dev', full_name: 'B O' });
    renderAt(<BrandNavbar />, '/b2b/catalog');
    const nav = screen.getByTestId('brand-primary-nav');
    const current = Array.from(nav.querySelectorAll('[aria-current="page"]'));
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute('href', '/b2b/catalog');
  });
});

// ===========================================================================
// D. ConsumerNavbar desktop — keyboard-operable disclosure menus
// ===========================================================================
describe('ConsumerNavbar keyboard menus', () => {
  it('disclosure triggers are real buttons with aria-expanded/controls — click opens, click closes', () => {
    renderAt(<ConsumerNavbar />);
    const trigger = screen.getByRole('button', { name: i18n.t('nav.style_discover') });
    expect(trigger).toHaveAttribute('aria-haspopup', 'true');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    const panel = document.getElementById(trigger.getAttribute('aria-controls')!)!;
    expect(panel).toBeTruthy();
    // Panel items are REAL links/buttons with accessible names.
    expect(screen.getByRole('link', { name: new RegExp(i18n.t('nav.outfit_builder')) })).toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('Escape closes the open menu and returns focus to its trigger', () => {
    renderAt(<ConsumerNavbar />);
    const trigger = screen.getByRole('button', { name: i18n.t('nav.tryon_fit') });
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');

    const link = screen.getByRole('link', { name: new RegExp(i18n.t('nav.virtual_tryon')) });
    link.focus();
    fireEvent.keyDown(link, { key: 'Escape' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(trigger);
  });

  it('store-backed intents (stylist / visual search) fire from menu items', () => {
    renderAt(<ConsumerNavbar />);
    fireEvent.click(screen.getByRole('button', { name: i18n.t('nav.style_discover') }));
    fireEvent.click(screen.getByRole('button', { name: new RegExp(i18n.t('nav.stylist')) }));
    expect(openStylist).toHaveBeenCalledTimes(1);
  });

  it('active section carries aria-current and matches the metadata table', () => {
    renderAt(<ConsumerNavbar />, '/wardrobe');
    const trigger = screen.getByRole('button', { name: i18n.t('nav.my_wardrobe') });
    expect(trigger).toHaveAttribute('aria-current', 'page');
    // The metadata helper agrees — one source of truth.
    const section = CONSUMER_NAV.find((s) => s.id === 'wardrobe')!;
    expect(isSectionActive(section, '/wardrobe')).toBe(true);
    expect(isSectionActive(section, '/discover')).toBe(false);
    // Home must not light up away from '/': the '/' prefix matches exactly.
    expect(isSectionActive(CONSUMER_NAV[0], '/wardrobe')).toBe(false);
  });

  it('deep link with a section query (/wardrobe?tab=looks) still activates the wardrobe section', () => {
    renderAt(<ConsumerNavbar />, '/wardrobe?tab=looks');
    expect(screen.getByRole('button', { name: i18n.t('nav.my_wardrobe') })).toHaveAttribute('aria-current', 'page');
  });
});

// ===========================================================================
// E. Mobile drawer — dialog semantics + focus trap
// ===========================================================================
describe('ConsumerNavbar mobile drawer', () => {
  const openDrawer = () => {
    const burger = screen.getByRole('button', { name: i18n.t('a11y.open_menu') });
    burger.focus(); // jsdom does not focus on click the way real browsers do
    fireEvent.click(burger);
    return burger;
  };

  it('opens as a modal dialog with an accessible name and focuses the close control', () => {
    renderAt(<ConsumerNavbar />);
    openDrawer();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-label', i18n.t('a11y.mobile_nav_label'));
    const close = screen.getByRole('button', { name: i18n.t('a11y.close_menu') });
    expect(document.activeElement).toBe(close);
    // Every top-level destination from the shared metadata is present.
    expect(screen.getAllByRole('link', { name: new RegExp(i18n.t('nav.my_closet')) }).length).toBeGreaterThan(0);
  });

  it('traps Tab inside the drawer — focus cannot land behind it', () => {
    renderAt(<ConsumerNavbar />);
    openDrawer();
    const dialog = screen.getByRole('dialog');
    const focusables = Array.from(
      dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
    );
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    last.focus();
    fireEvent.keyDown(dialog.parentElement!, { key: 'Tab' });
    expect(document.activeElement).toBe(first);

    first.focus();
    fireEvent.keyDown(dialog.parentElement!, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it('Escape closes the drawer and restores focus to the hamburger', () => {
    renderAt(<ConsumerNavbar />);
    const burger = openDrawer();
    fireEvent.keyDown(screen.getByRole('dialog').parentElement!, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(burger);
  });

  it('clicking the scrim closes; body scroll lock is released', () => {
    renderAt(<ConsumerNavbar />);
    openDrawer();
    expect(document.body.style.overflow).toBe('hidden');
    const scrim = screen.getByRole('dialog').previousElementSibling!;
    fireEvent.click(scrim);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.body.style.overflow).toBe('');
  });
});

// ===========================================================================
// F. Route announcement · logout honesty
// ===========================================================================
describe('route announcement & logout honesty', () => {
  it('announces a client-side navigation in the polite live region', async () => {
    const { container } = renderAt(
      <>
        <RouteAnnouncer />
        <Routes>
          <Route path="/" element={<a href="/wardrobe">go</a>} />
          <Route path="/wardrobe" element={<div />} />
        </Routes>
        <NavigateButton />
      </>,
    );
    const region = container.querySelector('[data-testid="route-announcer"]')!;
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region.textContent).toBe(''); // initial mount: silence by design

    fireEvent.click(screen.getByRole('button', { name: 'nav-now' }));
    await waitFor(() => expect(region.textContent).not.toBe(''));
    expect(region.textContent).toContain(i18n.t('meta.wardrobe_title'));
  });

  it('failed sign-out is reported, not swallowed into a fake success', async () => {
    setUser({ role: 'consumer', email: 'c@x.dev', full_name: 'Cee Ex' });
    logout.mockRejectedValueOnce(new Error('session revoke failed'));
    renderAt(<ConsumerNavbar />);
    fireEvent.click(screen.getByRole('button', { name: i18n.t('a11y.account_menu') }));
    fireEvent.click(screen.getByRole('button', { name: i18n.t('account.sign_out') }));
    await waitFor(() => expect(showToast).toHaveBeenCalled());
    const [message, type] = showToast.mock.calls[0];
    expect((message as { key: string }).key).toBe('toast.sign_out_failed');
    expect(type).toBe('error');
  });
});

const NavigateButton: React.FC = () => {
  const { useNavigate } = require('react-router-dom') as typeof import('react-router-dom');
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate('/wardrobe')}>
      nav-now
    </button>
  );
};

// ===========================================================================
// G. axe + RTL + reduced motion
// ===========================================================================
const JSDOM_UNCOMPUTABLE = ['color-contrast', 'target-size'];
async function expectNoSeriousViolations(node: HTMLElement, label: string) {
  const results = await axe(node, {
    rules: Object.fromEntries(JSDOM_UNCOMPUTABLE.map((r) => [r, { enabled: false }])),
  });
  const bad = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
  if (bad.length) {
    throw new Error(`${label}: ${bad.map((v) => `${v.id} — ${v.help}`).join('; ')}`);
  }
}

describe('axe / RTL / reduced motion', () => {
  it('consumer shell with an open menu: no critical/serious violations (EN/LTR)', async () => {
    const { container } = renderAt(<ConsumerNavbar />);
    fireEvent.click(screen.getByRole('button', { name: i18n.t('nav.style_discover') }));
    await expectNoSeriousViolations(container, 'ConsumerNavbar EN');
  });

  it('mobile drawer open: no critical/serious violations', async () => {
    const { container } = renderAt(<ConsumerNavbar />);
    fireEvent.click(screen.getByRole('button', { name: i18n.t('a11y.open_menu') }));
    await expectNoSeriousViolations(container, 'Mobile drawer EN');
  });

  it('Arabic/RTL shell: drawer + menus fully functional, axe clean', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    try {
      const { container } = renderAt(<ConsumerNavbar />);
      // Keyboard disclosure still works under RTL.
      const trigger = screen.getByRole('button', { name: i18n.t('nav.style_discover') });
      fireEvent.click(trigger);
      expect(trigger).toHaveAttribute('aria-expanded', 'true');
      fireEvent.keyDown(trigger, { key: 'Escape' });
      expect(trigger).toHaveAttribute('aria-expanded', 'false');
      // Drawer too.
      fireEvent.click(screen.getByRole('button', { name: i18n.t('a11y.open_menu') }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      await expectNoSeriousViolations(container, 'ConsumerNavbar AR/RTL');
    } finally {
      await act(async () => {
        await setAppLanguage('en');
      });
    }
  });

  it('reduced motion: drawer and menus remain fully functional (no animation dependency)', () => {
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
      renderAt(<ConsumerNavbar />);
      fireEvent.click(screen.getByRole('button', { name: i18n.t('a11y.open_menu') }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      fireEvent.keyDown(screen.getByRole('dialog').parentElement!, { key: 'Escape' });
      expect(screen.queryByRole('dialog')).toBeNull();
    } finally {
      window.matchMedia = original;
    }
  });
});
