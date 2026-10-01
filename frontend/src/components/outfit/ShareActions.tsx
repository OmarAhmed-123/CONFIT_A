import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Check, Share2, AlertTriangle } from 'lucide-react';

/**
 * ShareActions — the ONE copy-link / native-share affordance (spec 06).
 *
 * Used wherever a look already HAS a live public URL: the owner's share
 * panel on /my-looks and the public /looks/:token page. It is rendered only
 * after the server has minted the token (§6.3 "انسخ URL بعد نجاح generation")
 * — this component never builds or guesses a token; it receives the final
 * URL. A look without a live link simply never mounts it, which is how
 * "private look blocked" stays a server-owned fact rather than a UI promise.
 *
 * State contract (§5): idle → copying → copied (timed, re-copyable)
 *                      denied       — clipboard permission refused
 *                      unsupported  — no clipboard API in this browser
 * Every state is announced as TEXT inside one `aria-live="polite"` region;
 * colour and iconography are reinforcement, never the only signal (§7).
 *
 * Native share (§6.5): the button renders only when `navigator.share`
 * exists. A user cancelling the OS sheet (AbortError) returns silently to
 * idle — cancellation is not a failure and must not scream "error". A real
 * share failure falls back to the clipboard path, and the live region then
 * tells the truth about WHAT happened ("link copied instead").
 */

export type ShareStatus =
  | 'idle'
  | 'copying'
  | 'copied'
  | 'denied'
  | 'unsupported'
  | 'shared_fallback';

const COPIED_RESET_MS = 2500;

export const ShareActions: React.FC<{
  /** Absolute public URL — already minted by the server. */
  url: string;
  /** Share-sheet title (the look's title; never owner identity). */
  title: string;
  /** Compact = inline row (share panel); default = stacked (public page). */
  compact?: boolean;
}> = ({ url, title, compact = false }) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<ShareStatus>('idle');
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (resetTimer.current) clearTimeout(resetTimer.current);
  }, []);

  const settle = useCallback((next: ShareStatus, revert: boolean) => {
    setStatus(next);
    if (resetTimer.current) clearTimeout(resetTimer.current);
    if (revert) {
      resetTimer.current = setTimeout(() => setStatus('idle'), COPIED_RESET_MS);
    }
  }, []);

  const copy = useCallback(async (): Promise<boolean> => {
    setStatus('copying');
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(url);
        settle('copied', true);
        return true;
      } catch {
        // Permission refused (or transient failure): the honest state is
        // "denied", with the URL still visible for manual selection — never
        // a silent revert that leaves the user guessing (§5 denied).
        settle('denied', false);
        return false;
      }
    }
    // No async clipboard at all (old/locked-down browser): say so and leave
    // the visible URL as the manual path (§2 fallback).
    settle('unsupported', false);
    return false;
  }, [url, settle]);

  const nativeShare = useCallback(async () => {
    try {
      await navigator.share({ title, url });
      // The OS sheet handled it; nothing to announce — the user SAW the
      // share happen. Returning to idle keeps the region quiet and honest.
      setStatus('idle');
    } catch (err: unknown) {
      if ((err as { name?: string })?.name === 'AbortError') {
        // User closed the sheet. A cancellation is not an error.
        setStatus('idle');
        return;
      }
      // Real failure → clipboard fallback, and the announcement explains
      // the substitution instead of claiming the share succeeded.
      const copiedInstead = await copy();
      if (copiedInstead) settle('shared_fallback', true);
    }
  }, [title, url, copy, settle]);

  const canNativeShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';

  const statusText: Record<Exclude<ShareStatus, 'idle'>, string> = {
    copying: t('share.copying'),
    copied: t('share.copied'),
    denied: t('share.copy_denied'),
    unsupported: t('share.copy_unsupported'),
    shared_fallback: t('share.shared_fallback'),
  };

  const btnBase =
    'inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] disabled:opacity-50';

  return (
    <div className={compact ? 'space-y-1.5' : 'space-y-2'}>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void copy()}
          disabled={status === 'copying'}
          className={`${btnBase} flex-1 ${
            status === 'copied'
              ? 'border border-emerald-300 bg-emerald-50 text-emerald-800'
              : 'border border-slate-300 text-slate-700 hover:bg-slate-100'
          }`}
        >
          <span aria-hidden="true">
            {status === 'copied' ? <Check size={14} /> : <Copy size={14} />}
          </span>
          {/* The label itself states the outcome — not colour alone (§7). */}
          <span>{status === 'copied' ? t('share.copied') : t('share.copy_link')}</span>
        </button>

        {canNativeShare && (
          <button
            type="button"
            onClick={() => void nativeShare()}
            className={`${btnBase} flex-1 bg-[#1B1F3B] text-white hover:bg-[#0C0E1E]`}
          >
            <span aria-hidden="true"><Share2 size={14} /></span>
            <span>{t('share.native_share')}</span>
          </button>
        )}
      </div>

      {/* ONE polite live region for every state transition. Rendered even
          when idle so the region exists BEFORE the first announcement —
          regions created together with their first message are routinely
          missed by screen readers. */}
      <p role="status" aria-live="polite" aria-atomic="true" className="min-h-4 text-[11px]">
        {status !== 'idle' && (
          <span
            className={
              status === 'denied' || status === 'unsupported'
                ? 'inline-flex items-center gap-1 text-rose-700'
                : 'inline-flex items-center gap-1 text-emerald-700'
            }
          >
            {(status === 'denied' || status === 'unsupported') && (
              <span aria-hidden="true"><AlertTriangle size={12} /></span>
            )}
            {statusText[status]}
          </span>
        )}
      </p>
    </div>
  );
};
