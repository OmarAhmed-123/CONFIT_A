import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { ConsumerNavbar } from '../components/navigation/ConsumerNavbar';
import { VirtualStylistDrawer } from '../components/stylist/VirtualStylistDrawer';
import { VirtualTryOnModal } from '../components/tryon/VirtualTryOnModal';
import { TryOnStudioErrorBoundary } from '../components/tryon/TryOnStudioErrorBoundary';
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
import { RegisterBanner } from '../components/common/RegisterBanner';
import { resolveRegister, registerStyle } from '../design/registers';

export const ConsumerLayout: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const register = resolveRegister(location.pathname);
  const { openStylist } = useUIStore();
  // AUTH-02 FIX: fetchMe bootstrap moved to App (session must restore on
  // /b2b and /admin too); AuthModal/Toast are now mounted at the app root.
  const { fetchCart } = useCartStore();

  useEffect(() => {
    fetchCart();
  }, [fetchCart]);

  return (
    <div className="min-h-screen flex flex-col bg-white text-brand-charcoal">
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
        data-register={register}
        style={registerStyle(register) as React.CSSProperties}
        className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-6 sm:pt-8 outline-none"
      >
        <RegisterBanner register={register} />
        <Outlet />
      </main>

      {/* Floating AI Stylist FAB */}
      {/* Mobile: 48px icon-only control, bottom-4. Overlay footprint is measured (see
          coverage doc). A sticky CTA on the page raises it via .stylist-fab-anchor. */}
      <div className="stylist-fab-anchor fixed end-4 sm:end-6 z-40">
        {/* px-4.5 is not a Tailwind token (same class of defect as the
            p-4.5 card fixed in C03 pass 2) — the pill rendered with NO
            horizontal padding and its label touched the rounded edge
            (visible in the 2026-10-08 production screenshot). px-5 is
            the nearest real step. */}
        <button data-motion="creative"
          onClick={() => openStylist()}
          className="group flex h-12 w-12 items-center justify-center gap-2.5 rounded-full bg-white p-0 hover:bg-brand-wash text-brand-charcoal shadow-lg hover:scale-105 active:scale-95 transition-all border border-brand-field sm:h-auto sm:w-auto sm:px-5 sm:py-3"
          aria-label={t('layout.ai_stylist_director')}
          type="button"
        >
          <div className="w-6 h-6 rounded-full bg-brand-charcoal flex items-center justify-center text-white shadow-xs">
            <SparkleIcon size={14} color="#FFFFFF" />
          </div>
          <span className="hidden sm:inline font-serif font-bold text-xs tracking-wider text-brand-charcoal">
            {t('layout.ai_stylist_director')}
          </span>
        </button>
      </div>

      {/* Global Modals & Drawers (AuthModal + Toast live at App root) */}
      <VirtualStylistDrawer />
      <TryOnStudioErrorBoundary>
        <VirtualTryOnModal />
      </TryOnStudioErrorBoundary>
      <NoPhotoFitModal />
      <VisualSearchModal />
      <DuplicateAlertModal />
      <CartDrawer />

      {/* Luxury Footer */}
      {/* pb-28 (112px) is not decoration: it is the space the browser needs to
          scroll the last focusable items clear of the fixed AI Stylist FAB.
          Combined with `scroll-padding-bottom` in styles/index.css, this is the
          WCAG 2.2 SC 2.4.11 (Focus Not Obscured) fix — without trailing space the
          page cannot scroll any further and the links stay under the FAB. */}
      <footer className="bg-brand-wash text-brand-muted text-xs border-t border-brand-hairline pt-14 pb-28 px-4 sm:px-8 mt-auto">
        <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10">
          <div className="space-y-3">
            <div className="font-serif tracking-widest text-2xl font-bold text-brand-charcoal flex items-center gap-2">
              {/* Latin wordmark inside a possibly-RTL page: isolate it so
                  bidi reordering cannot mangle the letter order. */}
              <span dir="ltr" className="force-ltr">CONFIT</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-brand-lilac/30 text-brand-charcoal font-sans font-semibold">
                {t('footer.haute_tech')}
              </span>
            </div>
            <p className="text-brand-muted text-xs leading-relaxed font-light max-w-xs">
              {t('footer.tagline_full')}
            </p>
          </div>

          <div className="space-y-3">
            <div className="font-bold text-brand-charcoal uppercase tracking-wider text-[11px]">{t('footer.experiences_heading')}</div>
            <ul className="space-y-2 font-light">
              <li><Link to="/discover" className="hover:text-brand-charcoal hover:underline transition-colors">{t('footer.exp_catalog')}</Link></li>
              <li><Link to="/builder" className="hover:text-brand-charcoal hover:underline transition-colors">{t('footer.exp_builder')}</Link></li>
              <li><Link to="/tryon-studio" className="hover:text-brand-charcoal hover:underline transition-colors">{t('footer.exp_tryon')}</Link></li>
              <li><Link to="/wardrobe" className="hover:text-brand-charcoal hover:underline transition-colors">{t('footer.exp_wardrobe')}</Link></li>
            </ul>
          </div>

          <div className="space-y-3">
            <div className="font-bold text-brand-charcoal uppercase tracking-wider text-[11px]">{t('footer.commerce_trust')}</div>
            {/* Claims are read from the deployment's own /catalog/capabilities —
                see TrustFooter for why each one is gated. */}
            <TrustFooter />
          </div>

          <div className="space-y-3">
            <div className="font-bold text-brand-charcoal uppercase tracking-wider text-[11px]">{t('footer.for_brands')}</div>
            <p className="text-brand-muted text-xs font-light leading-relaxed">
              {t('footer.brands_pitch')}
            </p>
            <Link
              to="/b2b"
              className="inline-block mt-2 px-4 py-2.5 rounded-xl bg-brand-charcoal hover:bg-[#1A1B1D] text-white font-bold text-xs shadow-md transition-all"
            >
              {t('footer.open_brand_portal')}
            </Link>
          </div>
        </div>

        <div className="max-w-7xl mx-auto pt-8 mt-10 border-t border-brand-hairline flex flex-col sm:flex-row justify-between items-center gap-4 text-[11px] text-brand-muted font-light">
          <div>© {new Date().getFullYear()} {t('footer.rights')}</div>
          <div className="flex gap-6">
            <Link to="/privacy" className="text-brand-muted hover:text-brand-charcoal underline">{t('footer.privacy')}</Link>
            <Link to="/terms" className="text-brand-muted hover:text-brand-charcoal underline">{t('footer.terms')}</Link>
            <Link to="/gdpr" className="text-brand-muted hover:text-brand-charcoal underline">{t('footer.gdpr')}</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
