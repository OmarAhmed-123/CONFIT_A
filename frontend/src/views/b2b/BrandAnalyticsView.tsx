import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { brandService } from '../../services/apiServices';
import { LoadingSpinner, EmptyState } from '../../components/common/CommonComponents';
import { BiTrendChart } from '../../components/analytics/BiTrendChart';
import { BiCategoryDonut } from '../../components/analytics/BiCategoryDonut';
import { BiBranchPerformanceTable } from '../../components/analytics/BiBranchPerformanceTable';
import { BiInventoryHealthCard } from '../../components/analytics/BiInventoryHealthCard';
import { BiPromotionTable } from '../../components/analytics/BiPromotionTable';
import { DownloadIcon, RefreshIcon } from '../../components/icons/ConfitIcons';
import { useUIStore } from '../../stores/uiStore';
import type { BiDashboardResponse } from '../../models';

export const BrandAnalyticsView: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { showToast } = useUIStore();
  const isRtl = i18n.dir() === 'rtl';
  const presetWindows = [
    { label: t('audit_closure.preset_today'), days: 1 },
    { label: t('audit_closure.preset_7d'), days: 7 },
    { label: t('audit_closure.preset_30d'), days: 30 },
    { label: t('audit_closure.preset_90d'), days: 90 },
    { label: t('audit_closure.preset_ytd'), days: 365 },
  ] as const;

  // Filters State
  const [selectedDays, setSelectedDays] = useState<number | 'custom'>(30);
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [selectedBranchId, setSelectedBranchId] = useState<number | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);
  const [comparePeriod, setComparePeriod] = useState(true);

  // Data & Lifecycle
  const [data, setData] = useState<BiDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  // Export State
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params: any = {
        compare: comparePeriod,
      };
      if (selectedDays === 'custom') {
        if (customFrom) params.dateFrom = customFrom;
        if (customTo) params.dateTo = customTo;
      } else {
        params.days = selectedDays;
      }
      if (selectedBranchId != null) params.branchId = selectedBranchId;
      if (selectedCategoryId != null) params.categoryId = selectedCategoryId;

      const res = await brandService.getBiDashboard(params);
      setData(res);
      setLastFetched(new Date());
    } catch (err: any) {
      setError(err?.message || t('audit_closure.telemetry_load_failed'));
    } finally {
      setIsLoading(false);
    }
  }, [selectedDays, customFrom, customTo, selectedBranchId, selectedCategoryId, comparePeriod]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDownloadPdf = async () => {
    if (isExportingPdf) return;
    setIsExportingPdf(true);
    try {
      const params: any = {};
      if (selectedDays === 'custom') {
        if (customFrom) params.dateFrom = customFrom;
        if (customTo) params.dateTo = customTo;
      } else {
        params.days = selectedDays;
      }
      if (selectedBranchId != null) params.branchId = selectedBranchId;
      if (selectedCategoryId != null) params.categoryId = selectedCategoryId;

      const { blob, filename } = await brandService.downloadBiPdf(params);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || `confit-bi-report-${data?.brand?.slug || 'brand'}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      showToast(e?.message || t('audit_closure.pdf_export_failed'), 'error');
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleDownloadCsv = async () => {
    if (isExportingCsv) return;
    setIsExportingCsv(true);
    try {
      const params: any = {};
      if (selectedDays === 'custom') {
        if (customFrom) params.dateFrom = customFrom;
        if (customTo) params.dateTo = customTo;
      } else {
        params.days = selectedDays;
      }
      if (selectedBranchId != null) params.branchId = selectedBranchId;
      if (selectedCategoryId != null) params.categoryId = selectedCategoryId;

      const { blob, filename } = await brandService.downloadBiCsv(params);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || `confit-bi-data-${data?.brand?.slug || 'brand'}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      showToast(e?.message || t('audit_closure.csv_export_failed'), 'error');
    } finally {
      setIsExportingCsv(false);
    }
  };

  const handleResetFilters = () => {
    setSelectedDays(30);
    setCustomFrom('');
    setCustomTo('');
    setSelectedBranchId(null);
    setSelectedCategoryId(null);
    setComparePeriod(true);
  };

  if (isLoading && !data) {
    return <LoadingSpinner text={t('common.loading')} />;
  }

  if (error && !data) {
    return (
      <EmptyState
        title={t('brand_analytics.telemetry_unavailable')}
        description={error}
        actionText={t('common.retry')}
        onAction={fetchData}
      />
    );
  }

  const kpis = data?.kpis;
  const growth = data?.growth || {};
  const inventory = data?.inventory;
  const currency = kpis?.currency || 'USD';

  /*
   * A growth chip is a CLAIM. It may only be rendered from a real percentage.
   *
   * The server used to answer "+100%" for a metric whose previous-period value
   * was zero, so this component rendered a green success chip for brands with
   * no prior period at all. The server now sends null for those, plus
   * `growth_basis` explaining why — and the chip says so in words instead of
   * disappearing, because a silent gap reads as "no data" while the truth is
   * "there is nothing to compare against yet".
   */
  const renderGrowthChip = (key: string) => {
    const val = growth[key];
    if (!data?.period?.comparison_label) return null;

    const basis = data?.growth_basis?.[key.replace(/_change_pct$/, '')];

    if (val === undefined || val === null) {
      // Absent because it cannot be calculated — say which case it is.
      if (basis === 'no_prior_baseline') {
        return (
          <span
            data-testid={`growth-basis-${key}`}
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-50 text-slate-600 border border-slate-200"
            title={t('bi.no_prior_baseline_hint')}
          >
            {t('bi.no_prior_baseline')}
          </span>
        );
      }
      if (basis === 'no_activity') {
        return (
          <span
            data-testid={`growth-basis-${key}`}
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600"
            title={t('bi.no_activity_hint')}
          >
            {t('bi.no_activity')}
          </span>
        );
      }
      return null;
    }

    const isPositive = val > 0;
    const isNeutral = val === 0;
    return (
      <span
        className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold font-mono ${
          isPositive
            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            : isNeutral
            ? 'bg-slate-100 text-slate-600'
            : 'bg-rose-50 text-rose-700 border border-rose-200'
        }`}
        title={t('bi.compared_to', { period: data.period.comparison_label })}
      >
        {isPositive ? `+${val}%` : `${val}%`}
      </span>
    );
  };

  return (
    <div className="space-y-8 pb-24">
      {/* 1. Header & Context */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-brand-charcoal">
              {t('bi.title', 'Advanced Business Intelligence & Reporting')}
            </h1>
            <span className="hidden sm:inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-charcoal text-white">
              {t('audit_closure.tenant_isolated')}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl">
            {data?.methodology}
          </p>
          <div className="flex items-center gap-3 text-[11px] text-brand-muted mt-2 font-mono">
            <span>{t('audit_closure.period_label')} <strong className="text-slate-700"><bdi dir="ltr">{data?.period?.label}</bdi></strong></span>
            {lastFetched && (
              <span>· {t('audit_closure.freshness_label')} <strong className="text-slate-700"><bdi dir="ltr">{lastFetched.toLocaleTimeString()}</bdi></strong></span>
            )}
          </div>
        </div>

        {/* Action Controls: PDF & CSV Exports */}
        <div className="flex flex-wrap items-center gap-2">
          <button data-motion="recovery" data-motion-tone="icon"
            type="button"
            onClick={fetchData}
            disabled={isLoading}
            className="inline-flex min-h-11 items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-300 bg-white text-xs font-bold text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
            title={t('bi.refresh_data', 'Refresh Data')}
          >
            <RefreshIcon size={14} className={isLoading ? 'motion-safe:animate-spin' : ''} />
            <span>{t('brand_analytics.refresh', 'Refresh')}</span>
          </button>

          <button data-motion="download" data-motion-tone="icon"
            type="button"
            onClick={handleDownloadCsv}
            disabled={isExportingCsv}
            className="inline-flex min-h-11 items-center gap-1.5 px-3.5 py-1.5 rounded-xl border border-slate-300 bg-white text-xs font-bold text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
          >
            <DownloadIcon size={14} />
            <span>{isExportingCsv ? t('bi.exporting_csv', 'Exporting...') : t('bi.export_csv', 'Export CSV')}</span>
          </button>

          <button data-motion="download" data-motion-tone="icon"
            type="button"
            onClick={handleDownloadPdf}
            disabled={isExportingPdf}
            className="inline-flex min-h-11 items-center gap-1.5 px-4 py-1.5 rounded-xl bg-brand-charcoal text-white text-xs font-bold hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal shadow-xs"
          >
            <DownloadIcon size={14} />
            <span>{isExportingPdf ? t('bi.generating_pdf', 'Generating PDF...') : t('bi.download_pdf', 'Download PDF Report')}</span>
          </button>
        </div>
      </div>

      {/* 2. Global Scope & Period Filters */}
      <div className="bg-white rounded-3xl border border-slate-200 p-5 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
            {t('bi.filter_scope', 'Reporting Scope & Range Filters')}
          </span>
          <button data-motion="filter" data-motion-tone="icon"
            type="button"
            onClick={handleResetFilters}
            className="inline-flex min-h-11 items-center rounded-md px-2 text-xs font-bold text-slate-600 underline hover:text-brand-charcoal"
          >
            {/* bi.reset_filters has existed in BOTH locales but was never used:
                this control hard-coded English, so the Arabic page showed
                "Reset Filters" inside a dir=rtl document. Measured at
                1280x900 and 320x640, Chromium/Firefox/WebKit. */}
            {t('bi.reset_filters', 'Reset Filters')}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Preset Buttons */}
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t('bi.preset_windows', 'Preset Windows')}>
            {presetWindows.map((win) => (
              <button data-motion="filter" data-motion-tone="icon"
                key={win.days}
                type="button"
                onClick={() => setSelectedDays(win.days)}
                aria-pressed={selectedDays === win.days}
                className={`min-h-10 px-3.5 text-xs font-bold rounded-xl border transition-all ${
                  selectedDays === win.days
                    ? 'border-brand-charcoal bg-brand-charcoal text-white shadow-xs'
                    : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
                }`}
              >
                {win.label}
              </button>
            ))}
            <button data-motion="filter" data-motion-tone="icon"
              type="button"
              onClick={() => setSelectedDays('custom')}
              aria-pressed={selectedDays === 'custom'}
              className={`min-h-10 px-3.5 text-xs font-bold rounded-xl border transition-all ${
                selectedDays === 'custom'
                  ? 'border-brand-charcoal bg-brand-charcoal text-white shadow-xs'
                  : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
              }`}
            >
              {t('brand_analytics.custom', 'Custom')}
            </button>
          </div>

          {/* Custom Date Inputs */}
          {selectedDays === 'custom' && (
            <div className="flex items-center gap-2 text-xs">
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                className="min-h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-700"
                aria-label={t('bi.start_date', 'Start Date')}
              />
              <span className="text-brand-muted">{t('audit_closure.date_to')}</span>
              <input
                type="date"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                className="min-h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-700"
                aria-label={t('bi.end_date', 'End Date')}
              />
            </div>
          )}

          {/* Branch Filter Dropdown */}
          {data?.branches && data.branches.length > 0 && (
            <select
              value={selectedBranchId ?? ''}
              onChange={(e) => setSelectedBranchId(e.target.value ? Number(e.target.value) : null)}
              className="min-h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-700 bg-white"
              aria-label={t('bi.filter_by_branch', 'Filter by branch')}
            >
              <option value="">{t('bi.all_branches', 'All Branches')} ({data.branches.length})</option>
              {data.branches.map((b) => (
                <option key={b.store_id} value={b.store_id}>
                  {b.name} ({b.city})
                </option>
              ))}
            </select>
          )}

          {/* Category Filter Dropdown */}
          {data?.categories && data.categories.length > 0 && (
            <select
              value={selectedCategoryId ?? ''}
              onChange={(e) => setSelectedCategoryId(e.target.value ? Number(e.target.value) : null)}
              className="min-h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-700 bg-white"
              aria-label={t('bi.filter_by_category', 'Filter by category')}
            >
              <option value="">{t('bi.all_categories', 'All Categories')} ({data.categories.length})</option>
              {data.categories.map((c) => (
                <option key={c.category_id} value={c.category_id}>
                  {c.category_name}
                </option>
              ))}
            </select>
          )}

          {/* Compare Toggle */}
          <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700 ms-auto">
            <input
              type="checkbox"
              checked={comparePeriod}
              onChange={(e) => setComparePeriod(e.target.checked)}
              className="rounded text-brand-charcoal focus:ring-brand-charcoal"
            />
            <span>{t('bi.compare_preceding', 'Compare with preceding period')}</span>
          </label>
        </div>
      </div>

      {/* 3. Automated Business Insights (Factual, rule-based) */}
      {data?.insights && data.insights.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.insights.map((ins, idx) => (
            <div
              key={idx}
              className={`p-4 rounded-2xl border text-xs space-y-1.5 ${
                ins.severity === 'alert'
                  ? 'bg-rose-50/70 border-rose-200 text-rose-900'
                  : ins.severity === 'warning'
                  ? 'bg-amber-50/70 border-amber-200 text-amber-900'
                  : ins.severity === 'positive'
                  ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                  : 'bg-slate-50 border-slate-200 text-slate-800'
              }`}
            >
              <div className="font-bold flex items-center justify-between">
                <span>{ins.title}</span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-white/60">
                  {t('audit_closure.observation_badge')}
                </span>
              </div>
              <p className="text-[11px] leading-relaxed opacity-90">{ins.message}</p>
            </div>
          ))}
        </div>
      )}

      {/* 4. Executive Key Performance Indicators Grid */}
      {kpis && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          {/* Gross Sales */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs border-t-4 border-t-brand-coral">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-brand-muted">{t('bi.gross_sales', 'Gross Sales')}</span>
              {renderGrowthChip('gross_sales_change_pct')}
            </div>
            <div className="font-mono text-xl font-bold text-brand-charcoal mt-1 truncate">
              {currency} {kpis.gross_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
            <span className="text-[10px] text-brand-muted block mt-0.5">{t('bi.gross_sales_desc', 'Captured line value')}</span>
          </div>

          {/* Net Sales */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs border-t-4 border-t-brand-mint">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-brand-muted">{t('bi.net_sales', 'Net Sales')}</span>
              {renderGrowthChip('net_sales_change_pct')}
            </div>
            <div className="font-mono text-xl font-bold text-[#065F46] mt-1 truncate">
              {currency} {kpis.net_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
            <span className="text-[10px] text-brand-muted block mt-0.5">{t('bi.net_sales_desc', 'Net of promos & returns')}</span>
          </div>

          {/* Completed Orders */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs border-t-4 border-t-brand-lilac">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-brand-muted">{t('bi.orders', 'Orders')}</span>
              {renderGrowthChip('orders_count_change_pct')}
            </div>
            <div className="font-mono text-xl font-bold text-brand-charcoal mt-1">
              {kpis.orders_count.toLocaleString()}
            </div>
            <span className="text-[10px] text-brand-muted block mt-0.5">{t('bi.orders_desc', 'Revenue-standing')}</span>
          </div>

          {/* Units Sold */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs border-t-4 border-t-brand-charcoal">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-brand-muted">{t('bi.units_sold', 'Units Sold')}</span>
              {renderGrowthChip('units_sold_change_pct')}
            </div>
            <div className="font-mono text-xl font-bold text-brand-charcoal mt-1">
              {kpis.units_sold.toLocaleString()}
            </div>
            <span className="text-[10px] text-brand-muted block mt-0.5">{t('bi.units_sold_desc', 'Physical merchandise')}</span>
          </div>

          {/* Average Order Value */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs border-t-4 border-t-amber-500">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-brand-muted">{t('bi.avg_order_value', 'Avg Order Value')}</span>
              {renderGrowthChip('average_order_value_change_pct')}
            </div>
            <div className="font-mono text-xl font-bold text-brand-charcoal mt-1 truncate">
              {currency} {kpis.average_order_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
            <span className="text-[10px] text-brand-muted block mt-0.5">{t('bi.avg_order_value_desc', 'Gross / orders')}</span>
          </div>

          {/* Return Rate */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs border-t-4 border-t-rose-400">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-brand-muted">{t('bi.return_rate', 'Return Rate')}</span>
            </div>
            <div className="font-mono text-xl font-bold text-brand-charcoal mt-1">
              {kpis.return_rate !== null ? `${kpis.return_rate}%` : 'N/A'}
            </div>
            <span className="text-[10px] text-brand-muted block mt-0.5">
              {kpis.returned_units} {t('bi.returns_opened', 'returns opened')}
            </span>
          </div>
        </div>
      )}

      {/* 5. Interactive Time-Series Trends */}
      {data?.trends && (
        <BiTrendChart
          data={data.trends}
          currency={currency}
          comparisonLabel={data.period.comparison_label}
        />
      )}

      {/* 6. Two-Column Category Breakdown & Top Products Ranking */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5">
          {data?.categories && (
            <BiCategoryDonut
              categories={data.categories}
              currency={currency}
              selectedCategoryId={selectedCategoryId}
              onSelectCategory={(id) => setSelectedCategoryId(id)}
            />
          )}
        </div>

        {/* Top Products Table */}
        <div className="lg:col-span-7 bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h3 className="font-serif text-lg font-bold text-brand-charcoal">
                {t('audit_closure.top_products_title')}
              </h3>
              <p className="text-[11px] text-slate-500">
                {t('audit_closure.top_products_subtitle')}
              </p>
            </div>
          </div>

          <div className="overflow-x-auto max-h-80">
            <table className="w-full text-start text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-[10px] uppercase text-slate-500">
                  <th scope="col" className="py-2 text-start">{t('bi.product', 'Product')}</th>
                  <th scope="col" className="py-2 text-start">{t('bi.category', 'Category')}</th>
                  <th scope="col" className="py-2 text-end">{t('bi.units', 'Units')}</th>
                  <th scope="col" className="py-2 text-end">{t('bi.gross_sales', 'Gross Sales')}</th>
                  <th scope="col" className="py-2 text-center">{t('bi.return_rate', 'Return Rate')}</th>
                  <th scope="col" className="py-2 text-end">{t('bi.current_stock', 'Stock')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.products && data.products.length > 0 ? (
                  data.products.slice(0, 8).map((p) => (
                    <tr key={p.product_id} className="hover:bg-slate-50">
                      <td className="py-2.5 font-bold text-brand-charcoal truncate max-w-[170px]">
                        {p.title}
                      </td>
                      <td className="py-2.5 text-slate-600">{p.category}</td>
                      <td className="py-2.5 text-end font-mono font-bold text-slate-800">{p.units_sold}</td>
                      <td className="py-2.5 text-end font-mono font-bold text-emerald-700">
                        <bdi dir="ltr">{currency} {p.gross_sales.toLocaleString(undefined, { minimumFractionDigits: 2 })}</bdi>
                      </td>
                      <td className="py-2.5 text-center font-mono text-[11px]">
                        <bdi dir="ltr">{p.return_rate !== null ? `${p.return_rate}%` : 'N/A'}</bdi>
                      </td>
                      <td className="py-2.5 text-end font-mono text-slate-700">
                        <span
                          className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            p.stock_level === 0
                              ? 'bg-rose-100 text-rose-800'
                              : p.stock_level <= 5
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {p.stock_level}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-slate-500">
                      {/*
                        These are two different facts and used to be one
                        English sentence saying the same thing for both:
                        "No products sold in this period."

                        A brand with an EMPTY CATALOGUE has nothing to sell and
                        needs to add products; a brand with products but no
                        orders this month is trading normally and should not be
                        told its catalogue is empty. `inventory.total_skus` is
                        the catalogue size, so the distinction is made from
                        served data rather than guessed.
                      */}
                      {inventory && inventory.total_skus > 0 ? (
                        <span data-testid="no-sales-yet">
                          {t('bi.no_sales_this_period')}
                        </span>
                      ) : (
                        <span data-testid="empty-catalogue" className="space-y-1">
                          <span className="block">{t('bi.no_products_in_catalogue')}</span>
                          <Link
                            to="/b2b/catalog"
                            className="inline-block text-[11px] font-semibold text-brand-charcoal underline underline-offset-2 hover:no-underline"
                          >
                            {t('bi.go_to_catalog')}
                          </Link>
                        </span>
                      )}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 7. Branch & Omnichannel Performance */}
      {data?.branches && (
        <BiBranchPerformanceTable
          branches={data.branches}
          currency={currency}
          selectedBranchId={selectedBranchId}
          onSelectBranch={(id) => setSelectedBranchId(id)}
        />
      )}

      {/* 8. Inventory Health & Replenishment Alert Panel */}
      {data?.inventory && (
        <BiInventoryHealthCard inventory={data.inventory} />
      )}

      {/* 9. Promotions & Campaign ROI */}
      {data?.promotions && data.promotions.length > 0 && (
        <BiPromotionTable promotions={data.promotions} currency={currency} />
      )}

      {/* 9b. Real Storefront Media & Fit Engagement */}
      {data?.media_engagement && (
        <div
          data-testid="brand-media-engagement-panel"
          className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 space-y-4 shadow-xs"
        >
          <div className="border-b border-slate-100 pb-3">
            <h3 className="font-serif text-lg font-bold text-brand-charcoal">
              {t('b2b.media_engagement_title')}
            </h3>
            <p className="text-xs text-brand-muted mt-0.5">
              {t('b2b.media_engagement_subtitle')}
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200">
              <span className="text-brand-muted text-[10px] block uppercase font-bold">
                {t('b2b.media_gallery_views')}
              </span>
              <span className="font-mono text-2xl font-bold text-brand-charcoal mt-1 block">
                {data.media_engagement.gallery_photo_views}
              </span>
            </div>
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200">
              <span className="text-brand-muted text-[10px] block uppercase font-bold">
                {t('b2b.media_fit_recommendations')}
              </span>
              <span className="font-mono text-2xl font-bold text-brand-charcoal mt-1 block">
                {data.media_engagement.fit_recommendations}
              </span>
            </div>
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200">
              <span className="text-brand-muted text-[10px] block uppercase font-bold">
                {t('b2b.media_wishlist_saves')}
              </span>
              <span className="font-mono text-2xl font-bold text-brand-charcoal mt-1 block">
                {data.media_engagement.wishlist_saves}
              </span>
            </div>
          </div>
          {Object.keys(data.media_engagement.photo_index_breakdown || {}).length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {Object.entries(data.media_engagement.photo_index_breakdown).map(([slot, cnt]) => (
                <span
                  key={slot}
                  className="px-3 py-1 rounded-full bg-slate-100 text-brand-charcoal text-[11px] font-semibold"
                >
                  {t('b2b.media_photo_slot', { slot: Number(slot) + 1, count: cnt })}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 10. Return Cohort Comparison (Honest, Zero Fabricated Fallbacks) */}
      <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 space-y-5 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <h3 className="font-serif text-lg font-bold text-brand-charcoal">
            {t('bi.vton_benchmark_title')}
          </h3>
          <span className="rounded-full bg-brand-mint/25 border border-brand-mint/50 px-3 py-1 text-[11px] font-bold text-[#064E3B]">
            {data?.brand?.return_rate_benchmark != null && data?.brand?.current_return_rate != null
              ? t('bi.return_delta_badge', {
                  delta: Math.round((data.brand.return_rate_benchmark - data.brand.current_return_rate) * 10) / 10,
                })
              : t('bi.return_delta_na')}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-4 text-xs">
          <div className="p-4 rounded-2xl bg-white border border-slate-200 border-t-4 border-t-brand-coral shadow-xs">
            <span className="text-brand-muted text-[10px] block uppercase font-bold">{t('bi.standard_non_tryon')}</span>
            <span className="font-mono text-xl font-bold text-brand-charcoal">
              {data?.brand?.return_rate_benchmark != null ? `${data.brand.return_rate_benchmark}%` : '—'}
            </span>
            <span className="text-[11px] text-slate-500 block mt-1">{t('bi.standard_benchmark_note')}</span>
          </div>
          <div className="p-4 rounded-2xl bg-white border border-slate-200 border-t-4 border-t-brand-mint shadow-xs">
            <span className="text-brand-muted text-[10px] block uppercase font-bold">{t('bi.tryon_assisted_title')}</span>
            <span className="font-mono text-xl font-bold text-[#065F46]">
              {data?.brand?.current_return_rate != null ? `${data.brand.current_return_rate}%` : '—'}
            </span>
            <span className="text-[11px] text-slate-500 block mt-1">{t('bi.tryon_verified_note')}</span>
          </div>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">
          {t('bi.vton_cohort_honest_note')}
        </p>
      </div>
    </div>
  );
};
