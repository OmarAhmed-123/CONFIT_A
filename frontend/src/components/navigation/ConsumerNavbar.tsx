import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Menu, X, ChevronDown } from 'lucide-react';
import {
  VisualSearchIcon,
  BagIcon,
  UserIcon,
  BrandDashboardIcon,
  ShieldIcon,
} from '../icons/ConfitIcons';
import { ConfitLogo } from '../common/ConfitLogo';
import { useCartStore } from '../../stores/cartStore';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { msg } from '../../i18n/messages';
import { LanguageSwitcher } from './LanguageSwitcher';
import { CurrencySwitcher } from './CurrencySwitcher';
import { CONSUMER_NAV, isSectionActive, isItemActive, type NavAction, type NavItem, type NavSection } from './navMetadata';

/**
 * Consumer shell navigation — spec 05 (Magic Navigation / App Shell).
 *
 * WHAT THIS REWRITE FIXES, each item a real defect in the previous navbar:
 *
 *  1. HOVER WAS THE ONLY WAY IN. Menus opened exclusively on `mouseenter`.
 *     A keyboard user could Tab THROUGH a trigger but never see its panel;
 *     a touch user got whatever the browser synthesized. Triggers are now
 *     real disclosure buttons (click / Enter / Space, `aria-expanded`,
 *     `aria-controls`, Escape closes and returns focus). Hover still opens
 *     them on pointer devices — as an enhancement, not the mechanism.
 *  2. MOBILE HAD NO PRIMARY NAV AT ALL. The nav was `hidden lg:flex` and
 *     nothing replaced it below `lg`; a phone visitor could reach Discover
 *     only through the footer. Below `lg` a hamburger now opens a drawer
 *     built from the same metadata (same vocabulary, zero drift).
 *  3. ONE NAV VOCABULARY. Destinations/labels/icons live in navMetadata;
 *     desktop menus, the drawer and active-state matching all read it.
 *  4. `aria-current="page"` marks the active destination — state is exposed
 *     as text/semantics, not colour alone (spec §7).
 *  5. Logical direction (`start/end`) everywhere a panel is anchored, so the
 *     Arabic shell mirrors without manual flipping.
 *
 * Deliberate choices:
 *  · Disclosure pattern (buttons + lists of links), NOT `role="menu"` —
 *    menubar semantics demand roving tabindex and first-letter navigation;
 *    claiming them without implementing them is worse than links.
 *  · The drawer overlay is a plain translucent colour, no `backdrop-filter`
 *    (spec §8: blur over a full-viewport scrim on low-end phones).
 *  · Open/close animation comes from the global `animate-in` utilities which
 *    `styles/index.css` disables under `prefers-reduced-motion`; nothing
 *    here waits for an animation to function.
 */

const deskTrigger = (active: boolean) =>
  `flex min-h-11 items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
    active ? 'text-[#1B1F3B] bg-slate-100 font-bold' : 'text-slate-600 hover:text-[#1B1F3B] hover:bg-slate-50'
  }`;

