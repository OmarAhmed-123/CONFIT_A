import React, { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toPng } from 'html-to-image';
import { publicLookService } from '../../services/apiServices';
import { ShareCard, ShareCardItem } from '../../components/outfit/ShareCard';
import { ShareActions } from '../../components/outfit/ShareActions';

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
 * C8 — public, unauthenticated shared-look page. Fetches the real
 * GET /public/looks/:token endpoint; renders loading / not-found / error
 * states honestly and never exposes owner data (the DTO carries none — no
 * email, no user id, nothing but the look itself; §8).
 *
 * Spec 06 updates:
 *  · every string moved to i18n (this page used to be hardcoded English —
 *    on the ARABIC storefront, the most-forwarded page in the product);
 *  · the viewer gets the same copy/native-share affordance as the owner,
 *    re-sharing the CURRENT public URL (no token is ever constructed here);
 *  · PNG failure is announced inline in a live region instead of `alert()`
 *    (alert steals focus and is unannounceable politely);
 *  · expired / revoked tokens stay a server verdict: 404 → "no longer
 *    available". The UI never guesses at liveness (§9).
 */
export const SharedLookView: React.FC = () => {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const [look, setLook] = useState<PublicLook | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

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
      // Rendering failure (e.g. cross-origin image taint) — surface honestly,
      // inline and announced; never a focus-stealing alert().
      setExportError(true);
    } finally {
      setExporting(false);
    }
  };

  if (state === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50" role="status" aria-live="polite">
        <p className="text-slate-500">{t('shared_look.loading')}</p>
      </div>
    );
  }

  if (state === 'not_found') {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-slate-50 gap-4 px-4 text-center">
        <h1 className="text-2xl font-serif text-[#1B1F3B]">{t('shared_look.unavailable_title')}</h1>
        <p className="text-slate-500">{t('shared_look.unavailable_body')}</p>
        <Link
          to="/"
          className="inline-flex min-h-11 items-center rounded-xl px-4 text-[#1B1F3B] underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
        >
          {t('shared_look.back_home')}
        </Link>
      </main>
    );
  }

  if (state === 'error' || !look) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-slate-50 gap-4 px-4 text-center">
        <h1 className="text-2xl font-serif text-[#1B1F3B]">{t('shared_look.error_title')}</h1>
        <p className="text-slate-500">{t('shared_look.error_body')}</p>
      </main>
    );
  }

  const currentUrl = typeof window !== 'undefined' ? window.location.href : '';

  return (
    <main className="min-h-screen bg-slate-100 py-12 px-4 flex flex-col items-center gap-6">
      <ShareCard
        ref={cardRef}
        title={look.title}
        occasion={look.occasion}
        items={look.items}
        totalPrice={look.total_price}
        compatibilityScore={look.compatibility_score}
      />

      {/* Viewer re-share: copies/shares the CURRENT public URL only. */}
      <div className="w-full max-w-sm">
        <ShareActions url={currentUrl} title={look.title} />
      </div>

      <button
        onClick={downloadPng}
        disabled={exporting}
        type="button"
        className="inline-flex min-h-11 items-center px-6 py-3 rounded-full bg-[#1B1F3B] text-white text-sm tracking-wide hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
      >
        {exporting ? t('shared_look.generating') : t('shared_look.download_png')}
      </button>

      {/* Export status: text in a polite region; exists before first use. */}
      <p role="status" aria-live="polite" aria-atomic="true" className="min-h-4 text-xs text-rose-700">
        {exportError && t('shared_look.png_failed')}
      </p>

      <Link
        to="/"
        className="inline-flex min-h-11 items-center text-slate-500 text-sm underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
      >
        {t('shared_look.create_your_own')}
      </Link>
    </main>
  );
};
