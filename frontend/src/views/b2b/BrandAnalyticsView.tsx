import { useTranslation } from 'react-i18next';
import React from 'react';
const percent = (value: number | null) => value == null ? 'Not enough data' : `${value}%`;
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';

export const BrandAnalyticsView: React.FC = () => {
  const { t } = useTranslation();
  const { analytics, conversionPerSku, fetchErrors, isLoading, refresh } = useBrandViewModel();

  if (isLoading) {
    return <LoadingSpinner text={t('partnerPortal.text136')} />;
  }

  if (!analytics) {
    // A failed fetch must never look like "no data yet" — show an explicit,
    // actionable error (the C6 no-silent-failure rule extended to B2B).
    return (
      <EmptyState
        title={t('partnerPortal.text137')}
        description={fetchErrors.analytics || 'The analytics service could not be reached. Your data is intact — retry when the service is back.'}
        actionText="Retry"
        onAction={refresh}
      />
    );
  }

  const totalViews = analytics.total_views || 1;
  const funnelSteps = [
    { label: '1. Catalog Product Views', count: analytics.total_views, pct: analytics.total_views ? '100%' : 'N/A', source: 'RecentlyViewed' },
    { label: '2. Try-on sessions (all states)', count: analytics.total_tryons, pct: `${((analytics.total_tryons / totalViews) * 100).toFixed(1)}%`, source: 'TryOnSession' },
    { label: '3. Current shopping-bag lines', count: analytics.total_add_to_carts, pct: `${((analytics.total_add_to_carts / totalViews) * 100).toFixed(1)}%`, source: 'CartItem' },
    { label: '4. Eligible order lines', count: analytics.total_purchases, pct: `${analytics.funnel_conversion_rate == null ? t('partnerOps.insufficient') : analytics.funnel_conversion_rate == null ? t('partnerOps.insufficient') : `${analytics.funnel_conversion_rate}%`}`, source: 'OrderItem' },
  ];

  return (
    <div className="space-y-8 pb-20">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">{' '}{t('partnerPortal.text138')}{' '}</h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          {analytics.methodology}
        </p>
      </div>

      {/* Funnel Visualization - REAL DATA */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">{' '}{t('partnerPortal.text139')}{' '}</h3>
        <p className="text-[11px] text-slate-500">{t('partnerPortal.text140')}</p>

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
                  style={{ width: `${Math.max(5, 100 - (idx * 25))}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>

        {analytics.total_views === 0 && (
          <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-xs text-amber-800">{' '}{t('partnerPortal.text141')}{' '}</div>
        )}
      </div>

      {/* Per-product Conversion — an error is surfaced, not laundered into "no rows" */}
      {fetchErrors.conversion && (
        <div role="alert" className="p-4 rounded-2xl bg-rose-50 border border-rose-200">
          <p className="text-[11px] font-bold text-rose-800">{t('b2b.sku_conversion_failed')}</p>
          <p className="text-[11px] text-rose-600 mt-1">{fetchErrors.conversion}</p>
          <button onClick={refresh} className="mt-2 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50">{t('partnerPortal.text005')}</button>
        </div>
      )}
      {conversionPerSku.length > 0 && (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('b2b.sku_conversion_title')}</h3>
          <p className="text-[11px] text-slate-500">{t('partnerPortal.text142')}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400 uppercase text-[10px]">
                  <th className="py-2">{t('partnerPortal.text143')}</th>
                  <th className="py-2">{t('partnerPortal.text144')}</th>
                  <th className="py-2">{t('partnerPortal.text145')}</th>
                  <th className="py-2">{t('partnerPortal.text146')}</th>
                  <th className="py-2">{t('partnerPortal.text147')}</th>
                  <th className="py-2">{t('partnerPortal.text148')}</th>
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
                    <td className="py-2 font-mono font-bold">{row.conversion_rate == null ? t('partnerOps.insufficient') : `${row.conversion_rate}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Return Rate Benchmark Card - REAL */}
      <div className="bg-[#FAF9F6] rounded-3xl border border-slate-200 p-6 sm:p-8 space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">{' '}{t('partnerPortal.text065')}{' '}</h3>
        <div className="grid grid-cols-2 gap-4 text-xs">
          <div className="p-3 rounded-xl bg-white border">
            <span className="text-slate-400 text-[10px] block uppercase">{t('partnerPortal.text149')}</span>
            <span className="font-mono text-lg font-bold text-rose-600">{percent(analytics.return_rate_before_vton)}</span>
            <span className="text-[11px] text-slate-500 block">{t('partnerPortal.text150')}</span>
          </div>
          <div className="p-3 rounded-xl bg-white border">
            <span className="text-slate-400 text-[10px] block uppercase">{t('b2b.tryon_assisted_cohort')}</span>
            <span className="font-mono text-lg font-bold text-emerald-600">{percent(analytics.return_rate_after_vton)}</span>
            <span className="text-[11px] text-slate-500 block">{t('partnerPortal.text151')}</span>
          </div>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">{' '}{t('partnerPortal.text152')}{' '}<strong>{percent(analytics.return_reduction_percentage)}</strong> {analytics.return_cohorts?.methodology}
        </p>
        <div className="text-[11px] text-slate-500 p-2 bg-white rounded border">
          <span className="font-bold">{t('partnerPortal.text153')}</span> {percent(analytics.bopis_store_fulfillment_rate)}{' '}{t('partnerPortal.text154')}{analytics.ad_spend_total}{t('partnerPortal.text155')}{analytics.ad_revenue_total}{' '}{t('partnerPortal.text156')}{' '}</div>
      </div>
    </div>
  );
};
