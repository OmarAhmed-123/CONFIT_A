import React from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/uiStore';
import { SUPPORTED_LANGUAGES, type AppLanguage } from '../../i18n/i18n';
import { languageDisplayName, formatNumber } from '../../i18n/format';

/**
 * LanguageSwitcher — a labelled two-option segmented control.
 *
 * Audit 2026-09-21 (finding: "لم يتحقق الفحص من … هل يعمل كل زر دون mouse"):
 * the previous control was a single unlabelled mystery toggle whose
 * `aria-label` was the hard-coded English string "Switch Language" — so a
 * screen-reader user in Arabic heard an English label on the one control that
 * changes the language, and nothing told them which language was currently
 * active. It also wrote the store directly, bypassing the document
 * `lang`/`dir` application in some paths.
 *
 * WHAT CHANGED
 *   - One button per supported language inside a labelled group, each with
 *     `aria-pressed` — the active language is now a STATE a screen reader can
 *     read, not something you infer from the glyph order.
 *   - Each label carries its own `lang` attribute: "عربي" is announced in
 *     Arabic even while the document is English, so it is not read out
 *     letter-by-letter with English phonetics.
 *   - The label is a real translation key, translated in both locales.
 *   - Changing language writes through `useUIStore.setLanguage`, which routes
 *     to `setAppLanguage` — the single place that updates `<html lang>`,
 *     `<html dir>`, the Arabic typeface class and localStorage, so direction
 *     can never disagree with the active bundle.
 *   - The change is announced through a polite live region (the visible text
 *     of the page all changes at once; a keyboard user needs to be told).
 */
export const LanguageSwitcher: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { t } = useTranslation();
  const { language, setLanguage } = useUIStore();
  const [announcement, setAnnouncement] = React.useState('');

  const select = (next: AppLanguage) => {
    if (next === language) return;
    setLanguage(next);
    setAnnouncement(t('a11y.language_switched', { language: languageDisplayName(next, language) }));
  };

  return (
    <div className={className}>
      <div
        role="group"
        aria-label={t('a11y.language_switcher')}
        className="inline-flex items-center gap-0.5 p-0.5 rounded-full border border-slate-200 bg-white"
      >
        {SUPPORTED_LANGUAGES.map((code) => {
          const isActive = language === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => select(code)}
              aria-pressed={isActive}
              lang={code}
              className={`px-2.5 py-1 text-[11px] font-semibold rounded-full transition-all ${
                isActive
                  ? 'bg-[#1B1F3B] text-white shadow-2xs'
                  : 'text-slate-600 hover:bg-[#FDF8EE] hover:text-[#7A5C28]'
              }`}
            >
              {languageDisplayName(code)}
            </button>
          );
        })}
      </div>

      {/* Polite live region: the whole page re-renders in the new language, so
          the change itself must be announced — otherwise a keyboard or screen
          reader user receives a silent, total content swap. */}
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
    </div>
  );
};

/**
 * Compact numeric badge variant used inside the mobile menu, kept separate so
 * callers pick an explicit presentation instead of passing layout props that
 * silently change the accessible name.
 */
export const LanguageSwitcherCompact: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { language } = useUIStore();
  const { t } = useTranslation();
  return (
    <span className={`text-[10px] font-bold uppercase tracking-wider text-slate-400 ${className}`}>
      {t('a11y.language_current', {
        language: languageDisplayName(language),
        position: formatNumber(SUPPORTED_LANGUAGES.indexOf(language) + 1, language),
      })}
    </span>
  );
};
