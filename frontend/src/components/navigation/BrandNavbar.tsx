import { useTranslation } from 'react-i18next';
import { msg } from '../../i18n/messages';
import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  BarChart3, Boxes, ClipboardList, FolderCog, LayoutDashboard, LogOut,
  Megaphone, Menu, Package, PanelLeftClose, PanelLeftOpen, ScrollText,
  ShieldCheck, Store, X, type LucideIcon,
} from 'lucide-react';
import { ConfitLogo } from '../common/ConfitLogo';
import { LanguageSwitcher } from './LanguageSwitcher';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';

/**
 * Spec 13 — responsive B2B/Admin shell: a dense sidebar on desktop
 * (expanded/collapsed) that becomes a drawer on mobile.
 *
 * Contract decisions, each tied to a spec rule:
 *  · ONE typed, role-constrained nav config (§6.1): the two security
 *    domains stay separate — an admin NEVER receives partner-tenant hrefs
 *    and vice versa (§8 "no link the user cannot open"). This preserves
 *    the pre-existing boundary (admin hitting /partner/* endpoints used
 *    to produce an all-requests-failed screen).
 *  · The export name `BrandNavbar` is kept so BrandLayout and every
 *    route keep working — progressive replacement, nothing breaks (§2).
 *  · Drawer: focus is saved on open, enters the panel (close button),
 *    Tab wraps, Escape closes, scrim click closes, ROUTE CHANGE closes,
 *    and focus returns to the hamburger (§5/§6.2/§6.4).
 *  · Collapse state is announced as TEXT in aria-live=polite and
 *    persisted; collapsed links keep full accessible names (§7).
 *  · Logical positioning only (start/end/ms/me) — the drawer enters from
 *    the inline-start in BOTH directions; no manual RTL mirroring (§7).
 *  · Motion is a CSS width/opacity transition with
 *    `motion-reduce:transition-none` — full function without motion (§7).
 */

type NavItem = { href: string; labelKey: string; icon: LucideIcon };
type NavSection = { id: string; labelKey: string; items: NavItem[] };

const PARTNER_SECTIONS: NavSection[] = [
  {
    id: 'operations',
    labelKey: 'brand_nav.section_operations',
    items: [
      { href: '/b2b', labelKey: 'brand_nav.dashboard', icon: LayoutDashboard },
      { href: '/b2b/catalog', labelKey: 'brand_nav.catalog', icon: Package },
      { href: '/b2b/inventory', labelKey: 'brand_nav.inventory', icon: Boxes },
      { href: '/b2b/orders', labelKey: 'brand_nav.orders', icon: ClipboardList },
    ],
  },
  {
    id: 'growth',
    labelKey: 'brand_nav.section_growth',
    items: [
      { href: '/b2b/analytics', labelKey: 'brand_nav.analytics', icon: BarChart3 },
      { href: '/b2b/placements', labelKey: 'brand_nav.placements', icon: Megaphone },
    ],
  },
];

const ADMIN_SECTIONS: NavSection[] = [
  {
    id: 'governance',
    labelKey: 'brand_nav.section_governance',
    items: [
      { href: '/admin', labelKey: 'brand_nav.platform_admin', icon: ShieldCheck },
      { href: '/admin/catalog', labelKey: 'brand_nav.admin_catalog', icon: FolderCog },
    ],
  },
  {
    id: 'intelligence',
    labelKey: 'brand_nav.section_intelligence',
    items: [
      { href: '/admin/analytics', labelKey: 'brand_nav.platform_analytics', icon: BarChart3 },
    ],
  },
  {
    id: 'trust',
    labelKey: 'brand_nav.section_trust',
    items: [
      { href: '/admin/audit', labelKey: 'brand_nav.audit_trail', icon: ScrollText },
    ],
  },
];

/** Single role-gated source of truth (§6.1). */
export const sectionsForRole = (isAdmin: boolean): NavSection[] =>
  isAdmin ? ADMIN_SECTIONS : PARTNER_SECTIONS;

