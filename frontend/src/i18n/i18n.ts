import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import enTranslations from './en.json';
import arTranslations from './ar.json';
import { humanizeKey } from './messages';

export type AppLanguage = 'en' | 'ar';

export const SUPPORTED_LANGUAGES: readonly AppLanguage[] = ['en', 'ar'] as const;
export const LANGUAGE_STORAGE_KEY = 'confit_lang';
export const RTL_LANGUAGES: readonly AppLanguage[] = ['ar'] as const;

export function isSupportedLanguage(value: unknown): value is AppLanguage {
  return typeof value === 'string' && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

export function directionFor(lang: AppLanguage): 'rtl' | 'ltr' {
  return RTL_LANGUAGES.includes(lang) ? 'rtl' : 'ltr';
}

/**
 * Missing-key telemetry.
 *
 * Audit 2026-09-21 finding: "لم يتحقق الفحص من … عمل كل زر دون mouse" and,
 * more damaging for language, the previous `parseMissingKeyHandler` silently
 * humanized a missing key. A missing Arabic string therefore shipped as
 * English text and NOTHING recorded that it happened — the audit's exact
 * complaint that "HTTP 200 للمسار لا يثبت أن … العربية ترجمة متكافئة".
 *
 * A falling-back key is now an explicit, enumerable event:
 *   - always recorded in `missingTranslations` (read by tests and by the dev
 *     overlay), so a regression is visible in CI, not only in a console;
 *   - warned loudly in development.
 */
const missingTranslations = new Map<string, number>();

export function recordMissingTranslation(key: string, language: string): void {
  const id = `${language}:${key}`;
  missingTranslations.set(id, (missingTranslations.get(id) ?? 0) + 1);
  if (import.meta.env?.DEV) {
    // eslint-disable-next-line no-console
    console.warn(`[i18n] missing key "${key}" for "${language}" — fell back to humanized text`);
  }
}

/** Test/reporting accessor. Returns a snapshot so callers cannot mutate state. */
export function getMissingTranslations(): Record<string, number> {
  return Object.fromEntries(missingTranslations);
}

export function clearMissingTranslations(): void {
  missingTranslations.clear();
}

function readSavedLanguage(): AppLanguage {
  try {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isSupportedLanguage(saved)) return saved;
  } catch {
    /* private mode / storage disabled — fall through to the default */
  }
  return 'en';
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: enTranslations },
      ar: { translation: arTranslations },
    },
    lng: readSavedLanguage(),
    supportedLngs: [...SUPPORTED_LANGUAGES],
    // `false` (not 'en'): falling back to English is the behaviour we still
    // want at runtime, but i18next's own fallback would bypass the handler
    // below and hide the gap. Handling the miss ourselves keeps it countable.
    fallbackLng: false,
    interpolation: {
      escapeValue: false,
    },
    returnEmptyString: false,
    // A missing translation must NEVER render as a raw dotted key such as
    // "nav.wardrobe" (the audit's exact finding), and it must NEVER be
    // silently swallowed either. Humanize for the user, record for the team.
    saveMissing: true,
    // Two hooks, and BOTH are required — this is the subtlety that made the
    // original implementation silently fall back to English:
    //   · missingKeyHandler       fires for its SIDE EFFECT; i18next discards
    //                             whatever it returns.
    //   · parseMissingKeyHandler  is the one whose return value is RENDERED.
    // Recording without humanizing leaves a raw key on screen, and humanizing
    // without recording hides the gap — the audit found exactly the latter.
    missingKeyHandler: (lngs, _ns, key) => {
      recordMissingTranslation(key, String(Array.isArray(lngs) ? lngs[0] : lngs));
    },
    parseMissingKeyHandler: (key) => {
      recordMissingTranslation(key, 'render');
      return humanizeKey(key);
    },
  });

/**
 * Apply a language to the document: i18next bundle, `<html lang>`, `<html
 * dir>`, the Arabic typeface class and persistence. This is the ONLY place
 * direction is written, so LTR/RTL can never disagree with the active bundle.
 */
export const setAppLanguage = async (lang: AppLanguage): Promise<void> => {
  if (!isSupportedLanguage(lang)) return;
  await i18n.changeLanguage(lang);
  applyDocumentLanguage(lang);
};

/** Synchronous DOM application — separated so it can run before React mounts. */
export function applyDocumentLanguage(lang: AppLanguage): void {
  const root = document.documentElement;
  const dir = directionFor(lang);
  root.setAttribute('dir', dir);
  root.setAttribute('lang', lang);
  root.setAttribute('data-dir', dir);
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
  } catch {
    /* storage disabled — the in-memory language still applies */
  }
  const body = document.body;
  if (!body) return;
  body.classList.toggle('font-arabic', lang === 'ar');
  // Exposed so CSS can branch on language without duplicating the check.
  body.setAttribute('data-lang', lang);
}

// Keep <html lang/dir> authoritative even when the language changes through a
// path that did not call setAppLanguage (e.g. i18next's own changeLanguage).
i18n.on('languageChanged', (lang) => {
  if (isSupportedLanguage(lang)) applyDocumentLanguage(lang);
});

// Initial sync — runs once at module load, before React renders.
applyDocumentLanguage((i18n.resolvedLanguage as AppLanguage) ?? 'en');

export default i18n;
