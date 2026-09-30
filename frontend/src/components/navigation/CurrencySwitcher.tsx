import React from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useUIStore } from '../../stores/uiStore';
import {
  CURRENCY_CHANGED_EVENT,
  CURRENCY_LABELS,
  getPreferredCurrency,
  setPreferredCurrency,
  type CurrencyCatalog,
} from '../../lib/currency';
import { catalogService } from '../../services/apiServices';

/**
 * CurrencySwitcher — picks the presentation currency for the whole storefront.
 *
 * WHY IT IS BUILT THIS WAY
 * ------------------------
 * Measured on production 2026-09-30: the cart returned `"currency": "USD"`
 * while `/commerce/payment-methods` quoted EGP for the same Egyptian shopper.
 * The fix is server-side (one FX authority), so this control does NOT convert
 * anything. It stores a choice, the API client attaches it as `X-Currency`,
 * and the backend returns amounts already denominated in that currency.
 *
 * Three behaviours that stop this from being a decorative dropdown:
 *
 * 1. The option list comes from `GET /catalog/currencies`, so a currency the
 *    platform has no FX rate for is rendered DISABLED. Offering a currency we
 *    cannot convert into is how you ship a 48x pricing error.
 * 2. Changing it invalidates the react-query cache. A product list cached in
 *    EGP is wrong the instant the shopper picks SAR, and stale money is worse
 *    than a spinner.
 * 3. If the server reports it could not honour the choice (`honoured: false`),
 *    the control says so out loud instead of showing the old currency as if
 *    nothing happened.
 */
export const CurrencySwitcher: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { t } = useTranslation();
  const { language } = useUIStore();
  const queryClient = useQueryClient();
  const [selected, setSelected] = React.useState<string | null>(() => getPreferredCurrency());
  const [announcement, setAnnouncement] = React.useState('');

  const { data } = useQuery<CurrencyCatalog>({
    queryKey: ['catalog', 'currencies', selected],
    queryFn: () => catalogService.getCurrencies(),
    staleTime: 5 * 60 * 1000,
  });

  const active = data?.active;
  const options = React.useMemo(
    () => (data?.supported ?? []).filter((o) => o.available || o.currency === active?.currency),
    [data, active],
  );

  const onChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value || null;
    setSelected(next);
    setPreferredCurrency(next);
    // Every cached price is denominated in the PREVIOUS currency.
    queryClient.invalidateQueries();
    setAnnouncement(
      t('a11y.currency_switched', { currency: next ?? active?.pricing_currency ?? '' }),
    );
  };

  const label = (code: string) => {
    const names = CURRENCY_LABELS[code];
    const name = names ? (language === 'ar' ? names.ar : names.en) : code;
    return `${code} — ${name}`;
  };

  return (
    <div className={className}>
      <label className="sr-only" htmlFor="confit-currency-switcher">
        {t('a11y.currency_switcher')}
      </label>
      <select
        id="confit-currency-switcher"
        value={selected ?? ''}
        onChange={onChange}
        className="px-2.5 py-1 text-[11px] font-semibold rounded-full border border-slate-200 bg-white text-slate-700 hover:bg-[#FDF8EE] focus:outline-hidden focus:ring-2 focus:ring-[#7A5C28]"
      >
        <option value="">{t('a11y.currency_market_default')}</option>
        {options.map((option) => (
          <option key={option.currency} value={option.currency} disabled={!option.available}>
            {label(option.currency)}
          </option>
        ))}
      </select>

      {/* Honesty: the server is the authority on whether the switch took
          effect. If it refused, say so rather than leaving the shopper to
          discover it at checkout. */}
      {active && active.honoured === false ? (
        <p className="mt-1 text-[10px] text-amber-700">
          {t('a11y.currency_not_available', { currency: active.requested_currency ?? '', fallback: active.currency })}
        </p>
      ) : null}

      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
    </div>
  );
};

/**
 * Keeps non-react-query consumers honest: any part of the app that caches
 * money outside react-query can subscribe to the same event instead of
 * inventing its own signal.
 */
export function useCurrencyChange(handler: () => void): void {
  React.useEffect(() => {
    const listener = () => handler();
    window.addEventListener(CURRENCY_CHANGED_EVENT, listener);
    return () => window.removeEventListener(CURRENCY_CHANGED_EVENT, listener);
  }, [handler]);
}
