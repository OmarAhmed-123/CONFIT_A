import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, Link } from 'react-router-dom';
import { ConsumerNavbar } from '../components/navigation/ConsumerNavbar';
import { VirtualStylistDrawer } from '../components/stylist/VirtualStylistDrawer';
import { VirtualTryOnModal } from '../components/tryon/VirtualTryOnModal';
import { NoPhotoFitModal } from '../components/tryon/NoPhotoFitModal';
import { VisualSearchModal } from '../components/tryon/VisualSearchModal';
import { DuplicateAlertModal } from '../components/wardrobe/DuplicateAlertModal';
import { CartDrawer } from '../components/commerce/CartDrawer';
import { SplashScreen } from '../components/common/SplashScreen';
import { useUIStore } from '../stores/uiStore';
import { useCartStore } from '../stores/cartStore';
import { SparkleIcon } from '../components/icons/ConfitIcons';
import { SkipLink, SKIP_TARGET_ID } from '../components/common/SkipLink';
import { TrustFooter } from '../components/commerce/TrustFooter';

export const ConsumerLayout: React.FC = () => {
  const { t } = useTranslation();
  const { openStylist } = useUIStore();
  // AUTH-02 FIX: fetchMe bootstrap moved to App (session must restore on
  // /b2b and /admin too); AuthModal/Toast are now mounted at the app root.
  const { fetchCart } = useCartStore();

  useEffect(() => {
    fetchCart();
  }, [fetchCart]);

  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9F6] text-[#1B1F3B]">
      {/* WCAG 2.4.1 — first focusable element on the page. Hidden with
          sr-only (not display:none) and revealed on focus. */}
      <SkipLink />

      {/* Editorial Luxury Splash Screen (Session-Aware) */}
      <SplashScreen />

      {/* Consumer Header & Navigation */}
      <ConsumerNavbar />

      {/* Main View Container.
          id + tabIndex={-1}: the skip link and the route announcer move focus
          here, so "skip to content" actually lands in the content and the next
          Tab starts at this page's first control rather than back in the nav.
          tabIndex={-1} makes it programmatically focusable WITHOUT adding it to
          the tab order. */}
      <main
        id={SKIP_TARGET_ID}
        tabIndex={-1}
        className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-6 sm:pt-8 outline-none"
      >
        <Outlet />
      </main>

      {/* Floating AI Stylist FAB */}
      <div className="fixed bottom-20 lg:bottom-8 end-6 z-40">
        <button
          onClick={() => openStylist()}
          className="group flex items-center gap-2.5 px-4.5 py-3 rounded-full bg-[#0C0E1E] hover:bg-[#1B1F3B] text-white shadow-2xl hover:scale-105 active:scale-95 transition-all border border-[#C5A059]/40"
          aria-label={t('layout.open_ai_stylist')}
          type="button"
        >
          <div className="w-6 h-6 rounded-full bg-[#C5A059] flex items-center justify-center text-slate-950 shadow-xs">
            <SparkleIcon size={14} color="#0C0E1E" />
          </div>
          <span className="hidden sm:inline font-serif font-bold text-xs tracking-wider text-[#C5A059]">
            {t('layout.ai_stylist_director')}
          </span>
        </button>
      </div>

      {/* Global Modals & Drawers (AuthModal + Toast live at App root) */}
      <VirtualStylistDrawer />
      <VirtualTryOnModal />
      <NoPhotoFitModal />
      <VisualSearchModal />
      <DuplicateAlertModal />
      <CartDrawer />

      {/* Luxury Footer */}
      <footer className="bg-[#0C0E1E] text-slate-300 text-xs border-t border-slate-800 py-14 px-4 sm:px-8 mt-auto">
        <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10">
          <div className="space-y-3">
            <div className="font-serif tracking-widest text-2xl font-bold text-white flex items-center gap-2">
              {/* Latin wordmark inside a possibly-RTL page: isolate it so
                  bidi reordering cannot mangle the letter order. */}
              <span dir="ltr" className="force-ltr">CONFIT</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-[#C5A059]/20 text-[#C5A059] font-sans font-semibold">
                {t('footer.haute_tech')}
              </span>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed font-light max-w-xs">
              {t('footer.tagline_full')}
            </p>
          </div>

          <div className="space-y-3">
            <div className="font-bold text-white uppercase tracking-wider text-[11px]">{t('footer.experiences_heading')}</div>
            <ul className="space-y-2 font-light">
              <li><Link to="/discover" className="hover:text-[#C5A059] transition-colors">{t('footer.exp_catalog')}</Link></li>
              <li><Link to="/builder" className="hover:text-[#C5A059] transition-colors">{t('footer.exp_builder')}</Link></li>
              <li><Link to="/tryon-studio" className="hover:text-[#C5A059] transition-colors">{t('footer.exp_tryon')}</Link></li>
              <li><Link to="/wardrobe" className="hover:text-[#C5A059] transition-colors">{t('footer.exp_wardrobe')}</Link></li>
            </ul>
          </div>

          <div className="space-y-3">
            <div className="font-bold text-white uppercase tracking-wider text-[11px]">{t('footer.commerce_trust')}</div>
            {/* Claims are read from the deployment's own /catalog/capabilities —
                see TrustFooter for why each one is gated. */}
            <TrustFooter />
          </div>

          <div className="space-y-3">
            <div className="font-bold text-white uppercase tracking-wider text-[11px]">{t('footer.for_brands')}</div>
            <p className="text-slate-400 text-xs font-light leading-relaxed">
              {t('footer.brands_pitch')}
            </p>
            <Link
              to="/b2b"
              className="inline-block mt-2 px-4 py-2.5 rounded-xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs shadow-md transition-all"
            >
              {t('footer.open_brand_portal')}
            </Link>
          </div>
        </div>

        <div className="max-w-7xl mx-auto pt-8 mt-10 border-t border-slate-800 flex flex-col sm:flex-row justify-between items-center gap-4 text-[11px] text-slate-400 font-light">
          <div>© {new Date().getFullYear()} {t('footer.rights')}</div>
          <div className="flex gap-6">
            <Link to="/privacy" className="text-slate-300 hover:text-slate-400">{t('footer.privacy')}</Link>
            <Link to="/terms" className="text-slate-300 hover:text-slate-400">{t('footer.terms')}</Link>
            <Link to="/gdpr" className="text-slate-300 hover:text-slate-400">{t('footer.gdpr')}</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
