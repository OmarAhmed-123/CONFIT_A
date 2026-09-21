import { useTranslation } from 'react-i18next';
import { msg } from '../../i18n/messages';
import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ConfitLogo } from '../common/ConfitLogo';
import { LanguageSwitcher } from './LanguageSwitcher';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';

const PARTNER_LINKS = [
  ['/b2b', 'Dashboard'], ['/b2b/catalog', 'Catalog & SKUs'],
  ['/b2b/inventory', 'BOPIS Inventory'], ['/b2b/analytics', 'Return Telemetry'],
  ['/b2b/placements', 'Placements'],
];

export const BrandNavbar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { showToast } = useUIStore();
  const isAdmin = user?.role?.toLowerCase() === 'admin';
  const { t } = useTranslation();
  const path = location.pathname.replace(/^\/partner(?=\/|$)/, '/b2b');
  const links = isAdmin ? [...PARTNER_LINKS, ['/admin', 'Platform Admin']] : PARTNER_LINKS;
  const handleLogout = async () => {
    try { await logout(); navigate('/'); }
    catch { showToast(msg('toast.sign_out_failed'), 'error'); }
  };

  return (
    <header className="sticky top-0 z-40 bg-[#0C0E1E] border-b border-slate-800 text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 min-h-20 py-3 flex flex-wrap gap-3 items-center justify-between">
        <Link to="/b2b" className="flex items-center gap-3 min-w-0" aria-label={t('b2b.dashboard_link_label')}>
          <ConfitLogo variant="compact" theme="light" size="sm" />
          <span className="hidden sm:block text-xs font-bold text-[#C5A059]">
            {isAdmin ? 'Platform Governance' : 'Brand Partner Hub'}
          </span>
        </Link>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Link to="/" className="px-2 py-2 rounded-lg border border-slate-700 text-slate-200">← Storefront</Link>
          <LanguageSwitcher />
          <span className="hidden lg:block max-w-40 truncate text-slate-200">{user?.full_name || 'Partner'}</span>
          <button onClick={handleLogout} className="px-2 py-2 rounded-lg text-slate-200 hover:bg-slate-800">Sign Out</button>
        </div>
      </div>
      <nav aria-label="Brand partner navigation" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex gap-1 overflow-x-auto pb-3">
        {links.map(([href, label]) => {
          const active = path === href || (href === '/admin' && path === '/b2b/admin-platform');
          return <Link key={href} to={href} aria-current={active ? 'page' : undefined}
            className={`shrink-0 px-3 py-2 rounded-lg text-xs font-semibold ${active ? 'bg-slate-800 text-[#E2BF70]' : 'text-slate-200 hover:bg-slate-800'}`}>
            {label}
          </Link>;
        })}
      </nav>
    </header>
  );
};
