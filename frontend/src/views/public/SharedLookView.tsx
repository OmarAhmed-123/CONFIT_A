import React, { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { toPng } from 'html-to-image';
import { publicLookService } from '../../services/apiServices';
import { ShareCard, ShareCardItem } from '../../components/outfit/ShareCard';
import { ShareActions } from '../../components/outfit/ShareActions';
import { ConfitLogo } from '../../components/common/ConfitLogo';
import { usePrefersReducedMotion } from '../../components/common/InteractionPrimitives';

interface PublicLook {
  title: string;
  occasion: string;
  description?: string | null;
  total_price: number;
  compatibility_score: number;
  items: ShareCardItem[];
  created_at: string;
}

type LoadState = 'loading' | 'ready' | 'not_found' | 'error';

/**
 * C8 — public, unauthenticated shared-look page in Logo #3 white-first identity.
 * Fetches the real GET /public/looks/:token endpoint; renders loading / not-found / error
 * states honestly and never exposes owner data.
 */
export const SharedLookView: React.FC = () => {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const [look, setLook] = useState<PublicLook | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const reduceMotion = usePrefersReducedMotion();

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setState('not_found');
      return;
    }
    publicLookService
      .getPublicLook(token)
      .then((data) => {
        if (cancelled) return;
        setLook(data);
        setState('ready');
      })
      .catch((err: any) => {
        if (cancelled) return;
        setState(err?.status === 404 ? 'not_found' : 'error');
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const downloadPng = async () => {
    if (!cardRef.current || exporting) return;
    setExporting(true);
    setExportError(false);
    try {
      const dataUrl = await toPng(cardRef.current, { pixelRatio: 2, cacheBust: true });
      const link = document.createElement('a');
      link.download = `confit-look-${token}.png`;
      link.href = dataUrl;
      link.click();
    } catch {
      setExportError(true);
    } finally {
      setExporting(false);
    }
  };

  /** Entrance-only motion, disabled entirely under prefers-reduced-motion. */
  const enter = (delay = 0) =>
    reduceMotion
      ? {}
      : {
          initial: { opacity: 0, y: 14 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.4, delay, ease: 'easeOut' as const },
        };

  /** Shared page chrome: white field + CONFIT masthead. */
  const Shell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <main className="min-h-screen bg-white flex flex-col">
      <header className="w-full border-b border-brand-hairline bg-white/95">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link
            to="/"
            aria-label={t('shared_look.masthead_home')}
            className="inline-flex min-h-11 items-center rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
          >
            <ConfitLogo variant="full" theme="dark" size="sm" />
          </Link>
          <span className="text-[10px] font-bold uppercase tracking-[0.25em] text-brand-muted">
            {t('shared_look.masthead_tag')}
          </span>
        </div>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-10">{children}</div>
    </main>
  );

  if (state === 'loading') {
    return (
      <Shell>
        <div role="status" aria-live="polite" className="flex flex-col items-center gap-4">
          <span
            aria-hidden="true"
            className="inline-block h-6 w-6 rounded-full border-2 border-brand-hairline border-t-brand-charcoal motion-safe:animate-spin"
          />
          <p className="text-brand-muted text-sm tracking-wide">{t('shared_look.loading')}</p>
        </div>
      </Shell>
    );
  }

  if (state === 'not_found') {
    return (
      <Shell>
        <motion.div {...enter()} className="flex flex-col items-center gap-5 text-center max-w-md">
          <h1 className="text-3xl font-serif text-brand-charcoal">{t('shared_look.unavailable_title')}</h1>
          <div aria-hidden="true" className="h-px w-16 bg-brand-charcoal" />
          <p className="text-brand-muted leading-relaxed">{t('shared_look.unavailable_body')}</p>
          <Link
            to="/"
            className="inline-flex min-h-11 items-center px-6 rounded-full bg-brand-charcoal text-white text-sm tracking-wide hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
          >
            {t('shared_look.back_home')}
          </Link>
        </motion.div>
      </Shell>
    );
  }

  if (state === 'error' || !look) {
    return (
      <Shell>
        <motion.div {...enter()} className="flex flex-col items-center gap-5 text-center max-w-md">
          <h1 className="text-3xl font-serif text-brand-charcoal">{t('shared_look.error_title')}</h1>
          <div aria-hidden="true" className="h-px w-16 bg-brand-charcoal" />
          <p className="text-brand-muted leading-relaxed">{t('shared_look.error_body')}</p>
        </motion.div>
      </Shell>
    );
  }

  const currentUrl = typeof window !== 'undefined' ? window.location.href : '';

  return (
    <Shell>
      <div className="w-full flex flex-col items-center gap-6">
        <motion.div {...enter()} className="text-center max-w-md">
          <h1 className="text-xl sm:text-2xl font-serif text-brand-charcoal leading-tight tracking-wide">
            {t('shared_look.curated_line')}
          </h1>
          <div aria-hidden="true" className="h-px w-12 bg-brand-charcoal mx-auto mt-3" />
        </motion.div>

        <motion.div {...enter(0.08)}>
          <ShareCard
            ref={cardRef}
            title={look.title}
            occasion={look.occasion}
            items={look.items}
            totalPrice={look.total_price}
            compatibilityScore={look.compatibility_score}
          />
        </motion.div>

        {/* Viewer re-share: copies/shares the CURRENT public URL only. */}
        <motion.div {...enter(0.16)} className="w-full max-w-sm">
          <ShareActions url={currentUrl} title={look.title} />
        </motion.div>

        <motion.div {...enter(0.24)} className="flex flex-col items-center gap-3">
          <button data-motion="download" data-motion-tone="icon"
            onClick={downloadPng}
            disabled={exporting}
            type="button"
            className="inline-flex min-h-11 items-center px-6 py-3 rounded-full bg-brand-charcoal text-white text-sm tracking-wide hover:bg-black disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
          >
            {exporting ? t('shared_look.generating') : t('shared_look.download_png')}
          </button>

          {/* Export status: text in a polite region; exists before first use. */}
          <p role="status" aria-live="polite" aria-atomic="true" className="min-h-4 text-xs text-rose-700">
            {exportError && t('shared_look.png_failed')}
          </p>

          <Link
            to="/"
            className="inline-flex min-h-11 items-center px-5 rounded-full border border-brand-field text-brand-charcoal text-sm tracking-wide hover:bg-brand-wash focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
          >
            {t('shared_look.create_your_own')}
          </Link>
        </motion.div>
      </div>
    </Shell>
  );
};
