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
    return <LoadingSpinner text="Aggregating platform-wide telemetry & style heatmaps..." />;
  }

  if (!adminAnalytics) {
    return (
      <EmptyState
        title="Platform telemetry unavailable"
        description={fetchErrors.adminAnalytics || 'The admin analytics endpoint could not be reached. Retry when the service is back — no numbers are ever simulated here.'}
        actionText="Retry"
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
    value === null || value === undefined ? 'N/A' : `${value}%`;

  return (
    <div className="space-y-8 pb-20">
      {/* P1 (2026-09-22 audit): the readiness verdict from /health must be
          visible HERE, so KPI cards can never imply an operational platform
          while a core capability is blocked. */}
      <ReadinessBanner />
      <CardStackShowcase
        tone="analytics"
        compact
        eyebrow="Platform Governance Stack"
        title="Audit-ready design system across admin operations"
        description="The admin surface reuses the components as a governance overview for attribution, catalog quality, and operational control."
      />
      <div className="border-b border-slate-200 pb-4">
        <h1 className="font-serif text-3xl font-bold text-[#1B1F3B]">
          Platform Administration & Revenue Attribution - Real Data
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-1">
          Macro metrics from transactional DB: Order, OrderItem, Outfit, ReturnRequest, BrandAnalyticsEvent. No fake numbers.
        </p>
        <p className="text-[11px] text-slate-400 mt-1">Methodology: GMV from SUM(Order.total_amount) where status not cancelled/refunded. Try-on adoption from Order.try_on_assisted. Outfit-to-purchase from Outfit.is_saved + OrderItem.outfit_id. Return rates cohort analysis try-on vs non-try-on. Revenue attribution last-touch: stylist_assisted flag, outfit_id, BrandAnalyticsEvent.attribution_source. Brand performance from real views/tryons/orders.</p>
      </div>

      {/* Platform Macro KPIs - REAL */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Platform GMV (Real)</span>
          <div className="text-2xl font-serif font-black text-[#1B1F3B]">
            ${adminAnalytics.total_gmv.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">From Order.total_amount SUM, excl cancelled/refunded</div>
          {!hasData && <div className="text-[10px] text-amber-600">No orders yet</div>}
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Total Orders (Real)</span>
          <div className="text-2xl font-serif font-black text-[#1B1F3B]">
            {adminAnalytics.total_orders.toLocaleString()}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">Try-On Assisted: {pct(adminAnalytics.tryon_adoption_rate)} from Order.try_on_assisted</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Outfit-to-Purchase Ratio (Real)</span>
          <div className="text-2xl font-serif font-black text-[#B8935A]">
            {pct(adminAnalytics.stylist_conversion_ratio)}
          </div>
          <div className="text-[11px] text-slate-500 font-medium">Saved Outfit to Purchase, from Outfit.is_saved + OrderItem.outfit_id</div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold text-slate-400 uppercase">Platform Return Rate (Real)</span>
          <div className="text-2xl font-serif font-black text-emerald-600">
            {pct(adminAnalytics.platform_avg_return_rate)}
          </div>
          <div className="text-[11px] text-slate-500">Try-On: {pct(adminAnalytics.return_rate_tryon_users)} vs Non-Try-On: {pct(adminAnalytics.return_rate_non_tryon_users)}</div>
        </div>
      </div>

      {/* Revenue Attribution & Style Preference Heatmap - REAL */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-6 bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
              Revenue Attribution by AI Feature - Real
            </h3>
            <p className="text-xs text-slate-500">Direct sales from Order flags, not fake percentages</p>
            <p className="text-[10px] text-slate-400 mt-1">Last-touch: Virtual Stylist via Order.stylist_assisted, Outfit Builder via OrderItem.outfit_id, Visual Search via BrandAnalyticsEvent. Uses Order.total_amount authoritative, not frontend. Refunds excluded.</p>
            {/* P1 financial-semantics separation: operational metrics, not a
                billing ledger — echoed from the backend contract. */}
            <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-[10px] font-semibold text-amber-800">
              Operational metrics — NOT a verified billing ledger. Do not invoice or settle from these figures; reconcile against payment provider records first.
            </p>
          </div>

          <div className="space-y-3 text-xs">
            {Object.entries(adminAnalytics.revenue_attribution).map(([feat, rev]) => (
              <div key={feat} className="flex justify-between items-center p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="font-bold text-slate-800 capitalize">{feat.replace('_', ' ')}</span>
                <span className="font-mono text-sm font-bold text-[#1B1F3B]">
                  ${Number(rev).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>
            ))}
            {!hasData && <div className="text-[11px] text-amber-700 bg-amber-50 p-3 rounded">No revenue yet - will populate from Order.total_amount when orders occur with attribution flags.</div>}
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
          <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">Most Styled Items - Real Ranking</h3>
          <p className="text-[11px] text-slate-500">Ranking by outfit appearances across all users, from OutfitItem grouped by product_id ORDER BY count DESC, real data not random.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {(adminAnalytics as any).most_styled_items.slice(0, 6).map((item: any, idx: number) => (
              <div key={item.product_id} className="flex items-center gap-3 p-3 rounded-2xl bg-[#FAF9F6] border">
                <div className="w-8 h-8 rounded-xl bg-[#1B1F3B] text-white flex items-center justify-center font-bold text-xs">#{idx + 1}</div>
                <div className="w-10 h-12 rounded bg-white overflow-hidden"><img src={item.thumbnail_url} alt={item.title} className="w-full h-full object-cover" /></div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold truncate">{item.title}</div>
                  <div className="text-[10px] text-slate-500">{item.brand_name} · {item.appearances} appearances</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Brand Performance Table - REAL */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
        <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">Brand Performance Table - Real Side-by-Side</h3>
        <p className="text-[11px] text-slate-500">Side-by-side comparison of brand conversion rates from real platform data: views from RecentlyViewed, tryons from TryOnSession, orders from OrderItem, conversion = orders/views*100, return rate from ReturnRequest. Sorted by orders DESC. No fake rows.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-400 uppercase text-[10px]">
                <th className="py-2">Brand</th>
                <th className="py-2">Products</th>
                <th className="py-2">Views</th>
                <th className="py-2">Try-Ons</th>
                <th className="py-2">Orders</th>
                <th className="py-2">Conv %</th>
                <th className="py-2">Try-On Rate</th>
                <th className="py-2">Return Rate</th>
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
          {!hasData && <div className="p-4 text-center text-xs text-amber-700 bg-amber-50 rounded-xl mt-3">No brand performance data yet - will populate from real orders, views, try-ons.</div>}
        </div>
      </div>

      {/* System Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Total Users</span>
          <span className="font-bold text-lg">{adminAnalytics.total_users_count}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Total Brands</span>
          <span className="font-bold text-lg">{adminAnalytics.total_brands_count}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Try-On Adoption</span>
          <span className="font-bold text-lg text-[#B8935A]">{pct(adminAnalytics.tryon_adoption_rate)}</span>
        </div>
        <div className="p-4 rounded-2xl bg-white border border-slate-200">
          <span className="text-slate-400 text-[10px] uppercase block">Outfit-to-Purchase</span>
          <span className="font-bold text-lg text-emerald-600">{pct(adminAnalytics.stylist_conversion_ratio)}</span>
        </div>
      </div>
    </div>
  );
};
