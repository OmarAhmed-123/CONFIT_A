import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ConfitLogo } from '../common/ConfitLogo';
import { LanguageSwitcher } from './LanguageSwitcher';
import { useAuthStore } from '../../stores/authStore';
import { ShieldIcon, UserIcon } from '../icons/ConfitIcons';

export const BrandNavbar: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  const isActive = (path: string) => location.pathname === path;
  const isAdmin = user?.role?.toLowerCase() === 'admin';

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <header className="sticky top-0 z-40 bg-[#0C0E1E] border-b border-slate-800 text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
        {/* Brand Portal Logo */}
        <div className="flex items-center gap-8">
          <Link to="/b2b" className="flex items-center gap-3">
            <ConfitLogo variant="compact" theme="light" size="sm" />
            <div className="h-6 w-px bg-slate-800 hidden sm:block" />
            <div className="flex flex-col hidden sm:flex">
              <span className="text-xs font-bold uppercase tracking-wider text-[#C5A059]">
                {isAdmin ? 'CONFIT Admin Governance' : 'Brand Partner Hub'}
              </span>
              <span className="text-[10px] text-slate-400">
                {isAdmin ? 'Platform-Wide Telemetry & Auditing' : 'Merchant Operations & Telemetry'}
              </span>
            </div>
          </Link>

          {/* B2B Navigation Tabs */}
          <nav className="hidden md:flex items-center gap-1">
            <Link
              to="/b2b"
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                isActive('/b2b') ? 'bg-slate-800/80 text-[#C5A059] shadow-2xs' : 'text-slate-300 hover:text-white hover:bg-slate-800/40'
              }`}
            >
              Dashboard
            </Link>
            <Link
              to="/b2b/catalog"
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                isActive('/b2b/catalog') ? 'bg-slate-800/80 text-[#C5A059] shadow-2xs' : 'text-slate-300 hover:text-white hover:bg-slate-800/40'
              }`}
            >
              Catalog & SKUs
            </Link>
            <Link
              to="/b2b/inventory"
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                isActive('/b2b/inventory') ? 'bg-slate-800/80 text-[#C5A059] shadow-2xs' : 'text-slate-300 hover:text-white hover:bg-slate-800/40'
              }`}
            >
              BOPIS Inventory
            </Link>
            <Link
              to="/b2b/analytics"
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                isActive('/b2b/analytics') ? 'bg-slate-800/80 text-[#C5A059] shadow-2xs' : 'text-slate-300 hover:text-white hover:bg-slate-800/40'
              }`}
            >
              Return Telemetry
            </Link>
            <Link
              to="/b2b/placements"
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                isActive('/b2b/placements') ? 'bg-slate-800/80 text-[#C5A059] shadow-2xs' : 'text-slate-300 hover:text-white hover:bg-slate-800/40'
              }`}
            >
              Placements
            </Link>
            {isAdmin && (
              <Link
                to="/admin"
                className={`px-3.5 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                  isActive('/admin') || isActive('/b2b/admin-platform')
                    ? 'bg-[#C5A059]/20 text-[#C5A059] border border-[#C5A059]/40'
                    : 'text-amber-300 hover:text-white hover:bg-slate-800/40'
                }`}
              >
                Platform Admin
              </Link>
            )}
          </nav>
        </div>

        {/* Right Side Actions */}
        <div className="flex items-center gap-3 sm:gap-4">
          <Link
            to="/"
            className="px-3.5 py-1.5 rounded-xl border border-slate-700 hover:border-[#C5A059] text-slate-300 hover:text-white text-xs font-medium transition-all"
          >
            ← Storefront
          </Link>
          <LanguageSwitcher />

          {/* Authenticated Persona Badge & Sign Out */}
          <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
            <div className="w-8 h-8 rounded-full bg-slate-800 text-[#C5A059] flex items-center justify-center font-bold text-xs border border-slate-700">
              {isAdmin ? 'AD' : user?.full_name?.charAt(0) || 'MD'}
            </div>
            <div className="hidden lg:flex flex-col">
              <span className="text-xs font-medium text-slate-200 truncate max-w-[120px]">
                {user?.full_name || 'Massimo Dutti'}
              </span>
              <span className="text-[10px] text-[#C5A059] capitalize">
                {user?.role?.replace('_', ' ') || 'Partner'}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="ml-2 text-slate-400 hover:text-rose-400 text-xs px-2 py-1 rounded hover:bg-slate-800 transition-colors"
              title="Sign Out"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
