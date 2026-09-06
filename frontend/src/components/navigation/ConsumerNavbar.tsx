import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  HomeIcon,
  SparkleIcon,
  StylistIcon,
  OutfitBuilderIcon,
  VisualSearchIcon,
  FlameIcon,
  TryOnIcon,
  RulerIcon,
  WardrobeIcon,
  SavedLooksIcon,
  GapAnalysisIcon,
  BagIcon,
  OrdersIcon,
  UserIcon,
  BrandDashboardIcon,
  ShieldIcon,
} from '../icons/ConfitIcons';
import { ConfitLogo } from '../common/ConfitLogo';
import { useCartStore } from '../../stores/cartStore';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { LanguageSwitcher } from './LanguageSwitcher';

export const ConsumerNavbar: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();

  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);

  const { cart, openCart } = useCartStore();
  const { user, isAuthenticated, logout } = useAuthStore();
  const { openStylist, openVisualSearch, openAuthModal } = useUIStore();

  const itemsCount = cart?.items_count || 0;
  const isActive = (path: string) => location.pathname === path;
  const isPrivileged = user?.role && ['brand_owner', 'brand_manager', 'brand_staff', 'admin'].includes(user.role.toLowerCase());
  const isAdmin = user?.role?.toLowerCase() === 'admin';

  return (
    <>
      {/* Top Thin Luxury Bar */}
      <div className="bg-[#0C0E1E] text-slate-400 text-xs py-1.5 px-4 sm:px-8 flex justify-between items-center border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#C5A059] animate-pulse"></span>
          <span className="hidden sm:inline text-slate-300 font-light tracking-wide">
            CONFIT Precision Fashion Technology — Drape & Sizing Intelligence
          </span>
          <span className="sm:hidden text-slate-300">CONFIT AI Studio</span>
        </div>
        <div className="flex items-center gap-4">
          {isPrivileged ? (
            <Link
              to={isAdmin ? '/admin' : '/b2b'}
              className="inline-flex items-center gap-1.5 text-[#C5A059] hover:text-[#E2BF70] font-semibold transition-colors text-xs"
            >
              {isAdmin ? <ShieldIcon size={14} color="#C5A059" /> : <BrandDashboardIcon size={14} color="#C5A059" />}
              <span>{isAdmin ? t('nav.admin_governance') : t('nav.brand_partner_hub')}</span>
            </Link>
          ) : (
            <Link
              to="/b2b"
              className="inline-flex items-center gap-1.5 text-slate-400 hover:text-[#C5A059] font-medium transition-colors text-xs"
            >
              <BrandDashboardIcon size={14} color="#C5A059" />
              <span>{t('nav.partner_portal')}</span>
            </Link>
          )}
          <div className="h-3 w-px bg-slate-800" />
          <LanguageSwitcher />
        </div>
      </div>

      {/* Main Consumer Navigation Bar */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200/80 shadow-2xs transition-all">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          {/* Far Left: CONFIT Master Logo */}
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center group">
              <ConfitLogo variant="full" theme="dark" size="md" />
            </Link>

            {/* Desktop Primary Nav */}
            <nav className="hidden lg:flex items-center gap-1 xl:gap-2">
              {/* 1. Home Anchor */}
              <Link
                to="/"
                className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                  isActive('/')
                    ? 'text-[#1B1F3B] bg-slate-100 font-bold'
                    : 'text-slate-600 hover:text-[#1B1F3B] hover:bg-slate-50'
                }`}
              >
                <HomeIcon size={18} isActive={isActive('/')} />
                <span>{t('nav.home')}</span>
              </Link>

              {/* 2. Style & Discover (Mega Menu) */}
              <div
                className="relative"
                onMouseEnter={() => setActiveDropdown('discover')}
                onMouseLeave={() => setActiveDropdown(null)}
              >
                <button
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                    activeDropdown === 'discover' || isActive('/discover') || isActive('/builder')
                      ? 'text-[#7A5C28] bg-[#FDF8EE] font-bold'
                      : 'text-slate-600 hover:text-[#1B1F3B] hover:bg-slate-50'
                  }`}
                >
                  <SparkleIcon size={18} isActive={activeDropdown === 'discover'} color="#C5A059" />
                  <span>{t('nav.style_discover')}</span>
                  <span className="text-[9px] text-slate-400">▼</span>
                </button>

                {activeDropdown === 'discover' && (
                  <div className="absolute top-full left-0 w-80 bg-white border border-slate-100 rounded-2xl shadow-xl p-3 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                    <button
                      onClick={() => {
                        setActiveDropdown(null);
                        openStylist();
                      }}
                      className="w-full text-left flex items-start gap-3 p-2.5 rounded-xl hover:bg-[#FDF8EE] transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-[#FDF8EE] group-hover:bg-[#C5A059] transition-colors">
                        <StylistIcon size={20} color="#C5A059" />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.stylist')}
                        </div>
                        <div className="text-[11px] text-slate-500">Conversational AI recommendations</div>
                      </div>
                    </button>

                    <Link
                      to="/builder"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-50 transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100 group-hover:bg-slate-200 transition-colors">
                        <OutfitBuilderIcon size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.outfit_builder')}
                        </div>
                        <div className="text-[11px] text-slate-500">Multi-brand canvas & live budget tracker</div>
                      </div>
                    </Link>

                    <button
                      onClick={() => {
                        setActiveDropdown(null);
                        openVisualSearch();
                      }}
                      className="w-full text-left flex items-start gap-3 p-2.5 rounded-xl hover:bg-[#FDF8EE] transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-[#FDF8EE] group-hover:bg-[#C5A059] transition-colors">
                        <VisualSearchIcon size={20} color="#C5A059" />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.visual_search')}
                        </div>
                        <div className="text-[11px] text-slate-500">Find catalog matches from any photo</div>
                      </div>
                    </button>

                    <Link
                      to="/discover"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-50 transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100 group-hover:bg-slate-200 transition-colors">
                        <FlameIcon size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.trending')}
                        </div>
                        <div className="text-[11px] text-slate-500">Trending silhouettes & brand drops</div>
                      </div>
                    </Link>
                  </div>
                )}
              </div>

              {/* 3. Try-On & Fit Dropdown */}
              <div
                className="relative"
                onMouseEnter={() => setActiveDropdown('tryon')}
                onMouseLeave={() => setActiveDropdown(null)}
              >
                <button
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                    activeDropdown === 'tryon' || isActive('/tryon-studio')
                      ? 'text-[#1B1F3B] bg-slate-100 font-bold'
                      : 'text-slate-600 hover:text-[#1B1F3B] hover:bg-slate-50'
                  }`}
                >
                  <TryOnIcon size={18} isActive={activeDropdown === 'tryon'} />
                  <span>{t('nav.tryon_fit')}</span>
                  <span className="text-[9px] text-slate-400">▼</span>
                </button>

                {activeDropdown === 'tryon' && (
                  <div className="absolute top-full left-0 w-72 bg-white border border-slate-100 rounded-2xl shadow-xl p-3 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                    <Link
                      to="/tryon-studio"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-[#FDF8EE] transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-[#FDF8EE]">
                        <TryOnIcon size={20} color="#C5A059" isAi={true} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.virtual_tryon')}
                        </div>
                        <div className="text-[11px] text-slate-500">Interactive drape & multi-garment try-on</div>
                      </div>
                    </Link>

                    <Link
                      to="/fit"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-50 transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100">
                        <RulerIcon size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.no_photo_fit')}
                        </div>
                        <div className="text-[11px] text-slate-500">Zero-photo size & measurement engine</div>
                      </div>
                    </Link>
                  </div>
                )}
              </div>

              {/* 4. Wardrobe Dropdown */}
              <div
                className="relative"
                onMouseEnter={() => setActiveDropdown('wardrobe')}
                onMouseLeave={() => setActiveDropdown(null)}
              >
                <Link
                  to="/wardrobe"
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                    activeDropdown === 'wardrobe' || isActive('/wardrobe')
                      ? 'text-[#1B1F3B] bg-slate-100 font-bold'
                      : 'text-slate-600 hover:text-[#1B1F3B] hover:bg-slate-50'
                  }`}
                >
                  <WardrobeIcon size={18} isActive={isActive('/wardrobe')} />
                  <span>{t('nav.my_wardrobe')}</span>
                  <span className="text-[9px] text-slate-400">▼</span>
                </Link>

                {activeDropdown === 'wardrobe' && (
                  <div className="absolute top-full left-0 w-72 bg-white border border-slate-100 rounded-2xl shadow-xl p-3 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                    <Link
                      to="/wardrobe"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-50 transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100">
                        <WardrobeIcon size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.my_closet')}
                        </div>
                        <div className="text-[11px] text-slate-500">Auto-tagged owned clothing</div>
                      </div>
                    </Link>

                    <Link
                      to="/wardrobe?tab=looks"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-50 transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100">
                        <SavedLooksIcon size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.my_looks')}
                        </div>
                        <div className="text-[11px] text-slate-500">Saved outfit combinations</div>
                      </div>
                    </Link>

                    <Link
                      to="/wardrobe?tab=gaps"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-[#FDF8EE] transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-[#FDF8EE]">
                        <GapAnalysisIcon size={20} color="#C5A059" />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.gap_analysis')}
                        </div>
                        <div className="text-[11px] text-slate-500">Discover missing closet staples</div>
                      </div>
                    </Link>
                  </div>
                )}
              </div>

              {/* 5. Shop Dropdown */}
              <div
                className="relative"
                onMouseEnter={() => setActiveDropdown('shop')}
                onMouseLeave={() => setActiveDropdown(null)}
              >
                <Link
                  to="/discover"
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                    activeDropdown === 'shop' || isActive('/discover')
                      ? 'text-[#1B1F3B] bg-slate-100 font-bold'
                      : 'text-slate-600 hover:text-[#1B1F3B] hover:bg-slate-50'
                  }`}
                >
                  <BagIcon size={18} isActive={isActive('/discover')} />
                  <span>{t('nav.shop')}</span>
                  <span className="text-[9px] text-slate-400">▼</span>
                </Link>

                {activeDropdown === 'shop' && (
                  <div className="absolute top-full left-0 w-72 bg-white border border-slate-100 rounded-2xl shadow-xl p-3 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                    <Link
                      to="/discover"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-50 transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100">
                        <BagIcon size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          All Collections
                        </div>
                        <div className="text-[11px] text-slate-500">Curated multi-brand catalog</div>
                      </div>
                    </Link>

                    <Link
                      to="/orders"
                      onClick={() => setActiveDropdown(null)}
                      className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-slate-50 transition-colors group"
                    >
                      <div className="p-2 rounded-lg bg-slate-100">
                        <OrdersIcon size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">
                          {t('nav.orders_tracking')}
                        </div>
                        <div className="text-[11px] text-slate-500">Real-time status & timelines</div>
                      </div>
                    </Link>
                  </div>
                )}
              </div>
            </nav>
          </div>

          {/* Far Right: Utility Cluster (Search, Bag, Account) */}
          <div className="flex items-center gap-2 sm:gap-4">
            {/* Visual Search Quick Button */}
            <button
              onClick={() => openVisualSearch()}
              className="p-2.5 rounded-full text-slate-600 hover:text-[#C5A059] hover:bg-[#FDF8EE] transition-all"
              title={t('nav.visual_search')}
              aria-label="Open Visual Search"
            >
              <VisualSearchIcon size={20} color="#C5A059" />
            </button>

            {/* Shopping Bag / Cart with Badge */}
            <button
              onClick={openCart}
              className="relative p-2.5 rounded-full text-slate-700 hover:text-[#1B1F3B] hover:bg-slate-100 transition-all"
              aria-label="Open Shopping Bag"
            >
              <BagIcon size={20} badge={itemsCount} />
            </button>

            {/* User Account / Profile */}
            {isAuthenticated && user ? (
              <div
                className="relative"
                onMouseEnter={() => setActiveDropdown('user_menu')}
                onMouseLeave={() => setActiveDropdown(null)}
              >
                <Link
                  to="/profile"
                  className="flex items-center gap-2 p-1.5 pr-3 rounded-full hover:bg-slate-100 border border-slate-200/80 transition-all"
                >
                  <div className="w-8 h-8 rounded-full bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold text-xs shadow-2xs">
                    {user.full_name.charAt(0)}
                  </div>
                  <span className="hidden md:inline text-xs font-semibold text-slate-800">
                    {user.full_name.split(' ')[0]}
                  </span>
                </Link>

                {activeDropdown === 'user_menu' && (
                  <div className="absolute top-full right-0 w-60 bg-white border border-slate-100 rounded-2xl shadow-xl p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150 text-xs">
                    <div className="p-2.5 border-b border-slate-100 mb-1">
                      <div className="font-bold text-slate-900 truncate">{user.full_name}</div>
                      <div className="text-[10px] text-slate-500 truncate">{user.email}</div>
                      <div className="mt-1 inline-block px-2 py-0.5 rounded bg-slate-100 text-[10px] font-medium text-slate-700 capitalize">
                        Role: {user.role?.replace('_', ' ')}
                      </div>
                    </div>

                    <Link
                      to="/profile"
                      onClick={() => setActiveDropdown(null)}
                      className="block px-3 py-2 rounded-xl hover:bg-slate-50 text-slate-700 font-medium"
                    >
                      Style Profile (USP)
                    </Link>

                    <Link
                      to="/orders"
                      onClick={() => setActiveDropdown(null)}
                      className="block px-3 py-2 rounded-xl hover:bg-slate-50 text-slate-700 font-medium"
                    >
                      My Orders & Tracking
                    </Link>

                    <Link
                      to="/wardrobe"
                      onClick={() => setActiveDropdown(null)}
                      className="block px-3 py-2 rounded-xl hover:bg-slate-50 text-slate-700 font-medium"
                    >
                      Virtual Wardrobe
                    </Link>

                    {isPrivileged && (
                      <Link
                        to={isAdmin ? '/admin' : '/b2b'}
                        onClick={() => setActiveDropdown(null)}
                        className="block px-3 py-2 rounded-xl bg-[#FDF8EE] text-[#C5A059] font-bold hover:bg-[#C5A059] hover:text-white transition-colors mt-1"
                      >
                        {isAdmin ? 'Admin Governance Panel' : 'Brand Partner Dashboard'}
                      </Link>
                    )}

                    <div className="border-t border-slate-100 mt-1 pt-1">
                      <button
                        onClick={() => {
                          setActiveDropdown(null);
                          logout();
                          navigate('/');
                        }}
                        className="w-full text-left px-3 py-2 rounded-xl text-rose-600 hover:bg-rose-50 font-semibold"
                      >
                        Sign Out
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={() => openAuthModal('login')}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-medium text-xs transition-all shadow-sm"
              >
                <UserIcon size={15} color="#FFFFFF" />
                <span>{t('common.sign_in')}</span>
              </button>
            )}
          </div>
        </div>
      </header>
    </>
  );
};
