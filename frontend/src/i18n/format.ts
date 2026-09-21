/**
 * Locale-aware formatting.
 *
 * WHY THIS EXISTS (audit 2026-09-21, finding "RTL … contrast … labels" and the
 * un-measured i18n surface):
 *   Switching to Arabic translated the sentences but left every NUMBER, DATE
 *   and CURRENCY in the English/US convention — `1,234.50` and `09/21/2026`
 *   inside an RTL Arabic page. `toLocaleString()` without an explicit locale
 *   reads the *browser* locale, which is not the language the user picked in
 *   the app, so the two could disagree on the same screen.
 *
 * CONTRACT:
 *   - Every formatter takes the ACTIVE app language, never `undefined`.
 *   - Money is formatted from minor units with an explicit currency, so no
 *     caller can accidentally re-introduce a hand-built "$" + number string.
 *   - Arabic uses the Arabic-Indic digit set (ar-EG) because that is what
 *     Egyptian and Gulf readers expect for prices; `ar-EG` also gives the
 *     correct Arabic month names for dates.
 */
import type { AppLanguage } from './i18n';

/** Intl locale tag for each supported app language. */
export const INTL_LOCALE: Record<AppLanguage, string> = {
  en: 'en-US',
  // Egypt: Arabic-Indic digits + Arabic month names, the convention the
  // primary market (EG) and the GCC market both read natively.
  ar: 'ar-EG',
};

function intl(lang: AppLanguage | string | undefined): string {
  return INTL_LOCALE[(lang as AppLanguage) ?? 'en'] ?? INTL_LOCALE.en;
}

/** `1,234.5` / `١٬٢٣٤٫٥` */
export function formatNumber(value: number | null | undefined, lang: AppLanguage | string): string {
  if (value == null || !Number.isFinite(value)) return '';
  return new Intl.NumberFormat(intl(lang)).format(value);
}

/** `1,234.50` — for money amounts already expressed in major units. */
export function formatAmount(
  value: number | null | undefined,
  lang: AppLanguage | string,
  fractionDigits = 2,
): string {
  if (value == null || !Number.isFinite(value)) return '';
  return new Intl.NumberFormat(intl(lang), {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

/**
 * Money from minor units — mirrors the backend's decimal-money contract
 * (backend/app/core/money.py) so the UI cannot drift from the ledger.
 */
export function formatMoney(
  minorUnits: number | null | undefined,
  currency: string,
  lang: AppLanguage | string,
): string {
  if (minorUnits == null || !Number.isFinite(minorUnits)) return '';
  return new Intl.NumberFormat(intl(lang), {
    style: 'currency',
    currency: currency || 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(minorUnits / 100);
}

/** `21 September 2026` / `٢١ سبتمبر ٢٠٢٦` */
export function formatDate(
  value: Date | string | number | null | undefined,
  lang: AppLanguage | string,
  options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'long', day: 'numeric' },
): string {
  if (value == null) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(intl(lang), options).format(date);
}

/** `21 Sep 2026, 14:05` */
export function formatDateTime(value: Date | string | number | null | undefined, lang: AppLanguage | string): string {
  return formatDate(value, lang, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** `45%` / `٤٥٪` */
export function formatPercent(
  value: number | null | undefined,
  lang: AppLanguage | string,
  fractionDigits = 0,
): string {
  if (value == null || !Number.isFinite(value)) return '';
  // Accept both 0.45 and 45 — callers in this codebase pass whole percentages.
  const normalized = Math.abs(value) > 1 ? value / 100 : value;
  return new Intl.NumberFormat(intl(lang), {
    style: 'percent',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(normalized);
}

/** Relative "3 days ago" with a locale-aware unit string. */
export function formatRelativeDays(days: number, lang: AppLanguage | string): string {
  const rtf = new Intl.RelativeTimeFormat(intl(lang), { numeric: 'auto' });
  return rtf.format(days, 'day');
}

/**
 * Display name of the language itself, always written IN that language — an
 * Arabic speaker looking for Arabic should read "العربية", not "Arabic".
 */
export function languageDisplayName(lang: AppLanguage): string {
  return new Intl.DisplayNames([INTL_LOCALE[lang]], { type: 'language' }).of(INTL_LOCALE[lang]) ?? lang;
}
