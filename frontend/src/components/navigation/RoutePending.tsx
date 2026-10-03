import React from 'react';
import { useTranslation } from 'react-i18next';

/**
 * RoutePending — the pending-navigation state for a lazy route chunk
 * (spec "Magic Navigation" §5).
 *
 * Contract:
 *  · TEXT IS THE STATE (§7): a visible, translated sentence inside a
 *    `role="status"` / `aria-live="polite"` region. A screen-reader user
 *    hears that the section is loading; a sighted user reads it. The
 *    spinner is decoration (`aria-hidden`), and under
 *    `prefers-reduced-motion` it simply doesn't spin (`motion-safe:`) —
 *    the text keeps carrying the full meaning.
 *  · NO LAYOUT JUMP: min-height reserves real estate so the arriving view
 *    doesn't shove the page around.
 *  · NO false claims: this renders only while the import() is actually
 *    in flight; a chunk load FAILURE surfaces through the router's error
 *    boundary rather than being swallowed here.
 */
export const RoutePending: React.FC = () => {
  const { t } = useTranslation();
  return (
    <div className="min-h-[40vh] flex items-center justify-center p-8">
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-3 text-sm font-semibold text-slate-600"
      >
        <span
          aria-hidden="true"
          className="inline-block h-5 w-5 rounded-full border-2 border-[#C5A059]/40 border-t-[#C5A059] motion-safe:animate-spin"
        />
        <span>{t('nav.section_loading')}</span>
      </div>
    </div>
  );
};