/** /partner/* is a legacy alias of /b2b/*; /b2b/admin-platform of /admin. */
const normalizePath = (pathname: string) =>
  pathname.replace(/^\/partner(?=\/|$)/, '/b2b');

const isItemActive = (href: string, path: string) =>
  path === href || (href === '/admin' && path === '/b2b/admin-platform');

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E2BF70] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0C0E1E]';

const COLLAPSE_KEY = 'confit.b2b.sidebar_collapsed';

/* ------------------------------------------------------------------ */
/* Breadcrumbs (§1): derived from the SAME role-gated config           */
/* ------------------------------------------------------------------ */
export const BrandBreadcrumbs: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const { user } = useAuthStore();
  const isAdmin = user?.role?.toLowerCase() === 'admin';
  const path = normalizePath(location.pathname);
  const home = isAdmin
    ? { href: '/admin', label: t('brand_nav.governance') }
    : { href: '/b2b', label: t('brand_nav.partner_hub') };

  let section: NavSection | undefined;
  let item: NavItem | undefined;
  for (const candidate of sectionsForRole(isAdmin)) {
    const hit = candidate.items.find((i) => isItemActive(i.href, path));
    if (hit) {
      section = candidate;
      item = hit;
      break;
    }
  }

  // Unknown deep routes (e.g. product drill-downs) keep the home crumb —
  // we never invent a label for a page the config does not know (§2).
  return (
    <nav aria-label={t('brand_nav.breadcrumbs_aria')} className="mb-4 text-xs text-slate-500">
      <ol className="flex flex-wrap items-center gap-1">
        <li>
          {item && item.href === home.href ? (
            <span aria-current="page" className="font-bold text-slate-800">{home.label}</span>
          ) : (
            <Link
              to={home.href}
              className="inline-flex min-h-11 items-center rounded px-1 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
            >
              {home.label}
            </Link>
          )}
        </li>
        {section && item && item.href !== home.href && (
          <>
            <li aria-hidden="true" className="text-slate-300">/</li>
            <li className="text-slate-500">{t(section.labelKey)}</li>
            <li aria-hidden="true" className="text-slate-300">/</li>
            <li>
              <span aria-current="page" className="font-bold text-slate-800">
                {t(item.labelKey)}
              </span>
            </li>
          </>
        )}
      </ol>
    </nav>
  );
};

