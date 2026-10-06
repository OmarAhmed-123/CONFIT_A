import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { ArrowLeft, Compass, Home } from 'lucide-react';

import { usePrefersReducedMotion } from '../../components/common/InteractionPrimitives';
import { ConfitLogo } from '../../components/common/ConfitLogo';

/**
 * Honest 404 (audit 2026-10-06).
 *
 * Before this page the catch-all route silently redirected every unknown
 * URL to the home page — a shopper following a broken or mistyped link was
 * never told anything was wrong, which is a quiet lie. Now the dead end is
 * NAMED, the attempted path is shown, and every way out is a real link.
 *
 * Role-safe by construction: the quick links (home, discover, back) are
 * public surfaces — no permission-gated link is ever rendered here
 * (spec 13 rule), so the same page is correct for shopper, partner and
 * admin sessions alike.
 *
 * Motion: a slow editorial float on the glyph + one entrance tween —
 * both fully disabled under prefers-reduced-motion; the page's meaning
 * lives entirely in its text.
 */
export const NotFoundView: React.FC = () => {
  const { t } = useTranslation();
  const reduce = usePrefersReducedMotion();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#FAF9F6] px-4 py-14">
      <motion.section
        initial={reduce ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduce ? 0 : 0.35, ease: 'easeOut' }}
        className="w-full max-w-lg text-center"
      >
        <div className="mx-auto mb-8 flex justify-center">
          <ConfitLogo variant="compact" theme="dark" size="sm" />
        </div>

        {/* The glyph is decorative; the words carry the meaning. */}
        <motion.div
          aria-hidden="true"
          animate={reduce ? undefined : { y: [0, -8, 0] }}
          transition={
            reduce ? undefined : { duration: 5, repeat: Infinity, ease: 'easeInOut' }
          }
          className="relative mx-auto mb-6 flex h-28 w-28 items-center justify-center"
        >
          <span className="absolute inset-0 rounded-[2rem] bg-gradient-to-br from-[#FDF8EE] to-[#F3EBDD] shadow-sm" />
          <span className="relative font-serif text-4xl font-bold tracking-tight text-[#1B1F3B]">
            404
          </span>
        </motion.div>

        <h1 className="font-serif text-2xl font-bold text-[#1B1F3B]">
          {t('not_found.title')}
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-slate-600">
          {t('not_found.detail')}
        </p>
        {/* The path that failed — shown LTR always; URLs are not prose. */}
        <p className="mt-2 text-xs text-slate-400" dir="ltr">
          <code className="rounded bg-slate-100 px-2 py-0.5">{location.pathname}</code>
        </p>

        <div className="mx-auto mt-8 flex max-w-sm flex-col gap-3 sm:flex-row sm:justify-center">
          <Link
            to="/"
            className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-[#1B1F3B] px-5 text-sm font-bold text-white hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            <span aria-hidden="true"><Home size={16} /></span>
            {t('not_found.home_cta')}
          </Link>
          <Link
            to="/discover"
            className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-5 text-sm font-bold text-[#1B1F3B] hover:border-[#A37E44] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            <span aria-hidden="true"><Compass size={16} /></span>
            {t('not_found.discover_cta')}
          </Link>
        </div>

        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mx-auto mt-5 inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-4 text-xs font-bold text-slate-500 hover:text-[#1B1F3B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
        >
          <span aria-hidden="true" className="rtl:rotate-180"><ArrowLeft size={14} /></span>
          {t('not_found.back_cta')}
        </button>
      </motion.section>
    </main>
  );
};
