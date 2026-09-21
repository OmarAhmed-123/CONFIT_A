/**
 * Money display helper — the frontend must never hardcode a currency symbol.
 *
 * The backend is the single authority for WHICH currency an amount is
 * denominated in: the cart, order and checkout responses carry a `currency`
 * field resolved from the shopper's market (EG -> EGP, AE -> AED, …). Before
 * this module existed, several commerce surfaces rendered a literal "$", so an
 * EGP order displayed "$3,000.00" — a fabricated currency label.
 *
 * Every money value the commerce UI shows must go through `formatMoney` with
 * the currency the response actually declared (intl-formatting, RTL-safe).
 */

const SYMBOL_PREFIX: Record<string, string> = {
  USD: '$',
};

export function formatMoney(amount: number, currency?: string | null): string {
  const code = (currency || 'USD').toUpperCase();
  const safe = Number.isFinite(amount) ? amount : 0;
  let formatted: string;
  try {
    // `undefined` locale -> the user's browser locale, so Arabic viewers get
    // Arabic numerals/separators while the currency stays unambiguous.
    formatted = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(safe);
  } catch {
    formatted = safe.toFixed(2);
  }
  const prefix = SYMBOL_PREFIX[code];
  if (prefix) return `${prefix}${formatted}`;
  // Non-symbol currencies render the ISO code after the amount (e.g.
  // "1,234.50 EGP"), the convention shoppers in those markets expect.
  return `${formatted} ${code}`;
}