/* ------------------------------------------------------------------ */
/* Shared pieces                                                       */
/* ------------------------------------------------------------------ */
const NavLinks: React.FC<{
  sections: NavSection[];
  path: string;
  collapsed?: boolean;
  onNavigate?: () => void;
}> = ({ sections, path, collapsed = false, onNavigate }) => {
  const { t } = useTranslation();
  return (
    <div className="space-y-5">
      {sections.map((section) => (
        <div key={section.id} role="group" aria-label={t(section.labelKey)}>
          <p
            className={`px-3 pb-1 text-[10px] font-bold uppercase tracking-widest text-slate-500 ${
              collapsed ? 'sr-only' : ''
            }`}
          >
            {t(section.labelKey)}
          </p>
          <ul className="space-y-1">
            {section.items.map(({ href, labelKey, icon: Icon }) => {
              const active = isItemActive(href, path);
              return (
                <li key={href}>
                  <Link
                    to={href}
                    onClick={onNavigate}
                    aria-current={active ? 'page' : undefined}
                    aria-label={collapsed ? t(labelKey) : undefined}
                    title={collapsed ? t(labelKey) : undefined}
                    className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-xs font-semibold ${focusRing} ${
                      active
                        ? 'bg-slate-800 text-[#E2BF70]'
                        : 'text-slate-200 hover:bg-slate-800'
                    } ${collapsed ? 'justify-center px-0' : ''}`}
                  >
                    <span aria-hidden="true"><Icon size={16} /></span>
                    {!collapsed && <span className="truncate">{t(labelKey)}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Mobile drawer — same focus contract as the consumer MobileNavDrawer */
/* ------------------------------------------------------------------ */
const BrandNavDrawer: React.FC<{
  open: boolean;
  onClose: () => void;
  sections: NavSection[];
  path: string;
  portalTitle: string;
  onSignOut: () => void;
}> = ({ open, onClose, sections, path, portalTitle, onSignOut }) => {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = (document.activeElement as HTMLElement) ?? null;
      panelRef.current?.querySelector<HTMLElement>('[data-drawer-close]')?.focus();
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = '';
        restoreFocusRef.current?.focus();
      };
    }
  }, [open]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab' || !panelRef.current) return;
    const focusables = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  if (!open) return null;

  return (
    <div className="lg:hidden fixed inset-0 z-50" onKeyDown={onKeyDown}>
      {/* Plain scrim — no backdrop-filter; click outside closes (§5). */}
      <div className="absolute inset-0 bg-slate-950/70" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('brand_nav.drawer_label')}
        data-testid="brand-nav-drawer"
        className="absolute inset-y-0 start-0 flex w-[85vw] max-w-sm flex-col bg-[#0C0E1E] text-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <ConfitLogo variant="compact" theme="light" size="sm" />
            <span className="truncate text-xs font-bold text-[#C5A059]">{portalTitle}</span>
          </div>
          <button
            type="button"
            data-drawer-close
            onClick={onClose}
            aria-label={t('brand_nav.close_menu')}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl text-slate-300 hover:bg-slate-800 ${focusRing}`}
          >
            <X size={22} aria-hidden="true" />
          </button>
        </div>
        <nav
          aria-label={t('brand_nav.aria')}
          className="flex-1 overflow-y-auto px-3 py-4"
        >
          <NavLinks sections={sections} path={path} onNavigate={onClose} />
        </nav>
        <div className="space-y-1 border-t border-slate-800 px-3 py-3">
          <Link
            to="/"
            onClick={onClose}
            className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-xs text-slate-200 hover:bg-slate-800 ${focusRing}`}
          >
            <span aria-hidden="true"><Store size={16} /></span>
            {t('brand_nav.storefront')}
          </Link>
          <button
            type="button"
            onClick={onSignOut}
            className={`flex w-full min-h-11 items-center gap-3 rounded-xl px-3 text-start text-xs text-slate-200 hover:bg-slate-800 ${focusRing}`}
          >
            <span aria-hidden="true"><LogOut size={16} /></span>
            {t('brand_nav.sign_out')}
          </button>
        </div>
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Shell                                                               */
/* ------------------------------------------------------------------ */
export const BrandNavbar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { showToast } = useUIStore();
  const isAdmin = user?.role?.toLowerCase() === 'admin';
  const { t } = useTranslation();
  const path = normalizePath(location.pathname);
  const sections = sectionsForRole(isAdmin);
  const portalTitle = isAdmin ? t('brand_nav.governance') : t('brand_nav.partner_hub');

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  // §6.4: the drawer never survives a navigation — the user asked to GO
  // somewhere; covering the destination would block content and focus (§8).
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  const toggleCollapsed = () => {
    setCollapsed((current) => {
      const next = !current;
      try {
        localStorage.setItem(COLLAPSE_KEY, String(next));
      } catch {
        /* private mode: state stays for the session only */
      }
      return next;
    });
  };

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/');
    } catch {
      showToast(msg('toast.sign_out_failed'), 'error');
    }
  };

  return (
    <>
      {/* ── Mobile top bar (lg:hidden): the way into the drawer ── */}
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-[#0C0E1E] text-white lg:hidden">
        <div className="flex min-h-16 items-center justify-between gap-2 px-4">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-expanded={drawerOpen}
            aria-haspopup="dialog"
            aria-label={t('brand_nav.open_menu')}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl text-slate-200 hover:bg-slate-800 ${focusRing}`}
          >
            <Menu size={22} aria-hidden="true" />
          </button>
          <Link
            to={isAdmin ? '/admin' : '/b2b'}
            className={`flex min-h-11 min-w-0 items-center gap-2 rounded-lg ${focusRing}`}
            aria-label={t('b2b.dashboard_link_label')}
          >
            <ConfitLogo variant="compact" theme="light" size="sm" />
            <span className="truncate text-xs font-bold text-[#C5A059]">{portalTitle}</span>
          </Link>
          <LanguageSwitcher />
        </div>
      </header>

      <BrandNavDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sections={sections}
        path={path}
        portalTitle={portalTitle}
        onSignOut={handleLogout}
      />

      {/* ── Desktop sidebar (hidden below lg) ── */}
      <aside
        data-testid="brand-sidebar"
        className={`sticky top-0 z-30 hidden h-screen shrink-0 flex-col border-e border-slate-800 bg-[#0C0E1E] text-white transition-[width] duration-200 motion-reduce:transition-none lg:flex ${
          collapsed ? 'w-[4.5rem]' : 'w-64'
        }`}
      >
        <div className={`flex items-center gap-3 border-b border-slate-800 px-4 py-5 ${collapsed ? 'justify-center px-0' : ''}`}>
          <Link
            to={isAdmin ? '/admin' : '/b2b'}
            className={`flex min-h-11 min-w-0 items-center gap-3 rounded-lg ${focusRing}`}
            aria-label={t('b2b.dashboard_link_label')}
          >
            <ConfitLogo variant="compact" theme="light" size="sm" />
            {!collapsed && (
              <span className="truncate text-xs font-bold text-[#C5A059]">{portalTitle}</span>
            )}
          </Link>
        </div>

        <nav
          aria-label={t('brand_nav.aria')}
          data-testid="brand-primary-nav"
          className="flex-1 overflow-y-auto px-3 py-4"
        >
          <NavLinks sections={sections} path={path} collapsed={collapsed} />
        </nav>

        {/* Collapse state is TEXT for assistive tech, not just width (§7). */}
        <span className="sr-only" role="status" aria-live="polite">
          {collapsed ? t('brand_nav.state_collapsed') : t('brand_nav.state_expanded')}
        </span>

        <div className="space-y-1 border-t border-slate-800 px-3 py-3">
          {!collapsed && (
            <p className="truncate px-3 pb-1 text-[10px] text-slate-500">
              {user?.full_name || 'Partner'}
            </p>
          )}
          <Link
            to="/"
            aria-label={collapsed ? t('brand_nav.storefront') : undefined}
            title={collapsed ? t('brand_nav.storefront') : undefined}
            className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-xs text-slate-200 hover:bg-slate-800 ${focusRing} ${collapsed ? 'justify-center px-0' : ''}`}
          >
            <span aria-hidden="true"><Store size={16} /></span>
            {!collapsed && t('brand_nav.storefront')}
          </Link>
          {!collapsed && (
            <div className="px-3 py-1">
              <LanguageSwitcher />
            </div>
          )}
          <button
            type="button"
            onClick={handleLogout}
            aria-label={collapsed ? t('brand_nav.sign_out') : undefined}
            title={collapsed ? t('brand_nav.sign_out') : undefined}
            className={`flex w-full min-h-11 items-center gap-3 rounded-xl px-3 text-start text-xs text-slate-200 hover:bg-slate-800 ${focusRing} ${collapsed ? 'justify-center px-0' : ''}`}
          >
            <span aria-hidden="true"><LogOut size={16} /></span>
            {!collapsed && t('brand_nav.sign_out')}
          </button>
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-pressed={collapsed}
            aria-label={collapsed ? t('brand_nav.expand_sidebar') : t('brand_nav.collapse_sidebar')}
            className={`flex w-full min-h-11 items-center gap-3 rounded-xl px-3 text-start text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200 ${focusRing} ${collapsed ? 'justify-center px-0' : ''}`}
          >
            <span aria-hidden="true" className="rtl:rotate-180">
              {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
            </span>
            {!collapsed && t('brand_nav.collapse_sidebar')}
          </button>
        </div>
      </aside>
    </>
  );
};
