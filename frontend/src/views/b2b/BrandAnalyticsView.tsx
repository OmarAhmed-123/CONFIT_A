import { useTranslation } from 'react-i18next';
import React from 'react';
const percent = (value: number | null) => value == null ? 'Not enough data' : `${value}%`;
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';

export const BrandAnalyticsView: React.FC = () => {
  const { t } = useTranslation();
  const { analytics, conversionPerSku, fetchErrors, isLoading, refresh } = useBrandViewModel();

  if (isLoading) {
    return <LoadingSpinner text="Computing funnel telemetry and conversion rates..." />;
  }

  if (!analytics) {
    // A failed fetch must never look like "no data yet" — show an explicit,
    // actionable error (the C6 no-silent-failure rule extended to B2B).
    return (
      <EmptyState
        title="Telemetry unavailable"
        description={fetchErrors.analytics || 'The analytics service could not be reached. Your data is intact — retry when the service is back.'}
        actionText="Retry"
        onAction={refresh}
      />
    );
  }

  // P1 FIX — "3500% conversion". The old code coerced a zero denominator to 1
  // (`analytics.total_views || 1`), so 35 try-ons against 0 views rendered as
  // "3500%". A ratio with an empty denominator is undefined, not enormous:
  // dividing by a substituted 1 fabricates a statistic. When there are no
  // views we now say so instead of printing a number that cannot be true.
  const views = analytics.total_views;
  const ratioOfViews = (count: number): string => {
    if (!views) return 'N/A (no views)';
    // Still capped-checked: these are different measurement units (a current
    // cart line is not a lifetime view), so >100% is possible and is labelled
    // rather than hidden.
    const pct = (count / views) * 100;
    return `${pct.toFixed(1)}%${pct > 100 ? ' — exceeds views, different units' : ''}`;
  };

  const funnelSteps = [
    { label: '1. Catalog product views', count: analytics.total_views, pct: views ? '100% (baseline)' : 'N/A (no views)', source: 'RecentlyViewed' },
    { label: '2. Try-on sessions (all states)', count: analytics.total_tryons, pct: ratioOfViews(analytics.total_tryons), source: 'TryOnSession' },
    { label: '3. Current shopping-bag lines', count: analytics.total_add_to_carts, pct: ratioOfViews(analytics.total_add_to_carts), source: 'CartItem' },
    { label: '4. Eligible order lines', count: analytics.total_purchases, pct: views ? `${analytics.funnel_conversion_rate}%` : 'N/A (no views)', source: 'OrderItem' },
  ];

  // Bars must encode the data, not a decorative staircase. The previous
  // `100 - idx*25` made an empty funnel look like a healthy one.
  const maxCount = Math.max(1, ...funnelSteps.map((s) => s.count));

  return (
    <div className="space-y-8 pb-20">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
          Conversion Funnel & Return Telemetry
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          {analytics.methodology}
        </p>
      </div>

      {/* Funnel Visualization - REAL DATA */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">
          Commerce activity snapshot — not a linked-session funnel
        </h3>
        <p className="text-[11px] text-slate-500">Ratios mix different measurement units and may exceed 100%. A current cart line is not a lifetime add-to-cart event. Order lines exclude cancelled, refunded and failed orders.</p>

        <div className="space-y-4">
          {funnelSteps.map((step, idx) => (
            <div key={step.label} className="space-y-1.5">
              <div className="flex justify-between text-xs font-bold text-slate-700">
                <span>{step.label} <span className="text-[10px] text-slate-400 font-normal">({step.source})</span></span>
                <span className="font-mono text-sm text-[#1B1F3B]">{step.count.toLocaleString()} ({step.pct})</span>
              </div>
              <div className="w-full h-4 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-[#1B1F3B] to-[#B8935A]"
                  style={{ width: `${step.count === 0 ? 0 : Math.max(2, (step.count / maxCount) * 100)}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>

        {analytics.total_views === 0 && (
          <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-xs text-amber-800">
            No funnel data yet. Views tracked via RecentlyViewed when users view your products. Try-Ons via TryOnSession. Add-to-Cart via CartItem. Purchases via OrderItem.
          </div>
        )}
      </div>

      {/* Per-product Conversion — an error is surfaced, not laundered into "no rows" */}
      {fetchErrors.conversion && (
        <div role="alert" className="p-4 rounded-2xl bg-rose-50 border border-rose-200">
          <p className="text-[11px] font-bold text-rose-800">{t('b2b.sku_conversion_failed')}</p>
          <p className="text-[11px] text-rose-600 mt-1">{fetchErrors.conversion}</p>
          <button onClick={refresh} className="mt-2 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50">Retry</button>
        </div>
      )}
      {conversionPerSku.length > 0 && (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('b2b.sku_conversion_title')}</h3>
          <p className="text-[11px] text-slate-500">Funnel per SKU: views → tryons → add-to-cart → purchases, sorted by conversion rate DESC</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400 uppercase text-[10px]">
                  <th className="py-2">Product</th>
                  <th className="py-2">Views</th>
                  <th className="py-2">Try-Ons</th>
                  <th className="py-2">Add-to-Cart</th>
                  <th className="py-2">Purchases</th>
                  <th className="py-2">Conv %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {conversionPerSku.slice(0, 10).map((row) => (
                  <tr key={row.product_id} className="hover:bg-slate-50">
                    <td className="py-2 font-bold truncate max-w-[150px]">{row.title}</td>
                    <td className="py-2">{row.views}</td>
                    <td className="py-2">{row.tryons}</td>
                    <td className="py-2">{row.add_to_cart}</td>
                    <td className="py-2 font-bold text-emerald-600">{row.purchases}</td>
                    <td className="py-2 font-mono font-bold">
                      {row.conversion_rate == null
                        ? <span className="text-slate-400 font-normal" title="No views recorded for this product — the ratio has no denominator.">N/A</span>
                        : `${row.conversion_rate}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Return Rate Benchmark Card - REAL */}
      <div className="bg-[#FAF9F6] rounded-3xl border border-slate-200 p-6 sm:p-8 space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
          Observed return-marked line comparison
        </h3>
        <div className="grid grid-cols-2 gap-4 text-xs">
          <div className="p-3 rounded-xl bg-white border">
            <span className="text-slate-400 text-[10px] block uppercase">Non-Try-On cohort</span>
            <span className="font-mono text-lg font-bold text-rose-600">{percent(analytics.return_rate_before_vton)}</span>
            <span className="text-[11px] text-slate-500 block">Observed non-try-on order lines; no benchmark fallback</span>
          </div>
          <div className="p-3 rounded-xl bg-white border">
            <span className="text-slate-400 text-[10px] block uppercase">{t('b2b.tryon_assisted_cohort')}</span>
            <span className="font-mono text-lg font-bold text-emerald-600">{percent(analytics.return_rate_after_vton)}</span>
            <span className="text-[11px] text-slate-500 block">Try-on assisted orders</span>
          </div>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">
          Return reduction <strong>{percent(analytics.return_reduction_percentage)}</strong> {analytics.return_cohorts?.methodology}
        </p>
        <div className="text-[11px] text-slate-500 p-2 bg-white rounded border">
          <span className="font-bold">BOPIS Fulfillment:</span> {percent(analytics.bopis_store_fulfillment_rate)} of eligible pickup groups completed. Ad Spend: ${analytics.ad_spend_total}, Ad Revenue: ${analytics.ad_revenue_total} from recorded placement counters; not verified billing.
        </div>
      </div>
    </div>
  );
};