export const ConsumerNavbar: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const baseId = useId();

  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const { cart, openCart } = useCartStore();
  const { user, isAuthenticated, logout } = useAuthStore();
  const { openStylist, openVisualSearch, openAuthModal, showToast } = useUIStore();

  const itemsCount = cart?.items_count || 0;
  const isPrivileged =
    user?.role && ['brand_owner', 'brand_manager', 'brand_staff', 'admin'].includes(user.role.toLowerCase());
  const isAdmin = user?.role?.toLowerCase() === 'admin';

  // A navigation closes every open surface: the panel's job is done.
  useEffect(() => {
    setOpenMenu(null);
    setDrawerOpen(false);
  }, [location.pathname, location.search]);

  const runAction = useCallback(
    (action: NavAction) => {
      setOpenMenu(null);
      setDrawerOpen(false);
      if (action === 'open-stylist') openStylist();
      else openVisualSearch();
    },
    [openStylist, openVisualSearch],
  );

  const handleLogout = useCallback(async () => {
    setOpenMenu(null);
    setDrawerOpen(false);
    try {
      await logout();
      navigate('/');
    } catch {
      // Server-side sign-out failed: say so. Claiming a sign-out that did
      // not happen would leave a session the user believes is closed.
      showToast(msg('toast.sign_out_failed'), 'error');
    }
  }, [logout, navigate, showToast]);

  /** Close a desktop disclosure when focus leaves its container entirely. */
  const closeOnFocusOut = (menuId: string) => (e: React.FocusEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setOpenMenu((cur) => (cur === menuId ? null : cur));
    }
  };

  /** Escape inside a disclosure closes it and restores focus to its trigger. */
  const closeOnEscape = (menuId: string, triggerId: string) => (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      setOpenMenu((cur) => (cur === menuId ? null : cur));
      document.getElementById(triggerId)?.focus();
    }
  };

  const renderMenuItem = (item: NavItem) => {
    const IconComp = item.icon;
    const inner = (
      <>
        <div
          aria-hidden="true"
          className={`p-2 rounded-lg transition-colors ${item.accent ? 'bg-[#FDF8EE] group-hover:bg-[#C5A059]' : 'bg-slate-100 group-hover:bg-slate-200'}`}
        >
          <IconComp size={20} color={item.accent ? '#C5A059' : undefined} />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-bold text-[#1B1F3B] group-hover:text-[#C5A059]">{t(item.labelKey)}</div>
          {item.descKey && <div className="text-[11px] text-slate-500">{t(item.descKey)}</div>}
        </div>
      </>
    );
    const itemClass = `flex w-full min-h-11 items-start gap-3 p-2.5 rounded-xl text-start transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
      item.accent ? 'hover:bg-[#FDF8EE]' : 'hover:bg-slate-50'
    }`;
    return item.href ? (
      <Link
        key={item.id}
        to={item.href}
        aria-current={isItemActive(item, location.pathname) ? 'page' : undefined}
        onClick={() => setOpenMenu(null)}
        className={itemClass}
      >
        {inner}
      </Link>
    ) : (
      <button key={item.id} type="button" onClick={() => runAction(item.action!)} className={itemClass}>
        {inner}
      </button>
    );
  };

  const renderDesktopSection = (section: NavSection) => {
    const active = isSectionActive(section, location.pathname);
    const SectionIcon = section.icon;

    if (!section.children) {
      return (
        <Link
          key={section.id}
          to={section.href!}
          aria-current={active ? 'page' : undefined}
          className={deskTrigger(active)}
        >
          <span aria-hidden="true"><SectionIcon size={18} isActive={active} /></span>
          <span>{t(section.labelKey)}</span>
        </Link>
      );
    }

    const panelId = `${baseId}-${section.id}-panel`;
    const triggerId = `${baseId}-${section.id}-trigger`;
    const open = openMenu === section.id;

    return (
      <div
        key={section.id}
        className="relative"
        onMouseEnter={() => setOpenMenu(section.id)}
        onMouseLeave={() => setOpenMenu((cur) => (cur === section.id ? null : cur))}
        onBlur={closeOnFocusOut(section.id)}
        onKeyDown={closeOnEscape(section.id, triggerId)}
      >
        <button
          type="button"
          id={triggerId}
          aria-expanded={open}
          aria-haspopup="true"
          aria-controls={panelId}
          onClick={() => setOpenMenu(open ? null : section.id)}
          className={deskTrigger(open || active)}
          aria-current={active ? 'page' : undefined}
        >
          <span aria-hidden="true">
            <SectionIcon size={18} isActive={open || active} color={section.id === 'discover' ? '#C5A059' : undefined} />
          </span>
          <span>{t(section.labelKey)}</span>
          <ChevronDown size={12} aria-hidden="true" className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>

        {open && (
          <div
            id={panelId}
            className="absolute top-full start-0 w-80 bg-white border border-slate-100 rounded-2xl shadow-xl p-3 z-50 animate-in fade-in slide-in-from-top-2 duration-150"
          >
            {section.children.map(renderMenuItem)}
          </div>
        )}
      </div>
    );
  };

  return (
    <header className="z-40">
      {/* Top thin luxury bar */}
      <div className="bg-[#0C0E1E] text-slate-400 text-xs py-1.5 px-4 sm:px-8 flex justify-between items-center border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#C5A059] animate-pulse" aria-hidden="true"></span>
          <span className="hidden sm:inline text-slate-300 font-light tracking-wide">{t('nav.brand_line')}</span>
          <span className="sm:hidden text-slate-300">{t('nav_desc.studio')}</span>
        </div>
        <div className="flex items-center gap-4">
          {isPrivileged ? (
            <Link
              to={isAdmin ? '/admin' : '/b2b'}
              className="inline-flex min-h-8 items-center gap-1.5 text-[#C5A059] hover:text-[#E2BF70] font-semibold transition-colors text-xs"
            >
              <span aria-hidden="true">{isAdmin ? <ShieldIcon size={14} color="#C5A059" /> : <BrandDashboardIcon size={14} color="#C5A059" />}</span>
              <span>{isAdmin ? t('nav.admin_governance') : t('nav.brand_partner_hub')}</span>
            </Link>
          ) : (
            <Link
              to="/b2b"
              className="inline-flex min-h-8 items-center gap-1.5 text-slate-400 hover:text-[#C5A059] font-medium transition-colors text-xs"
            >
              <span aria-hidden="true"><BrandDashboardIcon size={14} color="#C5A059" /></span>
              <span>{t('nav.partner_portal')}</span>
            </Link>
          )}
          <div className="h-3 w-px bg-slate-800" aria-hidden="true" />
          <LanguageSwitcher />
          <CurrencySwitcher />
        </div>
      </div>

      {/* Main consumer navigation bar */}
      <div className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200/80 shadow-2xs transition-all">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          <div className="flex min-w-0 items-center gap-4 lg:gap-8">
            {/* Hamburger — the mobile way IN. 44px floor, named, stateful. */}
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-expanded={drawerOpen}
              aria-haspopup="dialog"
              aria-label={t('a11y.open_menu')}
              className="lg:hidden inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
            >
              <Menu size={22} aria-hidden="true" />
            </button>

            <Link
              to="/"
              className="flex shrink-0 items-center group rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
            >
              <ConfitLogo variant="mark" theme="dark" size="sm" className="sm:hidden" />
              <ConfitLogo variant="full" theme="dark" size="md" className="hidden sm:inline-flex" />
            </Link>

            {/* Desktop primary nav — one source: CONSUMER_NAV */}
            <nav ref={navRef} aria-label={t('a11y.primary_nav')} className="hidden lg:flex items-center gap-1 xl:gap-2">
              {CONSUMER_NAV.map(renderDesktopSection)}
            </nav>
          </div>

          {/* Utility cluster */}
          <div className="flex items-center gap-1 sm:gap-3">
            <button
              onClick={() => openVisualSearch()}
              type="button"
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-slate-600 hover:text-[#C5A059] hover:bg-[#FDF8EE] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
              aria-label={t('a11y.open_visual_search')}
            >
              <VisualSearchIcon size={20} color="#C5A059" />
            </button>

            <button
              onClick={openCart}
              type="button"
              className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-slate-700 hover:text-[#1B1F3B] hover:bg-slate-100 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
              aria-label={t('a11y.open_shopping_bag')}
            >
              <BagIcon size={20} badge={itemsCount} />
            </button>

            {isAuthenticated && user ? (
              <div
                ref={userMenuRef}
                className="relative"
                onMouseEnter={() => setOpenMenu('user_menu')}
                onMouseLeave={() => setOpenMenu((cur) => (cur === 'user_menu' ? null : cur))}
                onBlur={closeOnFocusOut('user_menu')}
                onKeyDown={closeOnEscape('user_menu', `${baseId}-user-trigger`)}
              >
                <button
                  type="button"
                  id={`${baseId}-user-trigger`}
                  aria-expanded={openMenu === 'user_menu'}
                  aria-haspopup="true"
                  aria-controls={`${baseId}-user-panel`}
                  aria-label={t('a11y.account_menu')}
                  onClick={() => setOpenMenu(openMenu === 'user_menu' ? null : 'user_menu')}
                  className="flex min-h-11 items-center gap-2 p-1.5 pe-3 rounded-full hover:bg-slate-100 border border-slate-200/80 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
                >
                  <div className="w-8 h-8 rounded-full bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold text-xs shadow-2xs" aria-hidden="true">
                    {user.full_name.charAt(0)}
                  </div>
                  <span className="hidden md:inline text-xs font-semibold text-slate-800">
                    {user.full_name.split(' ')[0]}
                  </span>
                  <ChevronDown size={12} aria-hidden="true" className="hidden md:inline text-slate-400" />
                </button>

                {openMenu === 'user_menu' && (
                  <div
                    id={`${baseId}-user-panel`}
                    className="absolute top-full end-0 w-60 bg-white border border-slate-100 rounded-2xl shadow-xl p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150 text-xs"
                  >
                    <div className="p-2.5 border-b border-slate-100 mb-1">
                      <div className="font-bold text-slate-900 truncate">{user.full_name}</div>
                      {/* Email is Latin — keep it LTR inside the Arabic shell. */}
                      <div className="text-[10px] text-slate-500 truncate" dir="ltr">{user.email}</div>
                      <div className="mt-1 inline-block px-2 py-0.5 rounded bg-slate-100 text-[10px] font-medium text-slate-700 capitalize">
                        {t('account.role_label')}{' '}
                        <span dir="ltr">{user.role?.replace('_', ' ')}</span>
                      </div>
                    </div>

                    <Link to="/profile" onClick={() => setOpenMenu(null)} className="flex min-h-11 items-center px-3 py-2 rounded-xl hover:bg-slate-50 text-slate-700 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]">
                      {t('account.style_profile')}
                    </Link>
                    <Link to="/orders" onClick={() => setOpenMenu(null)} className="flex min-h-11 items-center px-3 py-2 rounded-xl hover:bg-slate-50 text-slate-700 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]">
                      {t('account.orders_tracking')}
                    </Link>
                    <Link to="/wardrobe" onClick={() => setOpenMenu(null)} className="flex min-h-11 items-center px-3 py-2 rounded-xl hover:bg-slate-50 text-slate-700 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]">
                      {t('account.virtual_wardrobe')}
                    </Link>

                    {isPrivileged && (
                      <Link
                        to={isAdmin ? '/admin' : '/b2b'}
                        onClick={() => setOpenMenu(null)}
                        className="flex min-h-11 items-center px-3 py-2 rounded-xl bg-[#FDF8EE] text-[#C5A059] font-bold hover:bg-[#C5A059] hover:text-white transition-colors mt-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
                      >
                        {isAdmin ? t('account.admin_panel') : t('account.partner_dashboard')}
                      </Link>
                    )}

                    <div className="border-t border-slate-100 mt-1 pt-1">
                      <button
                        type="button"
                        onClick={handleLogout}
                        className="w-full min-h-11 text-start px-3 py-2 rounded-xl text-rose-600 hover:bg-rose-50 font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
                      >
                        {t('account.sign_out')}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={() => openAuthModal('login')}
                type="button"
                className="inline-flex min-h-11 items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-medium text-xs transition-all shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
              >
                <span aria-hidden="true"><UserIcon size={15} color="#FFFFFF" /></span>
                <span>{t('common.sign_in')}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      <MobileNavDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onAction={runAction}
        isAuthenticated={isAuthenticated}
        onSignIn={() => {
          setDrawerOpen(false);
          openAuthModal('login');
        }}
        onSignOut={handleLogout}
      />
    </header>
  );
};

/**
 * Mobile navigation drawer — modal dialog with a REAL focus trap (spec §8:
 * "لا تسمح focus خلف drawer"). Tab wraps inside the panel, Escape closes and
 * focus returns to the hamburger (the invoker). Built from the same
 * CONSUMER_NAV metadata as the desktop menus.
 */
const MobileNavDrawer: React.FC<{
  open: boolean;
  onClose: () => void;
  onAction: (action: NavAction) => void;
  isAuthenticated: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
}> = ({ open, onClose, onAction, isAuthenticated, onSignIn, onSignOut }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // Focus management: remember the invoker, enter the panel, restore on close.
  useEffect(() => {
    if (open) {
      restoreFocusRef.current = (document.activeElement as HTMLElement) ?? null;
      // The close button is the first focusable — predictable entry point.
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
    // Wrap Tab inside the dialog: nothing behind the drawer may take focus.
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
      {/* Scrim: plain colour, no backdrop-filter (spec §8). Click closes. */}
      <div className="absolute inset-0 bg-slate-950/70" onClick={onClose} aria-hidden="true" />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('a11y.mobile_nav_label')}
        className="absolute inset-y-0 start-0 w-[85vw] max-w-sm bg-white shadow-2xl flex flex-col animate-in fade-in duration-200"
      >
        <div className="flex items-center justify-between px-4 py-4 border-b border-slate-100">
          <ConfitLogo variant="full" theme="dark" size="sm" />
          <button
            type="button"
            data-drawer-close
            onClick={onClose}
            aria-label={t('a11y.close_menu')}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            <X size={22} aria-hidden="true" />
          </button>
        </div>

        <nav aria-label={t('a11y.primary_nav')} className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
          {CONSUMER_NAV.map((section) => {
            const SectionIcon = section.icon;
            const active = isSectionActive(section, location.pathname);
            if (!section.children) {
              return (
                <Link
                  key={section.id}
                  to={section.href!}
                  aria-current={active ? 'page' : undefined}
                  className={`flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
                    active ? 'bg-[#FDF8EE] text-[#7A5C28]' : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <span aria-hidden="true"><SectionIcon size={20} isActive={active} /></span>
                  <span>{t(section.labelKey)}</span>
                </Link>
              );
            }
            return (
              <div key={section.id}>
                {/* Group header: static text, not a toggle — one tap reaches
                    any destination; nothing is hidden two levels deep. */}
                <div className="flex items-center gap-2 px-3 pb-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-400">
                  <span aria-hidden="true"><SectionIcon size={14} /></span>
                  <span>{t(section.labelKey)}</span>
                </div>
                <ul className="space-y-0.5">
                  {section.children.map((item) => {
                    const ItemIcon = item.icon;
                    const itemActive = isItemActive(item, location.pathname);
                    const cls = `flex w-full min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-start focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
                      itemActive ? 'bg-[#FDF8EE] text-[#7A5C28] font-bold' : 'text-slate-700 hover:bg-slate-50'
                    }`;
                    return (
                      <li key={item.id}>
                        {item.href ? (
                          <Link to={item.href} aria-current={itemActive ? 'page' : undefined} className={cls}>
                            <span aria-hidden="true"><ItemIcon size={18} color={item.accent ? '#C5A059' : undefined} /></span>
                            <span>{t(item.labelKey)}</span>
                          </Link>
                        ) : (
                          <button type="button" onClick={() => onAction(item.action!)} className={cls}>
                            <span aria-hidden="true"><ItemIcon size={18} color={item.accent ? '#C5A059' : undefined} /></span>
                            <span>{t(item.labelKey)}</span>
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>

        <div className="border-t border-slate-100 p-3">
          {isAuthenticated ? (
            <button
              type="button"
              onClick={onSignOut}
              className="w-full min-h-11 rounded-xl px-3 py-2.5 text-start text-sm font-semibold text-rose-600 hover:bg-rose-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
            >
              {t('account.sign_out')}
            </button>
          ) : (
            <button
              type="button"
              onClick={onSignIn}
              className="w-full min-h-11 rounded-xl bg-[#1B1F3B] px-3 py-2.5 text-sm font-semibold text-white hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
            >
              {t('common.sign_in')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
