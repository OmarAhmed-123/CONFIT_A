import { useTranslation } from 'react-i18next';
import { msg } from '../../i18n/messages';
import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ConfitLogo } from '../common/ConfitLogo';
import { LanguageSwitcher } from './LanguageSwitcher';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';

type NavDestination = { href: string; labelKey: string };

const PARTNER_LINKS: NavDestination[] = [
  { href: '/b2b', labelKey: 'brand_nav.dashboard' },
  { href: '/b2b/catalog', labelKey: 'brand_nav.catalog' },
  { href: '/b2b/inventory', labelKey: 'brand_nav.inventory' },
  { href: '/b2b/analytics', labelKey: 'brand_nav.analytics' },
  { href: '/b2b/placements', labelKey: 'brand_nav.placements' },
];

const GOVERNANCE_LINKS: NavDestination[] = [
  { href: '/admin', labelKey: 'brand_nav.platform_admin' },
  { href: '/admin/audit', labelKey: 'brand_nav.audit_trail' },
];

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E2BF70] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0C0E1E]';

export const BrandNavbar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { showToast } = useUIStore();
  const isAdmin = user?.role?.toLowerCase() === 'admin';
  const { t } = useTranslation();
  const path = location.pathname.replace(/^\/partner(?=\/|$)/, '/b2b');

  // Governance is the admin's primary task, so those two links come FIRST.
  // At 390px they are in the initial viewport rather than hidden at the far
  // end of a long partner menu. All partner links remain available in the
  // same horizontally-scrollable nav — no mobile functionality is removed.
  const links = isAdmin ? [...GOVERNANCE_LINKS, ...PARTNER_LINKS] : PARTNER_LINKS;

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/');
    } catch {
      showToast(msg('toast.sign_out_failed'), 'error');
    }
  };

  return (
    <header className="sticky top-0 z-40 border-b border-slate-800 bg-[#0C0E1E] text-white">
      <div className="mx-auto flex min-h-20 max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <Link
          to="/b2b"
          className={`flex min-h-11 min-w-0 items-center gap-3 rounded-lg ${focusRing}`}
          aria-label={t('b2b.dashboard_link_label')}
        >
          <ConfitLogo variant="compact" theme="light" size="sm" />
          <span className="hidden text-xs font-bold text-[#C5A059] sm:block">
            {isAdmin ? t('brand_nav.governance') : t('brand_nav.partner_hub')}
          </span>
        </Link>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Link
            to="/"
            className={`inline-flex min-h-11 items-center rounded-lg border border-slate-700 px-3 py-2 text-slate-200 ${focusRing}`}
          >
            ← {t('brand_nav.storefront')}
          </Link>
          <LanguageSwitcher />
          <span className="hidden max-w-40 truncate text-slate-200 lg:block">
            {user?.full_name || 'Partner'}
          </span>
          <button
            type="button"
            onClick={handleLogout}
            className={`min-h-11 rounded-lg px-3 py-2 text-slate-200 hover:bg-slate-800 ${focusRing}`}
          >
            {t('brand_nav.sign_out')}
          </button>
        </div>
      </div>
      <p id="brand-nav-scroll-hint" className="sr-only">
        {t('brand_nav.scroll_hint')}
      </p>
      <nav
        aria-label={t('brand_nav.aria')}
        aria-describedby="brand-nav-scroll-hint"
        data-testid="brand-primary-nav"
        className="mx-auto flex max-w-7xl gap-1 overflow-x-auto overscroll-x-contain px-4 pb-3 sm:px-6 lg:px-8"
      >
        {links.map(({ href, labelKey }) => {
          const active = path === href || (href === '/admin' && path === '/b2b/admin-platform');
          return (
            <Link
              key={href}
              to={href}
              aria-current={active ? 'page' : undefined}
              className={`inline-flex min-h-11 shrink-0 items-center rounded-lg px-3 py-2 text-xs font-semibold ${focusRing} ${
                active ? 'bg-slate-800 text-[#E2BF70]' : 'text-slate-200 hover:bg-slate-800'
              }`}
            >
              {t(labelKey)}
            </Link>
          );
        })}
      </nav>
    </header>
  );
};
