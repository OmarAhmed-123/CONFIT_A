import React from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

/**
 * Consistent, keyboard-accessible back navigation for every partner/admin page.
 *
 * A direct visit has no useful in-app history entry, so it falls back to the
 * caller's own portal home instead of navigating out of CONFIT. React Router
 * marks an initial entry with location.key === "default".
 */
export const PortalBackButton: React.FC = () => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();
  const isAdmin = user?.role?.toLowerCase() === 'admin';

  const goBack = () => {
    if (location.key && location.key !== 'default') {
      navigate(-1);
      return;
    }
    navigate(isAdmin ? '/admin' : '/b2b', { replace: true });
  };

  return (
    <button
      type="button"
      onClick={goBack}
      aria-label={t('portal_back.aria_label')}
      className="mb-5 inline-flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-[#B8935A] hover:text-[#8A6A2F] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A] focus-visible:ring-offset-2"
    >
      <span aria-hidden="true" className="text-lg leading-none">
        {i18n.dir() === 'rtl' ? '→' : '←'}
      </span>
      {t('portal_back.label')}
    </button>
  );
};
