import React, { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { toPng } from 'html-to-image';
import { publicLookService } from '../../services/apiServices';
import { ShareCard, ShareCardItem } from '../../components/outfit/ShareCard';

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
 * states honestly and never exposes owner data (the DTO carries none).
 * C7 — "Download PNG" rasterizes the actual rendered ShareCard via
 * html-to-image; no fabricated server card URL exists anywhere.
 */
export const SharedLookView: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const [look, setLook] = useState<PublicLook | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [exporting, setExporting] = useState(false);
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
    try {
      const dataUrl = await toPng(cardRef.current, { pixelRatio: 2, cacheBust: true });
      const link = document.createElement('a');
      link.download = `confit-look-${token}.png`;
      link.href = dataUrl;
      link.click();
    } catch {
      // Rendering failure (e.g. cross-origin image taint) — surface honestly.
      alert('Sorry, the image could not be generated. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  if (state === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50" role="status">
        <p className="text-slate-500">Loading shared look…</p>
      </div>
    );
  }

  if (state === 'not_found') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 gap-4">
        <h1 className="text-2xl font-serif text-[#1B1F3B]">This look is no longer available</h1>
        <p className="text-slate-500">The share link is invalid or has expired.</p>
        <Link to="/" className="text-[#1B1F3B] underline">Back to CONFIT</Link>
      </div>
    );
  }

  if (state === 'error' || !look) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 gap-4">
        <h1 className="text-2xl font-serif text-[#1B1F3B]">Something went wrong</h1>
        <p className="text-slate-500">We could not load this shared look. Please try again later.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 py-12 px-4 flex flex-col items-center gap-6">
      <ShareCard
        ref={cardRef}
        title={look.title}
        occasion={look.occasion}
        items={look.items}
        totalPrice={look.total_price}
        compatibilityScore={look.compatibility_score}
      />
      <button
        onClick={downloadPng}
        disabled={exporting}
        className="px-6 py-3 rounded-full bg-[#1B1F3B] text-white text-sm tracking-wide hover:opacity-90 disabled:opacity-50"
      >
        {exporting ? 'Generating…' : 'Download PNG'}
      </button>
      <Link to="/" className="text-slate-500 text-sm underline">
        Create your own look on CONFIT
      </Link>
    </div>
  );
};
