import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BrandNavbar, BrandBreadcrumbs } from '../components/navigation/BrandNavbar';
import { SkipLink, SKIP_TARGET_ID } from '../components/common/SkipLink';
import { PortalBackButton } from '../components/navigation/PortalBackButton';
import { RegisterBanner } from '../components/common/RegisterBanner';
import { resolveRegister, registerStyle } from '../design/registers';

export const BrandLayout: React.FC = () => {
  const location = useLocation();
  const register = resolveRegister(location.pathname);
  const { t } = useTranslation();
  // AUTH-02 FIX: Toast is mounted at the App root so toasts fired on /b2b
  // and /admin (gate actions, brand CRUD) render identically. The local
  // Toast here previously double-rendered with the global one.
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      {/* WCAG 2.4.1: the brand portal has an even longer nav (catalog,
          inventory, analytics, placements, admin) before any content. */}
      <SkipLink />
      {/* Spec 13: desktop = sidebar + content row; mobile = top bar +
          drawer (both rendered by BrandNavbar). */}
      <div className="flex flex-1 lg:flex-row flex-col min-w-0">
        <BrandNavbar />

        <main
          id={SKIP_TARGET_ID}
          tabIndex={-1}
          data-register={register}
          style={registerStyle(register) as React.CSSProperties}
          className="flex-1 min-w-0 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-8 outline-none"
        >
          <RegisterBanner register={register} />
          <BrandBreadcrumbs />
          <PortalBackButton />
          <Outlet />
        </main>
      </div>

      <footer className="bg-slate-900 border-t border-slate-800 text-slate-500 text-xs py-8 px-4 sm:px-8 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4">
          <div>
            {t('b2b_layout.platform_title')} · 1.0.0
          </div>
          <div className="flex gap-4">
            <Link to="/" className="text-[#B8935A] hover:underline">
              {t('b2b_layout.switch_to_consumer')}
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
