import React, { useEffect } from 'react';
import { Outlet, Link } from 'react-router-dom';
import { ConsumerNavbar } from '../components/navigation/ConsumerNavbar';
import { VirtualStylistDrawer } from '../components/stylist/VirtualStylistDrawer';
import { VirtualTryOnModal } from '../components/tryon/VirtualTryOnModal';
import { NoPhotoFitModal } from '../components/tryon/NoPhotoFitModal';
import { VisualSearchModal } from '../components/tryon/VisualSearchModal';
import { DuplicateAlertModal } from '../components/wardrobe/DuplicateAlertModal';
import { CartDrawer } from '../components/commerce/CartDrawer';
import { AuthModal } from '../views/auth/AuthModal';
import { Toast } from '../components/common/CommonComponents';
import { useUIStore } from '../stores/uiStore';
import { useAuthStore } from '../stores/authStore';
import { useCartStore } from '../stores/cartStore';
import { SparkleIcon } from '../components/icons/ConfitIcons';

export const ConsumerLayout: React.FC = () => {
  const { toast, hideToast, openStylist } = useUIStore();
  const { fetchMe } = useAuthStore();
  const { fetchCart } = useCartStore();

  useEffect(() => {
    fetchMe();
    fetchCart();
  }, [fetchMe, fetchCart]);

  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9F6] text-[#1B1F3B]">
      {/* Consumer Header & Navigation */}
      <ConsumerNavbar />

      {/* Main View Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-6 sm:pt-8">
        <Outlet />
      </main>

      {/* Floating AI Stylist FAB (Desktop & Mobile trigger) */}
      <div className="fixed bottom-20 lg:bottom-8 right-6 z-40">
        <button
          onClick={() => openStylist()}
          className="group flex items-center gap-2.5 px-4 py-3 rounded-full bg-[#1B1F3B] hover:bg-[#2A3C78] text-white shadow-2xl hover:scale-105 active:scale-95 transition-all border border-[#B8935A]/50"
          aria-label="Open AI Virtual Stylist"
        >
          <div className="w-6 h-6 rounded-full bg-[#B8935A] flex items-center justify-center text-slate-950 shadow-xs">
            <SparkleIcon size={14} color="#1B1F3B" />
          </div>
          <span className="hidden sm:inline font-serif font-bold text-xs tracking-wide">
            CONFIT Stylist AI
          </span>
        </button>
      </div>

      {/* Global Modals & Drawers */}
      <VirtualStylistDrawer />
      <VirtualTryOnModal />
      <NoPhotoFitModal />
      <VisualSearchModal />
      <DuplicateAlertModal />
      <CartDrawer />
      <AuthModal />

      {/* Global Toast */}
      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={hideToast} />
      )}

      {/* Luxury Footer */}
      <footer className="bg-[#1B1F3B] text-slate-400 text-xs border-t border-slate-800 py-12 px-4 sm:px-8 mt-auto">
        <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          <div className="space-y-2">
            <div className="font-serif tracking-widest text-xl font-bold text-white">CONFIT</div>
            <p className="text-slate-400 text-xs max-w-xs leading-relaxed">
              Where Style Meets Your Character in Every Moment. Combining generative AI styling, precision virtual try-on, and smart wardrobe reuse.
            </p>
          </div>

          <div className="space-y-2">
            <div className="font-bold text-white uppercase tracking-wider text-[11px]">Experience</div>
            <ul className="space-y-1.5">
              <li><Link to="/discover" className="hover:text-white">Style & Discover</Link></li>
              <li><Link to="/builder" className="hover:text-white">Outfit Builder Canvas</Link></li>
              <li><Link to="/tryon-studio" className="hover:text-white">Virtual Try-On Studio</Link></li>
              <li><Link to="/wardrobe" className="hover:text-white">Smart Wardrobe & Gap Analysis</Link></li>
            </ul>
          </div>

          <div className="space-y-2">
            <div className="font-bold text-white uppercase tracking-wider text-[11px]">Trust & Commerce</div>
            <ul className="space-y-1.5">
              <li><span className="text-slate-400">Tabby & Tamara 0% BNPL</span></li>
              <li><span className="text-slate-400">BOPIS In-Store Pickup in 2h</span></li>
              <li><span className="text-slate-400">Zero-Fee 30-Day Returns</span></li>
              <li><span className="text-slate-400">GDPR Privacy & Encrypted Biometrics</span></li>
            </ul>
          </div>

          <div className="space-y-2">
            <div className="font-bold text-white uppercase tracking-wider text-[11px]">For Partners</div>
            <p className="text-slate-400 text-xs">
              Connect your fashion catalog to reduce sizing returns by up to 71%.
            </p>
            <Link
              to="/b2b"
              className="inline-block mt-2 px-4 py-2 rounded-xl bg-[#B8935A] text-slate-950 font-bold text-xs"
            >
              Open Brand Partner Portal →
            </Link>
          </div>
        </div>

        <div className="max-w-7xl mx-auto pt-8 mt-8 border-t border-slate-800 flex flex-col sm:flex-row justify-between items-center gap-4 text-[11px] text-slate-500">
          <div>© {new Date().getFullYear()} CONFIT Fashion Technology Inc. All rights reserved.</div>
          <div className="flex gap-4">
            <Link to="/profile" className="hover:text-slate-400">Privacy Policy</Link>
            <Link to="/profile" className="hover:text-slate-400">Terms of Service</Link>
            <Link to="/profile" className="hover:text-slate-400">GDPR Compliance</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
