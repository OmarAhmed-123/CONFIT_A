import React from 'react';
import { Outlet, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BrandNavbar } from '../components/navigation/BrandNavbar';
import { useUIStore } from '../stores/uiStore';

export const BrandLayout: React.FC = () => {
  const { t } = useTranslation();
  // AUTH-02 FIX: Toast is mounted at the App root so toasts fired on /b2b
  // and /admin (gate actions, brand CRUD) render identically. The local
  // Toast here previously double-rendered with the global one.
  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <BrandNavbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        <Outlet />
      </main>

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
