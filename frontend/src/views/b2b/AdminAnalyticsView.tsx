import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { useBrandViewModel } from '../../viewmodels/useBrandViewModel';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';
import { CardStackShowcase } from '../../components/showcase/DesignShowcases';
import { ReadinessBanner } from '../../components/admin/ReadinessBanner';
import { Reveal } from '../../components/common/Surface';
import { BrandReportDownloadButton } from '../../components/admin/BrandReportDownloadButton';
import { HonestProductImage } from '../../components/common/HonestProductImage';
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

/** Spec 12 §6.3: the analysed window lives in the URL — shareable and
 *  reload-proof. 'all' (no param) matches the API's own default. */
const WINDOW_CHOICES = [30, 90, 365] as const;

export const AdminAnalyticsView: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const daysParam = Number(searchParams.get('days'));
  const analyticsDays = (WINDOW_CHOICES as readonly number[]).includes(daysParam)
    ? daysParam
    : undefined;
  const { adminAnalytics, fetchErrors, fetchErrorMeta = {}, isLoading, refresh } = useBrandViewModel('admin', {
    analyticsDays,
  });

  // Freshness is MEASURED, not decorative: stamped when a payload lands.
  const [fetchedAt, setFetchedAt] = React.useState<Date | null>(null);
  React.useEffect(() => {
    if (adminAnalytics) setFetchedAt(new Date());
  }, [adminAnalytics]);

  const setWindow = (days?: number) => {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (days) next.set('days', String(days));
        else next.delete('days');
        return next;
      },
      { replace: true },
    );
  };

  // Spec 12 §6.4: client-side sort of the ALREADY-LOADED brand rows (the
  // endpoint returns one bounded list; there is no server sort to call —
  // sorting what is on screen invents nothing).
  const [sortKey, setSortKey] = React.useState<'orders' | 'products' | 'views' | 'conversion_rate'>('orders');
  const [sortDir, setSortDir] = React.useState<'desc' | 'asc'>('desc');
  const toggleSort = (key: typeof sortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  if (isLoading) {
    return <LoadingSpinner text={t('admin_analytics.loading')} />;
  }

  if (!adminAnalytics) {
    // §5 permission denied ≠ outage: a server-side 401/403 is a ROLE verdict.
    // Localized (the raw server string is English-only), and no retry button —
    // retrying cannot change a refusal, it only suggests the data is flaky.
    const denialStatus = fetchErrorMeta.adminAnalytics?.status;
    if (denialStatus === 401 || denialStatus === 403) {
      return (
        <EmptyState
          title={t('admin_analytics.permission_denied_title')}
          description={t('admin_analytics.permission_denied_body')}
        />
      );
    }
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

        {/* Spec 12 §6.2: every number's provenance in one audited line —
            the SERVER's echo of the analysed window + the measured fetch
            time. Text, polite, never animation. */}
        <p role="status" aria-live="polite" className="mt-2 text-[11px] font-medium text-slate-600">
          {adminAnalytics.time_range
            ? adminAnalytics.time_range.is_all_time
              ? t('admin_analytics.window_all_time')
              : t('admin_analytics.window_bounded', {
                  from: adminAnalytics.time_range.date_from?.slice(0, 10) ?? '—',
                  to: adminAnalytics.time_range.date_to?.slice(0, 10) ?? '—',
                })
            : t('admin_analytics.window_unreported')}
          {fetchedAt
            ? ` · ${t('admin_analytics.fetched_at', {
                time: fetchedAt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
              })}`
            : ''}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label={t('admin_analytics.window_label')}>
          {WINDOW_CHOICES.map((days) => (
            <button
              key={days}
              type="button"
              onClick={() => setWindow(days)}
              aria-pressed={analyticsDays === days}
              className={`min-h-11 rounded-xl border px-4 text-xs font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A] ${
                analyticsDays === days
                  ? 'border-[#1B1F3B] bg-[#1B1F3B] text-white'
                  : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
              }`}
            >
              {t('admin_analytics.window_days', { days: days })}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setWindow(undefined)}
            aria-pressed={analyticsDays === undefined}
            className={`min-h-11 rounded-xl border px-4 text-xs font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A] ${
              analyticsDays === undefined
                ? 'border-[#1B1F3B] bg-[#1B1F3B] text-white'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
            }`}
          >
            {t('admin_analytics.window_all')}
          </button>
          <button
            type="button"
            onClick={refresh}
            className="min-h-11 rounded-xl border border-slate-300 bg-white px-4 text-xs font-bold text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
          >
            {t('admin_analytics.refresh')}
          </button>
        </div>
      </div>

      {/* Platform Macro KPIs - REAL. Reveal = spec-09 entrance (opacity/
          translate only, reduced-motion renders the identical static grid). */}
      <Reveal className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-sm space-y-1">
          <span className="text-xs font-bold uppercase text-slate-500">{t('admin_analytics.gmv_title')}</span>
          <div className="font-serif text-2xl font-black text-[#1B1F3B]" dir="ltr">
            {money(adminAnalytics.total_gmv, adminAnalytics.currency)}
          </div>
          {gmvEntries.length > 0 && adminAnalytics.currency_status === 'mixed_currencies' && (
            <ul className="space-y-1 font-mono text-xs text-slate-700">
              {gmvEntries.map(([code, amount]) => (
                <li key={code} dir="ltr">{money(amount, code)}</li>
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
      </Reveal>

      {/* Revenue Attribution & Style Preference Heatmap - REAL */}
      <Reveal delay={0.1} className="grid grid-cols-1 lg:grid-cols-12 gap-8">
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
                        <span className="font-mono text-sm font-bold text-[#1B1F3B]" dir="ltr">
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
                  <span className="font-mono text-sm font-bold text-[#1B1F3B]" dir="ltr">
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
      </Reveal>

      {/* Most Styled Items - REAL */}
      {adminAnalytics.most_styled_items?.length ? (
        <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h2 className="font-serif text-lg font-bold text-[#1B1F3B]">{t('admin_analytics.most_styled_title')}</h2>
          <p className="text-[11px] text-slate-600">{t('admin_analytics.most_styled_methodology')}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {adminAnalytics.most_styled_items.slice(0, 6).map((item, idx) => (
              <div key={item.product_id} className="flex items-center gap-3 p-3 rounded-2xl bg-[#FAF9F6] border">
                <div className="w-8 h-8 rounded-xl bg-[#1B1F3B] text-white flex items-center justify-center font-bold text-xs">#{idx + 1}</div>
                <div className="w-10 h-12 rounded bg-white overflow-hidden"><HonestProductImage src={item.thumbnail_url} alt={item.title} className="w-full h-full object-cover" /></div>
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
      ) : null}

      {/* Brand Performance Table - REAL */}
      {(() => {
        const rows = [...adminAnalytics.top_performing_brands].sort((a, b) => {
          const pick = (r: typeof a) =>
            sortKey === 'orders' ? r.orders
            : sortKey === 'products' ? r.products
            : sortKey === 'views' ? r.views
            : r.conversion_rate;
          const av = pick(a);
          const bv = pick(b);
          // Missing values sort LAST regardless of direction — absence is
          // not a ranking, it is absence (§2).
          if (av === undefined || av === null) return 1;
          if (bv === undefined || bv === null) return -1;
          return sortDir === 'desc' ? Number(bv) - Number(av) : Number(av) - Number(bv);
        });
        return (
      <Reveal delay={0.15} className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-4">
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
                <th scope="col" className="py-2" aria-sort={sortKey === 'products' ? (sortDir === 'desc' ? 'descending' : 'ascending') : undefined}>
                  <button
                    type="button"
                    onClick={() => toggleSort('products')}
                    className="inline-flex min-h-11 items-center gap-1 font-bold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
                  >
                    {t('admin_analytics.products')}
                    <span aria-hidden="true">{sortKey === 'products' ? (sortDir === 'desc' ? '↓' : '↑') : ''}</span>
                  </button>
                </th>
                <th scope="col" className="py-2" aria-sort={sortKey === 'views' ? (sortDir === 'desc' ? 'descending' : 'ascending') : undefined}>
                  <button
                    type="button"
                    onClick={() => toggleSort('views')}
                    className="inline-flex min-h-11 items-center gap-1 font-bold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
                  >
                    {t('admin_analytics.views')}
                    <span aria-hidden="true">{sortKey === 'views' ? (sortDir === 'desc' ? '↓' : '↑') : ''}</span>
                  </button>
                </th>
                <th scope="col" className="py-2">{t('admin_analytics.tryons')}</th>
                <th scope="col" className="py-2" aria-sort={sortKey === 'orders' ? (sortDir === 'desc' ? 'descending' : 'ascending') : undefined}>
                  <button
                    type="button"
                    onClick={() => toggleSort('orders')}
                    className="inline-flex min-h-11 items-center gap-1 font-bold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
                  >
                    {t('admin_analytics.orders')}
                    <span aria-hidden="true">{sortKey === 'orders' ? (sortDir === 'desc' ? '↓' : '↑') : ''}</span>
                  </button>
                </th>
                <th scope="col" className="py-2" aria-sort={sortKey === 'conversion_rate' ? (sortDir === 'desc' ? 'descending' : 'ascending') : undefined}>
                  <button
                    type="button"
                    onClick={() => toggleSort('conversion_rate')}
                    className="inline-flex min-h-11 items-center gap-1 font-bold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
                  >
                    {t('admin_analytics.conversion')}
                    <span aria-hidden="true">{sortKey === 'conversion_rate' ? (sortDir === 'desc' ? '↓' : '↑') : ''}</span>
                  </button>
                </th>
                <th scope="col" className="py-2">{t('admin_analytics.tryon_rate')}</th>
                <th scope="col" className="py-2">{t('admin_analytics.return_rate')}</th>
                {/* Spec 12 export: the real PDF contract, next to each brand. */}
                <th scope="col" className="py-2">{t('admin_catalog.report_pdf')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((brand) => {
                /* §2: a metric the API did not send renders as N/A TEXT.
                   The old cells fabricated data: tryons fell back to the
                   ORDERS count and then to 0, and a missing conversion
                   rendered "-%". */
                const na = t('admin_analytics.not_available');
                return (
                <tr key={brand.brand_id ?? brand.brand} className="hover:bg-slate-50">
                  <td className="py-3 font-bold">
                    {brand.brand_id ? (
                      /* §6.5 drill-down: restricted admin route; the catalog
                         view already reads brand_id from the URL. */
                      <Link
                        to={`/admin/catalog?brand_id=${brand.brand_id}`}
                        className="inline-flex min-h-11 items-center underline decoration-[#B8935A] underline-offset-2 hover:text-[#8A6A2F] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B8935A]"
                        aria-label={t('admin_analytics.drill_down', { brand: brand.brand })}
                      >
                        {brand.brand}
                      </Link>
                    ) : (
                      brand.brand
                    )}
                  </td>
                  <td className="py-3" dir="ltr">{brand.products ?? na}</td>
                  <td className="py-3" dir="ltr">{brand.views ?? na}</td>
                  <td className="py-3" dir="ltr">{brand.tryons ?? na}</td>
                  <td className="py-3 font-bold text-emerald-600" dir="ltr">{brand.orders}</td>
                  <td className="py-3 font-mono" dir="ltr">
                    {brand.conversion_rate === undefined || brand.conversion_rate === null
                      ? na
                      : `${brand.conversion_rate}%`}
                  </td>
                  <td className="py-3" dir="ltr">{brand.tryon_rate ?? na}</td>
                  <td className="py-3" dir="ltr">{brand.return_rate ?? na}</td>
                  <td className="py-3">
                    {brand.brand_id ? (
                      <BrandReportDownloadButton
                        brandId={brand.brand_id}
                        brandName={brand.brand}
                      />
                    ) : (
                      /* No brand_id on the row ⇒ no real endpoint to call —
                         say so instead of a dead button (§2 honesty). */
                      <span className="text-[11px] text-slate-400">{na}</span>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
          {!hasData && (
            <div className="mt-3 rounded-xl bg-amber-50 p-4 text-center text-xs text-amber-800">
              {t('admin_analytics.no_brand_data')}
            </div>
          )}
        </div>
      </Reveal>
        );
      })()}

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
