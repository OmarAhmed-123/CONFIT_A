/**
 * Which text a shopper reads, when the catalogue carries two languages.
 *
 * THE DEFECT THIS CLOSES (measured 2026-10-20, Arabic storefront)
 * ---------------------------------------------------------------
 * Every one of the 12 products in production has a populated `title_ar` — the
 * column is NOT empty, and the API ships it. The product page, though, set the
 * *document* title from `title_ar` and rendered the visible `<h1>` from
 * `title`:
 *
 *     setRouteTitleOverride((lang === "ar" && product.title_ar) || product.title)
 *     <h1>{product.title}</h1>          // English, on an RTL Arabic page
 *
 * So the browser tab read Arabic while the page heading read English, and the
 * product cards were English in both locales. The data was right; the render
 * was not.
 *
 * THE RULE
 * --------
 * Prefer the language the interface is actually in; fall back to the other
 * language only when the preferred field is genuinely missing or blank.
 *
 * A blank string is treated as missing on purpose: a row whose `title_ar` is
 * `""` or whitespace would otherwise render an invisible heading, which is
 * worse than an honest English fallback. This function never invents a title —
 * if both are absent the caller's `primary` comes back unchanged.
 */

export interface Bilingual {
  title?: string | null;
  title_ar?: string | null;
}

const usable = (value?: string | null): value is string =>
  typeof value === "string" && value.trim().length > 0;

export function localizedTitle(
  item: Bilingual | null | undefined,
  language: string | undefined,
): string {
  if (!item) return "";
  const isArabic = (language ?? "").toLowerCase().startsWith("ar");
  const primary = isArabic ? item.title_ar : item.title;
  const secondary = isArabic ? item.title : item.title_ar;
  if (usable(primary)) return primary;
  if (usable(secondary)) return secondary;
  return "";
}

/** Same rule for the long-form fields, so a page never mixes languages. */
export interface BilingualBody {
  description?: string | null;
  description_ar?: string | null;
}

export function localizedDescription(
  item: BilingualBody | null | undefined,
  language: string | undefined,
): string {
  if (!item) return "";
  const isArabic = (language ?? "").toLowerCase().startsWith("ar");
  const primary = isArabic ? item.description_ar : item.description;
  const secondary = isArabic ? item.description : item.description_ar;
  if (usable(primary)) return primary;
  if (usable(secondary)) return secondary;
  return "";
}
