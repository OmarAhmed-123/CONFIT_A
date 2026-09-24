import React from 'react';
import { useTranslation } from 'react-i18next';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';
import { CardStackShowcase } from '../../components/showcase/DesignShowcases';
import { ReadinessBanner } from '../../components/admin/ReadinessBanner';
import type { StyleHeatmapCell } from '../../models';

const HeatmapDimension: React.FC<{
  title: string;
  cells: StyleHeatmapCell[];
  cellLabel: (cell: StyleHeatmapCell) => string;
}> = ({ title, cells, cellLabel }) => {
  const { t } = useTranslation();
  if (!cells || cells.length === 0) {
    return (
      <div className="text-[11px] text-slate-400">
        <span className="font-bold text-slate-600">{title}: </span>
        {t('admin_heatmap.dimension_empty')}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <span className="text-xs font-bold text-slate-700 block">{title}</span>
      {cells.map((cell) => (
        <div key={cell.raw_name ?? cell.name} className="space-y-1 text-xs">
          <div className="flex justify-between font-bold text-slate-700">
            <span>{cell.name}</span>
            <span className="text-[#B8935A]">{cellLabel(cell)}</span>
          </div>
          <div className="w-full h-3 rounded-full bg-slate-100 overflow-hidden">
            <div
              className="h-full bg-[#1B1F3B] rounded-full"
              style={{ width: `${Math.min(100, cell.share)}%` }}
              role="presentation"
            />
          </div>
        </div>
      ))}
    </div>
  );
};

export const AdminAnalyticsView: React.FC = () => {
  const { t } = useTranslation();
  const { adminAnalytics, fetchErrors, isLoading, refresh } = useBrandViewModel('admin');

  if (isLoading) {
    return <LoadingSpinner text={t('admin_analytics.loading')} />;
  }

  if (!adminAnalytics) {
    return (
      <EmptyState
        title={t('admin_analytics.unavailable_title')}
        description={fetchErrors.adminAnalytics || t('admin_analytics.unavailable_fallback')}
        actionText={t('admin_analytics.retry')}
        onAction={refresh}
      />
    );
  }

  const hasData = adminAnalytics.total_orders > 0;
  const heatmap = adminAnalytics.style_preference_heatmap;
  const cellShare = (cell: StyleHeatmapCell) =>
    t('admin_heatmap.cell_share', { share: cell.share, count: cell.count });
  // P1 honesty contract: null = unmeasured (zero denominator) -> N/A.
  // A real 0 renders as "0%" — measured zero and unmeasured are different facts.
  const pct = (value: number | null | undefined) =>
    value === null || value === undefined ? t('admin_analytics.not_available') : `${value}%`;
  const money = (value: number | null | undefined, currency?: string | null) => {
    if (value === null || value === undefined || !currency) {
      return t('admin_analytics.not_available');
    }
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency', currency, minimumFractionDigits: 2,
      }).format(value);
    } catch {
      return `${currency} ${value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
    }
  };
  const gmvEntries = Object.entries(adminAnalytics.gmv_by_currency ?? {});
  const attributionGroups = Object.entries(adminAnalytics.attribution_by_currency ?? {});

  return (
    <div className="space-y-8 pb-20">
      {/* P1 (2026-09-22 audit): the readiness verdict from /health must be
          visible HERE, so KPI cards can never imply an operational platform
          while a core capability is blocked. */}
      <ReadinessBanner />
      <CardStackShowcase
        tone="analytics"
        compact
        eyebrow={t('admin_analytics.eyebrow')}
        title={t('admin_analytics.showcase_title')}
        description={t('admin_analytics.showcase_desc')}
      />
      <div className="border-b border-slate-200 pb-4">
        <h1 className="font-serif text-2xl font-bold text-[#1B1F3B] sm:text-3xl">
          {t('admin_analytics.title')}
        </h1>
        <p className="mt-1 text-xs text-slate-500 sm:text-sm">
          {t('admin_analytics.lede')}
        </p>
        <p className="mt-1 text-[11px] text-slate-500">
          {t('admin_analytics.methodology')}
        </p>
      </div>

      {/* Platform Macro KPIs - REAL */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold uppercase text-slate-500">{t('admin_analytics.gmv_title')}</span>
          <div className="font-serif text-2xl font-black text-[#1B1F3B]">
            {money(adminAnalytics.total_gmv, adminAnalytics.currency)}
          </div>
          {gmvEntries.length > 0 && adminAnalytics.currency_status === 'mixed_currencies' && (
            <ul className="space-y-1 font-mono text-xs text-slate-700">
              {gmvEntries.map(([code, amount]) => (
                <li key={code}>{money(amount, code)}</li>
              ))}
            </ul>
          )}
          <div className="text-[11px] font-medium text-slate-600">{t('admin_analytics.gmv_source')}</div>
          {adminAnalytics.currency_status === 'mixed_currencies' && (
            <div role="status" className="text-[10px] font-semibold text-amber-700">
              {t('admin_analytics.mixed_currency')}
            </div>
          )}
          {!hasData && <div className="text-[10px] text-amber-700">{t('admin_analytics.no_orders')}</div>}
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold uppercase text-slate-500">{t('admin_analytics.orders_title')}</span>
          <div className="font-serif text-2xl font-black text-[#1B1F3B]">
            {adminAnalytics.total_orders.toLocaleString()}
          </div>
          <div className="text-[11px] font-medium text-slate-600">
            {t('admin_analytics.tryon_assisted', { value: pct(adminAnalytics.tryon_adoption_rate) })}
          </div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold uppercase text-slate-500">{t('admin_analytics.outfit_ratio_title')}</span>
          <div className="font-serif text-2xl font-black text-[#8A6A2F]">
            {pct(adminAnalytics.stylist_conversion_ratio)}
          </div>
          <div className="text-[11px] font-medium text-slate-600">{t('admin_analytics.outfit_ratio_source')}</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold uppercase text-slate-500">{t('admin_analytics.return_rate_title')}</span>
          <div className="font-serif text-2xl font-black text-emerald-700">
            {pct(adminAnalytics.platform_avg_return_rate)}
          </div>
          <div className="text-[11px] text-slate-600">
            {t('admin_analytics.tryon_vs', {
              tryon: pct(adminAnalytics.return_rate_tryon_users),
              nonTryon: pct(adminAnalytics.return_rate_non_tryon_users),
            })}
          </div>
        </div>
      </div>

      {/* Revenue Attribution & Style Preference Heatmap - REAL */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-6 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h2 className="font-serif text-lg font-bold text-[#1B1F3B]">
              {t('admin_analytics.attribution_title')}
            </h2>
            <p className="text-xs text-slate-600">{t('admin_analytics.attribution_subtitle')}</p>
            <p className="mt-1 text-[10px] text-slate-500">{t('admin_analytics.attribution_methodology')}</p>
            <p className="mt-2 rounded-lg border border-amber-300 bg-amber-50 px-2 py-1.5 text-[10px] font-semibold text-amber-900">
              {t('admin_analytics.financial_warning')}
            </p>
          </div>

          <div className="space-y-4 text-xs">
            {attributionGroups.length > 0 ? (
              attributionGroups.map(([currencyCode, channels]) => (
                <section key={currencyCode} aria-label={t('admin_analytics.currency_group', { currency: currencyCode })}>
                  <h3 className="mb-2 font-mono text-[11px] font-bold text-slate-600">{currencyCode}</h3>
                  <div className="space-y-2">
                    {Object.entries(channels).map(([feat, rev]) => (
                      <div key={feat} className="flex items-center justify-between gap-3 rounded-2xl border border-slate-100 bg-[#FAF9F6] p-3">
                        <span className="font-bold text-slate-800">
                          {t(`admin_analytics.channel.${feat}`, { defaultValue: feat.replace(/_/g, ' ') })}
                        </span>
                        <span className="font-mono text-sm font-bold text-[#1B1F3B]">
                          {money(rev, currencyCode)}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              ))
            ) : (
              Object.entries(adminAnalytics.revenue_attribution).map(([feat, rev]) => (
                <div key={feat} className="flex items-center justify-between gap-3 rounded-2xl border border-slate-100 bg-[#FAF9F6] p-3">
                  <span className="font-bold text-slate-800">
                    {t(`admin_analytics.channel.${feat}`, { defaultValue: feat.replace(/_/g, ' ') })}
                  </span>
                  <span className="font-mono text-sm font-bold text-[#1B1F3B]">
                    {money(rev, adminAnalytics.currency)}
                  </span>
                </div>
              ))
            )}
            {!hasData && (
              <div className="rounded bg-amber-50 p-3 text-[11px] text-amber-800">
                {t('admin_analytics.no_revenue')}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-6 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              {t('admin_heatmap.title', { scope: heatmap.region })}
            </h3>
            <p className="text-xs text-slate-500">{t('admin_heatmap.subtitle')}</p>
            <p className="text-[10px] text-slate-400 mt-1">{heatmap.privacy_threshold}</p>
          </div>

          {heatmap.data_available === false ? (
            /* G-01: this panel used to fill itself with four hardcoded aesthetics
               and four hardcoded colour chips whenever the real aggregate was
               empty, inside a dashboard titled "Real Data". It now says why
               there is nothing to show. */
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
              <div className="font-bold">{t('admin_heatmap.not_available_title')}</div>
              <p className="mt-1 leading-relaxed">
                {t('admin_heatmap.not_available_body', {
                  sample: heatmap.sample_size ?? 0,
                  required: heatmap.min_sample_required ?? 10,
                })}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <HeatmapDimension
                title={t('admin_heatmap.dimension_aesthetics')}
                cells={heatmap.top_aesthetics}
                cellLabel={cellShare}
              />
              <HeatmapDimension
                title={t('admin_heatmap.dimension_colours')}
                cells={heatmap.trending_colors}
                cellLabel={cellShare}
              />
              <HeatmapDimension
                title={t('admin_heatmap.dimension_occasions')}
                cells={heatmap.top_occasions}
                cellLabel={cellShare}
              />
            </div>
          )}

          {!!heatmap.limitations?.length && (
            <ul className="space-y-1 border-t border-slate-100 pt-3 text-[10px] leading-relaxed text-slate-400">
              {heatmap.limitations.map((limitation) => (
                <li key={limitation}>· {limitation}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Most Styled Items - REAL */}
      {(adminAnalytics as any).most_styled_items && (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h2 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('admin_analytics.most_styled_title')}</h2>
          <p className="text-[11px] text-slate-600">{t('admin_analytics.most_styled_methodology')}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {(adminAnalytics as any).most_styled_items.slice(0, 6).map((item: any, idx: number) => (
              <div key={item.product_id} className="flex items-center gap-3 p-3 rounded-2xl bg-[#FAF9F6] border">
                <div className="w-8 h-8 rounded-xl bg-[#1B1F3B] text-white flex items-center justify-center font-bold text-xs">#{idx + 1}</div>
                <div className="w-10 h-12 rounded bg-white overflow-hidden"><img src={item.thumbnail_url} alt={item.title} className="w-full h-full object-cover" /></div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold truncate">{item.title}</div>
                  <div className="text-[10px] text-slate-600">
                    {item.brand_name} · {t('admin_analytics.appearances', { count: item.appearances })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Brand Performance Table - REAL */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
        <h2 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('admin_analytics.brand_perf_title')}</h2>
        <p className="text-[11px] text-slate-600">{t('admin_analytics.brand_perf_methodology')}</p>
        <div
          role="region"
          aria-label={t('admin_analytics.brand_table_caption')}
          tabIndex={0}
          className="overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
        >
          <table className="min-w-[760px] w-full text-left text-xs">
            <caption className="sr-only">{t('admin_analytics.brand_table_caption')}</caption>
            <thead>
              <tr className="border-b border-slate-100 text-[10px] uppercase text-slate-500">
                <th scope="col" className="py-2">{t('admin_analytics.brand')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.products')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.views')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.tryons')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.orders')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.conversion')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.tryon_rate')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.return_rate')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {adminAnalytics.top_performing_brands.map((brand: any) => (
                <tr key={brand.brand_id || brand.brand} className="hover:bg-slate-50">
                  <td className="py-3 font-bold">{brand.brand}</td>
                  <td className="py-3">{brand.products ?? '-'}</td>
                  <td className="py-3">{brand.views ?? '-'}</td>
                  <td className="py-3">{brand.tryons ?? brand.orders ?? 0}</td>
                  <td className="py-3 font-bold text-emerald-600">{brand.orders}</td>
                  <td className="py-3 font-mono">{brand.conversion_rate ?? '-'}%</td>
                  <td className="py-3">{brand.tryon_rate}</td>
                  <td className="py-3">{brand.return_rate}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!hasData && (
            <div className="mt-3 rounded-xl bg-amber-50 p-4 text-center text-xs text-amber-800">
              {t('admin_analytics.no_brand_data')}
            </div>
          )}
        </div>
      </div>

      {/* System Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="block text-[10px] uppercase text-slate-500">{t('admin_analytics.total_users')}</span>
          <span className="font-bold text-lg">{adminAnalytics.total_users_count}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="block text-[10px] uppercase text-slate-500">{t('admin_analytics.total_brands')}</span>
          <span className="font-bold text-lg">{adminAnalytics.total_brands_count}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="block text-[10px] uppercase text-slate-500">{t('admin_analytics.tryon_adoption')}</span>
          <span className="font-bold text-lg text-[#B8935A]">{pct(adminAnalytics.tryon_adoption_rate)}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="block text-[10px] uppercase text-slate-500">{t('admin_analytics.outfit_to_purchase')}</span>
          <span className="font-bold text-lg text-emerald-600">{pct(adminAnalytics.stylist_conversion_ratio)}</span>
        </div>
      </div>
    </div>
  );
};
